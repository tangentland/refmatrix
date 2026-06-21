"""The refmatrix hub — one user-level, launchd-supervised process that sits
*above* the per-project daemons.

Responsibilities:
  * **Watchdog** — poll every discovered store's daemon, keep a health history,
    and restart the dead ones (launchctl kickstart when supervised, else a
    direct `spawn_daemon`).
  * **Control socket** (`~/.refmatrix/hub.sock`) — newline-delimited JSON RPC so
    `rmx hub …` / terminal agents can query and drive the hub.
  * **Global store** — owns `~/.refmatrix/global/.refmatrix/` (partition
    `global`) for cross-project "Claude behavior" memories.
  * **UI host** — when `refmatrix[ui]` is installed, `run()` also serves the
    FastAPI web app; otherwise it supervises headless.

The per-project daemons are unchanged; the hub never owns their catalogs.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

from refmatrix import daemon as daemon_mod
from refmatrix import discovery, launchctl
from refmatrix.bus import Bus
from refmatrix.taxonomy import user_home

HUB_SOCK = "hub.sock"
HUB_PID = "hub.pid"
HUB_LOG = "hub.log"
GLOBAL_PARTITION = "global"
DEFAULT_PORT = 7777
WATCHDOG_INTERVAL_S = float(os.environ.get("RMX_HUB_WATCH_INTERVAL", "15"))
QUEUE_ALERT_INTERVAL_S = float(os.environ.get("RMX_HUB_QUEUE_ALERT_INTERVAL", "60"))
HEALTH_HISTORY = 50


# ---- paths ----------------------------------------------------------------


def hub_home() -> Path:
    return user_home()


def hub_sock_path() -> Path:
    return hub_home() / HUB_SOCK


def hub_pid_path() -> Path:
    return hub_home() / HUB_PID


def hub_log_path() -> Path:
    return hub_home() / HUB_LOG


def global_store_root() -> Path:
    """Root of the user-level "global" store. This IS the hub home
    (`~/.refmatrix`) — the home dir doubles as the cross-project store, holding
    its catalog alongside the registry/taxonomy/bus. `_root()` falls back here
    when no project `.refmatrix` is found, so a bare `rmx` command targets the
    user's global store instead of auto-creating a junk one."""
    return hub_home()


def _log(msg: str) -> None:
    try:
        hub_home().mkdir(parents=True, exist_ok=True)
        with hub_log_path().open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    except OSError:
        pass


# ---- global memory store --------------------------------------------------


def _bootstrap_global_store() -> None:
    """One-time schema create for the global store (the only sanctioned direct
    Store() open — the store's daemon doesn't exist yet). Ongoing access goes
    through `global_call` / the daemon."""
    from refmatrix.store import Store
    root = global_store_root()
    root.mkdir(parents=True, exist_ok=True)
    s = Store(root)
    s.init()
    s.close()


def ensure_global_daemon() -> bool:
    """Make sure the global store has a (watcher-less) daemon serving. The
    store is memory-only, so no filesystem watch. Returns True if up."""
    root = global_store_root()
    if daemon_mod.ping(root):
        return True
    _bootstrap_global_store()
    try:
        daemon_mod.spawn_daemon(root, partition=GLOBAL_PARTITION, watch_root=[])
    except Exception as e:
        _log(f"global daemon spawn failed: {e}")
        return False
    return daemon_mod.ping(root)


def global_call(op: str, args: dict | None = None, *, timeout: float = 60.0) -> dict:
    """Route a memory op to the global store's daemon (the single writer for
    global behavior memories). Ensures the daemon is up first."""
    ensure_global_daemon()
    a = {**(args or {}), "partition": GLOBAL_PARTITION}
    return daemon_mod.call(global_store_root(), op, a, timeout=timeout)


# ---- watchdog -------------------------------------------------------------


class Watchdog:
    """Polls discovered stores and restarts dead daemons per policy.

    `policy[root]` is 'auto' (restart on death) or 'manual' (observe only).
    Default is auto. Health is a bounded ring of {ts, up, restarted} per root.
    """

    def __init__(self, interval: float = WATCHDOG_INTERVAL_S):
        self.interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.policy: dict[str, str] = {}
        self.history: dict[str, deque] = {}
        self.restart_counts: dict[str, int] = {}
        self._thread: threading.Thread | None = None

    # -- policy ----
    def get_policy(self, root: Path) -> str:
        return self.policy.get(str(Path(root).resolve()), "auto")

    def set_policy(self, root: Path, policy: str) -> None:
        if policy not in ("auto", "manual"):
            raise ValueError("policy must be 'auto' or 'manual'")
        self.policy[str(Path(root).resolve())] = policy

    # -- lifecycle ----
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="rmx-hub-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:  # never let the watchdog die
                _log(f"watchdog tick error: {e}")
            self._stop.wait(self.interval)

    def tick(self) -> None:
        for root in discovery.discover_roots():
            self._check(root)

    def _check(self, root: Path) -> None:
        key = str(Path(root).resolve())
        up = False
        try:
            up = bool(daemon_mod.ping(root))
        except Exception:
            up = False
        restarted = False
        if not up and self.get_policy(root) == "auto":
            restarted = self._restart(root)
        with self._lock:
            ring = self.history.setdefault(key, deque(maxlen=HEALTH_HISTORY))
            ring.append({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "up": up, "restarted": restarted,
            })
            if restarted:
                self.restart_counts[key] = self.restart_counts.get(key, 0) + 1

    def _restart(self, root: Path) -> bool:
        """Restart a dead daemon: prefer launchd kickstart (it owns the
        process), else spawn directly."""
        try:
            if launchctl.is_loaded(root):
                launchctl.kickstart(root, restart=True)
                _log(f"watchdog kickstarted {root}")
                return True
        except Exception as e:
            _log(f"watchdog kickstart failed for {root}: {e}")
        try:
            daemon_mod.spawn_daemon(root)
            _log(f"watchdog spawned daemon for {root}")
            return True
        except Exception as e:
            _log(f"watchdog spawn failed for {root}: {e}")
            return False

    def health(self) -> dict:
        with self._lock:
            roots = set(self.history) | set(self.policy)
            return {
                root: {
                    "restart_count": self.restart_counts.get(root, 0),
                    "history": list(self.history.get(root, [])),
                    "policy": self.policy.get(root, "auto"),
                }
                for root in roots
            }


# ---- control RPC server ---------------------------------------------------


class Hub:
    """Holds shared state (watchdog) and serves the hub.sock control RPC."""

    def __init__(self, *, port: int = DEFAULT_PORT):
        self.port = port
        self.watchdog = Watchdog()
        self.bus = Bus()
        from refmatrix.scheduler import Scheduler
        self.scheduler = Scheduler()
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._alert_thread: threading.Thread | None = None

    # -- ops ----
    def _op_ping(self, args: dict) -> dict:
        return {"pid": os.getpid(), "port": self.port}

    def _op_hub_info(self, args: dict) -> dict:
        return {
            "pid": os.getpid(),
            "port": self.port,
            "home": str(hub_home()),
            "watch_interval_s": self.watchdog.interval,
            "registry_size": len(discovery.load_registry()),
        }

    def _op_projects(self, args: dict) -> dict:
        fp = bool(args.get("with_footprint", True))
        return {"projects": discovery.all_projects(with_footprint=fp)}

    def _op_usage(self, args: dict) -> dict:
        from refmatrix import telemetry
        roots = discovery.discover_roots()
        return telemetry.summarize_all(roots, since=args.get("since"))

    def _op_adoption(self, args: dict) -> dict:
        from refmatrix import telemetry
        out = []
        for root in discovery.discover_roots():
            st = discovery.daemon_status(root)
            stats = None
            if st["up"]:
                try:
                    resp = daemon_mod.call(root, "stats", {"include_stale": True})
                    if resp.get("ok"):
                        stats = resp["result"]
                except Exception:
                    stats = None
            lc = discovery.launchd_state(root)
            sigs = telemetry.adoption_report(
                root, stats=stats, daemon_up=st["up"],
                launchd_installed=lc["installed"], since=args.get("since"),
            )
            if sigs:
                out.append({"root": str(root), "name": discovery.store_name(root),
                            "signals": sigs})
        return {"projects": out}

    def _op_health(self, args: dict) -> dict:
        return {"health": self.watchdog.health()}

    def _op_restart(self, args: dict) -> dict:
        root = Path(args["root"])
        ok = self.watchdog._restart(root)
        return {"restarted": ok}

    def _op_set_watchdog(self, args: dict) -> dict:
        self.watchdog.set_policy(Path(args["root"]), args["policy"])
        return {"ok": True, "policy": args["policy"]}

    def _op_stop(self, args: dict) -> dict:
        self._stop.set()
        return {"stopping": True}

    # -- bus ----
    def _op_bus_pub(self, args: dict) -> dict:
        msg = self.bus.publish(
            args["channel"], args.get("body"),
            sender=args.get("from", "?"), project=args.get("project"),
            mtype=args.get("type", "announce"), reply_to=args.get("reply_to"),
        )
        return {"message": msg}

    def _op_bus_channels(self, args: dict) -> dict:
        return {"channels": self.bus.channels()}

    def _op_bus_history(self, args: dict) -> dict:
        return {"messages": self.bus.history(args["channel"], int(args.get("n", 50)))}

    def _op_refine_list(self, args: dict) -> dict:
        return {"candidates": self.bus.refinement_queue(args.get("status", "pending"))}

    def _op_refine_accept(self, args: dict) -> dict:
        return self.bus.accept_refinement(args["id"])

    def _op_refine_reject(self, args: dict) -> dict:
        return self.bus.reject_refinement(args["id"])

    def _op_queues(self, args: dict) -> dict:
        return {"queues": self._gather_queues()}

    # -- short-term focus (per-project, read-only aggregation) ----
    def _op_focus(self, args: dict) -> dict:
        from refmatrix import stm as stm_mod
        s = stm_mod.Stm(Path(args["root"]), args.get("session") or "default")
        return {"graph": s.focus_graph(top=int(args.get("top", 30))),
                "tasks": s.task_list()}

    def _op_focus_sessions(self, args: dict) -> dict:
        from refmatrix import stm as stm_mod
        d = stm_mod.stm_dir(Path(args["root"]))
        sessions = []
        if d.is_dir():
            for p in d.glob("*.jsonl"):
                sessions.append(p.stem)
        return {"sessions": sessions}

    @property
    def OPS(self) -> dict[str, Callable[[dict], dict]]:
        return {
            "ping": self._op_ping,
            "hub_info": self._op_hub_info,
            "projects": self._op_projects,
            "usage": self._op_usage,
            "adoption": self._op_adoption,
            "health": self._op_health,
            "restart": self._op_restart,
            "set_watchdog": self._op_set_watchdog,
            "bus_pub": self._op_bus_pub,
            "bus_channels": self._op_bus_channels,
            "bus_history": self._op_bus_history,
            "refine_list": self._op_refine_list,
            "refine_accept": self._op_refine_accept,
            "refine_reject": self._op_refine_reject,
            "queues": self._op_queues,
            "focus": self._op_focus,
            "focus_sessions": self._op_focus_sessions,
            "stop": self._op_stop,
        }

    # -- change-queue visibility ----
    def _gather_queues(self) -> list[dict]:
        """Per-project pending-work snapshot: stale files (change queue),
        plus the machine-wide refinement-queue depth."""
        out: list[dict] = []
        for root in discovery.discover_roots():
            st = discovery.daemon_status(root)
            stale = None
            if st["up"]:
                try:
                    resp = daemon_mod.call(root, "stats", {"include_stale": True},
                                           timeout=10.0)
                    if resp.get("ok"):
                        sf = resp["result"].get("stale_files") or []
                        stale = len(sf)
                except Exception:
                    stale = None
            out.append({"project": discovery.store_name(root), "root": str(root),
                        "daemon_up": st["up"], "stale_files": stale})
        return out

    def _queue_alert_loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(QUEUE_ALERT_INTERVAL_S)
            if self._stop.is_set():
                break
            try:
                queues = self._gather_queues()
                pending_refine = len(self.bus.refinement_queue("pending"))
                hot = [q for q in queues if (q.get("stale_files") or 0) > 0]
                if hot or pending_refine:
                    self.bus.publish(
                        "global:queues",
                        {"queues": queues, "refinement_pending": pending_refine},
                        sender="hub", mtype="alert",
                    )
            except Exception as e:
                _log(f"queue-alert error: {e}")

    # -- socket server ----
    def serve_sock(self) -> None:
        sp = hub_sock_path()
        sp.parent.mkdir(parents=True, exist_ok=True)
        if sp.exists():
            sp.unlink()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sp))
        srv.listen(16)
        srv.settimeout(1.0)
        self._sock = srv
        _log(f"hub sock listening at {sp}")
        while not self._stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle, args=(conn,), daemon=True).start()
        try:
            srv.close()
            sp.unlink()
        except OSError:
            pass

    def _handle(self, conn: socket.socket) -> None:
        try:
            buf = b""
            conn.settimeout(5.0)
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
            req = json.loads(buf.decode())
            op = req.get("op")
            if op == "bus_sub":
                self._stream_bus_sub(conn, req.get("args") or {})
                return
            handler = self.OPS.get(op)
            if handler is None:
                resp = {"ok": False, "error": f"unknown op: {op}"}
            else:
                resp = {"ok": True, "result": handler(req.get("args") or {})}
        except Exception as e:
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            conn.sendall((json.dumps(resp) + "\n").encode())
        except OSError:
            pass
        finally:
            conn.close()

    def _stream_bus_sub(self, conn: socket.socket, args: dict) -> None:
        """Long-lived subscription: stream newline-JSON messages until the
        client disconnects. Optionally replays `history` backlog first."""
        patterns = args.get("channels") or args.get("patterns") or ["*"]
        if isinstance(patterns, str):
            patterns = [patterns]
        sub = self.bus.subscribe(patterns)
        conn.settimeout(1.0)
        try:
            backlog = int(args.get("history", 0))
            if backlog and len(patterns) == 1 and not patterns[0].endswith(("*", ":")):
                for m in self.bus.history(patterns[0], backlog):
                    conn.sendall((json.dumps(m) + "\n").encode())
            while not self._stop.is_set():
                try:
                    msg = sub.q.get(timeout=1.0)
                except Exception:
                    # idle: probe the socket so a dead client is noticed
                    try:
                        conn.sendall(b"")
                    except OSError:
                        break
                    continue
                try:
                    conn.sendall((json.dumps(msg) + "\n").encode())
                except OSError:
                    break
        finally:
            self.bus.unsubscribe(sub)
            try:
                conn.close()
            except OSError:
                pass

    # -- run ----
    def run(self, *, host: str = "127.0.0.1", serve_http: bool = True) -> None:
        hub_home().mkdir(parents=True, exist_ok=True)
        hub_pid_path().write_text(str(os.getpid()))
        _log(f"hub starting pid={os.getpid()} port={self.port}")
        try:
            ensure_global_daemon()
            discovery.register_root(global_store_root())  # watchdog supervises it
        except Exception as e:
            _log(f"global store init failed: {e}")
        self.watchdog.start()
        self.scheduler.start()
        self._alert_thread = threading.Thread(
            target=self._queue_alert_loop, name="rmx-hub-queue-alert", daemon=True)
        self._alert_thread.start()
        threading.Thread(target=self.serve_sock, name="rmx-hub-sock",
                         daemon=True).start()

        def _sig(_signum, _frame):
            self._stop.set()
        for s in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(s, _sig)
            except ValueError:
                pass  # not main thread

        if serve_http:
            try:
                self._serve_http(host)
                return
            except ImportError:
                _log("fastapi/uvicorn not installed — supervising headless "
                     "(install refmatrix[ui] for the web UI)")
        # Headless idle loop.
        while not self._stop.is_set():
            self._stop.wait(1.0)
        self.shutdown()

    def _serve_http(self, host: str) -> None:
        import uvicorn  # noqa: F401  (ImportError bubbles to run())
        from refmatrix.ui.server import create_app
        # Preflight the port. Without this, an orphan still holding the port
        # (a zombie hub whose control socket died but whose uvicorn survived)
        # makes uvicorn fail to bind inside its thread; the thread dies, the
        # serve loop falls through to shutdown(), and the user sees "hub
        # started pid=X" immediately followed by "not running" — the wedge
        # that drove the crash-loop debugging. Surface it as a clear log.
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, self.port))
        except OSError:
            other = _pid_on_port(self.port)
            who = f" by pid {other}" if other else ""
            _log(f"hub port {self.port} already in use{who} — run "
                 f"`rmx hub stop` (reaps the orphan) or kill it; not starting")
            probe.close()
            self.shutdown()
            return
        finally:
            probe.close()
        app = create_app(self)
        config = uvicorn.Config(app, host=host, port=self.port,
                                log_level="warning")
        server = uvicorn.Server(config)

        # Run uvicorn in a thread so we can watch self._stop.
        th = threading.Thread(target=server.run, daemon=True)
        th.start()
        while not self._stop.is_set() and th.is_alive():
            self._stop.wait(0.5)
        server.should_exit = True
        th.join(timeout=5)
        self.shutdown()

    def shutdown(self) -> None:
        _log("hub stopping")
        self.watchdog.stop()
        try:
            hub_pid_path().unlink()
        except OSError:
            pass


# ---- lifecycle (module-level, for the CLI) --------------------------------


def hub_pid() -> int | None:
    p = hub_pid_path()
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return None


def is_running() -> bool:
    """A hub is up if its control socket answers ping."""
    sp = hub_sock_path()
    if not sp.exists():
        return False
    try:
        return rpc("ping", timeout=0.5).get("ok", False)
    except Exception:
        return False


def rpc(op: str, args: dict | None = None, *, timeout: float = 30.0) -> dict:
    """Send a control-RPC to the running hub. Returns the parsed response."""
    sp = hub_sock_path()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(sp))
        s.sendall((json.dumps({"op": op, "args": args or {}}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode()) if buf else {"ok": False, "error": "no response"}
    finally:
        s.close()


def subscribe_stream(patterns, *, history: int = 0):
    """Connect to the hub bus and yield messages as they arrive. Blocks;
    the caller breaks out (e.g. KeyboardInterrupt). Closes on hub shutdown."""
    if isinstance(patterns, str):
        patterns = [patterns]
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(str(hub_sock_path()))
    s.sendall((json.dumps({"op": "bus_sub",
                           "args": {"channels": patterns, "history": history}}) + "\n").encode())
    buf = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if line:
                    yield json.loads(line)
    finally:
        s.close()


def spawn_hub(*, port: int = DEFAULT_PORT, host: str = "127.0.0.1",
              wait: float = 5.0) -> int:
    """Fork a detached hub process and wait until it answers. Idempotent."""
    if is_running():
        return hub_pid() or -1
    pid = os.fork()
    if pid == 0:  # child
        os.setsid()
        # Detach stdio.
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        try:
            Hub(port=port).run(host=host)
        finally:
            os._exit(0)
    # parent
    deadline = time.time() + wait
    while time.time() < deadline:
        if is_running():
            return hub_pid() or pid
        time.sleep(0.1)
    return pid


def _pid_on_port(port: int) -> int | None:
    """PID of the process LISTENing on `port`, or None. Best-effort via lsof
    (no extra dep). Used to find/reap a hub orphan that lost its control
    socket but still holds the HTTP port."""
    import subprocess
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=5).stdout.split()
    except Exception:
        return None
    for tok in out:
        if tok.isdigit():
            return int(tok)
    return None


def stop_hub(*, timeout: float = 5.0, port: int = DEFAULT_PORT) -> bool:
    """Ask the hub to stop; fall back to SIGTERM, then reap any orphan still
    holding the HTTP port. Returns True if nothing is left running."""
    if is_running():
        try:
            rpc("stop", timeout=2.0)
        except Exception:
            pass
    pid = hub_pid()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_running():
            try:
                hub_pid_path().unlink()
            except OSError:
                pass
            break
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                break
            except OSError:
                pass
        time.sleep(0.2)
    # Reap a port-orphan: a zombie hub whose control socket is dead (so
    # is_running()/rpc can't reach it) but whose uvicorn still squats the
    # port, blocking every future `hub start`. The socket-based stop above
    # is blind to it; kill it by port.
    orphan = _pid_on_port(port)
    if orphan and orphan != os.getpid():
        try:
            os.kill(orphan, signal.SIGTERM)
            for _ in range(15):
                time.sleep(0.2)
                if _pid_on_port(port) != orphan:
                    break
            else:
                os.kill(orphan, signal.SIGKILL)
        except OSError:
            pass
    return not is_running() and _pid_on_port(port) is None


def status() -> dict:
    running = is_running()
    info: dict[str, Any] = {"running": running, "pid": hub_pid(),
                            "sock": str(hub_sock_path()), "home": str(hub_home())}
    if running:
        try:
            r = rpc("hub_info")
            if r.get("ok"):
                info.update(r["result"])
        except Exception:
            pass
    return info
