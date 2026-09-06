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
# Liveness grace. A daemon busy in a GIL/lock-holding op (embed, big ingest,
# pagerank) can't answer a ping in time but is NOT dead — SIGKILL-restarting it
# mid-op churns the daemon and risks DuckDB WAL corruption. So: ping with a
# generous timeout, and only restart a non-answering daemon when EITHER its
# process is gone (genuinely dead → restart now) OR it has missed this many
# consecutive ticks while its process stays alive (a real wedge, past grace).
WATCHDOG_PING_TIMEOUT_S = float(
    os.environ.get("RMX_HUB_WATCH_PING_TIMEOUT", "2.0"))
WATCHDOG_GRACE_MISSES = int(
    os.environ.get("RMX_HUB_WATCH_GRACE_MISSES", "3"))
QUEUE_ALERT_INTERVAL_S = float(os.environ.get("RMX_HUB_QUEUE_ALERT_INTERVAL", "1800"))
# Catalog footprint that earns a line in the queue alert. DuckDB reuses freed
# blocks but never shrinks the file, so a store can grow without bound and
# nothing notices: cliquet reached 41GB for 45 documents while every health
# signal read green. 2GB is far above any healthy store here (the largest,
# viascope, sits in the hundreds of MB) and far below "the disk is gone".
STORE_BYTES_ALERT = int(os.environ.get("RMX_HUB_STORE_BYTES_ALERT", str(2 * 1024**3)))
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
        # Subprocess, not os.fork — the hub is multi-threaded (watchdog/bus/
        # queue threads) and forking it risks a deadlocked child (see
        # spawn_daemon_subprocess).
        daemon_mod.spawn_daemon_subprocess(
            root, partition=GLOBAL_PARTITION, watch_root=[])
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
        # consecutive ping-miss counter per root, for the liveness grace window
        self.miss_counts: dict[str, int] = {}
        # root -> unix ts when a maintenance pause expires (inf = until
        # resumed). While paused the watchdog observes but NEVER restarts —
        # an operator doing a bootout/merge/repair must not fight a respawn
        # (a paused root's freshly-killed daemon got respawned 44s later and
        # took the catalog lock out from under a direct-store merge).
        self.paused_until: dict[str, float] = {}
        self._thread: threading.Thread | None = None

    # -- policy ----
    def get_policy(self, root: Path) -> str:
        return self.policy.get(str(Path(root).resolve()), "auto")

    def set_policy(self, root: Path, policy: str) -> None:
        if policy not in ("auto", "manual"):
            raise ValueError("policy must be 'auto' or 'manual'")
        self.policy[str(Path(root).resolve())] = policy

    # -- maintenance pause ----
    def pause(self, root: Path, seconds: "float | None" = None) -> float:
        """Suspend restarts for `root`. `seconds=None` pauses until `resume`.
        Returns the expiry timestamp (inf for indefinite)."""
        until = float("inf") if seconds is None else time.time() + float(seconds)
        with self._lock:
            self.paused_until[str(Path(root).resolve())] = until
        return until

    def resume(self, root: Path) -> bool:
        """Lift a maintenance pause. Returns True if one was active."""
        with self._lock:
            return self.paused_until.pop(
                str(Path(root).resolve()), None) is not None

    def is_paused(self, root: Path) -> bool:
        key = str(Path(root).resolve())
        with self._lock:
            until = self.paused_until.get(key)
            if until is None:
                return False
            if time.time() >= until:      # expired: auto-revert to policy
                del self.paused_until[key]
                return False
            return True

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
            up = bool(daemon_mod.ping(root, timeout=WATCHDOG_PING_TIMEOUT_S))
        except Exception:
            up = False
        restarted = False
        reason = ""
        if up:
            self.miss_counts[key] = 0
        elif self.is_paused(root):
            # Maintenance window: observe, never restart. Reset the miss
            # counter so a long pause doesn't bank grace-misses that trigger
            # an instant SIGKILL the moment the pause lifts.
            reason = "paused"
            self.miss_counts[key] = 0
        elif self.get_policy(root) == "auto":
            # Not answering — but is it DEAD or just BUSY/STARTING? A live
            # process holding the GIL/store-lock in a long op (embed, ingest,
            # pagerank) or still initializing isn't dead. Restarting it here is
            # a SIGKILL (`kickstart -k`) mid-op → churn + WAL-corruption risk.
            proc_alive = False
            try:
                proc_alive = daemon_mod.read_pid(root) is not None
            except Exception:
                proc_alive = False
            misses = self.miss_counts.get(key, 0) + 1
            self.miss_counts[key] = misses
            if not proc_alive:
                restarted = self._restart(root)          # genuinely dead
                reason = "no-process"
                self.miss_counts[key] = 0
            elif misses >= WATCHDOG_GRACE_MISSES:
                restarted = self._restart(root)          # wedged past grace
                reason = f"wedged-{misses}-misses"
                self.miss_counts[key] = 0
            else:
                reason = f"busy-grace-{misses}/{WATCHDOG_GRACE_MISSES}"
        with self._lock:
            ring = self.history.setdefault(key, deque(maxlen=HEALTH_HISTORY))
            ring.append({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "up": up, "restarted": restarted,
                "reason": reason,
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
            # Subprocess, not os.fork — the watchdog runs in the multi-threaded
            # hub; forking it risks a deadlocked child.
            daemon_mod.spawn_daemon_subprocess(root)
            _log(f"watchdog spawned daemon for {root}")
            return True
        except Exception as e:
            _log(f"watchdog spawn failed for {root}: {e}")
            return False

    def health(self) -> dict:
        now = time.time()
        with self._lock:
            roots = set(self.history) | set(self.policy) | set(self.paused_until)
            return {
                root: {
                    "restart_count": self.restart_counts.get(root, 0),
                    "history": list(self.history.get(root, [])),
                    "policy": self.policy.get(root, "auto"),
                    "paused_until": self.paused_until.get(root),
                    "paused": (self.paused_until.get(root) or 0) > now,
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
        # Shared model workers. The hub hosts ONE embedder + ONE reranker for
        # the whole fleet; per-project daemons connect over `models.sock`
        # instead of each spawning its own pair (7 stores x 2 models was
        # ~6.5 GB resident to serve one person typing in one project).
        # `RMX_HUB_MODELS=0` leaves them off and every daemon goes private.
        self._models = None
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

    def _op_pause(self, args: dict) -> dict:
        until = self.watchdog.pause(
            Path(args["root"]), args.get("seconds"))
        return {"paused": True, "until": None if until == float("inf") else until}

    def _op_resume(self, args: dict) -> dict:
        was = self.watchdog.resume(Path(args["root"]))
        return {"resumed": was}

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
        return {"messages": self.bus.history(
            args["channel"], int(args.get("n", 50)),
            status=args.get("status", "active"))}

    def _op_bus_read(self, args: dict) -> dict:
        return {"messages": self.bus.read(
            args["agent"], args.get("channels") or ["*"],
            peek=bool(args.get("peek")), n=args.get("n"))}

    def _op_bus_mark_read(self, args: dict) -> dict:
        return self.bus.mark_read(
            args["agent"], args["channel"], args.get("upto_seq"))

    def _op_bus_delete(self, args: dict) -> dict:
        return self.bus.delete(args["id"])

    def _op_bus_archive(self, args: dict) -> dict:
        return self.bus.archive(
            msg_id=args.get("id"), channel=args.get("channel"),
            before_ts=args.get("before_ts"))

    def _op_bus_unarchive(self, args: dict) -> dict:
        return self.bus.unarchive(args["id"])

    def _op_bus_purge(self, args: dict) -> dict:
        return self.bus.purge(
            status=args.get("status", "deleted"),
            channel=args.get("channel"), before_ts=args.get("before_ts"))

    def _op_bus_stats(self, args: dict) -> dict:
        return self.bus.stats(agent=args.get("agent"))

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
            "pause": self._op_pause,
            "resume": self._op_resume,
            "bus_pub": self._op_bus_pub,
            "bus_channels": self._op_bus_channels,
            "bus_history": self._op_bus_history,
            "bus_read": self._op_bus_read,
            "bus_mark_read": self._op_bus_mark_read,
            "bus_delete": self._op_bus_delete,
            "bus_archive": self._op_bus_archive,
            "bus_unarchive": self._op_bus_unarchive,
            "bus_purge": self._op_bus_purge,
            "bus_stats": self._op_bus_stats,
            "refine_list": self._op_refine_list,
            "refine_accept": self._op_refine_accept,
            "refine_reject": self._op_refine_reject,
            "queues": self._op_queues,
            "focus": self._op_focus,
            "focus_sessions": self._op_focus_sessions,
            "stop": self._op_stop,
            "models": self._op_models,
        }

    # -- change-queue visibility ----
    def _gather_queues(self) -> list[dict]:
        """Per-project pending-work snapshot: stale files (change queue),
        plus the machine-wide refinement-queue depth."""
        out: list[dict] = []
        for root in discovery.discover_roots():
            st = discovery.daemon_status(root)
            stale = None
            health: dict = {}
            if st["up"]:
                try:
                    resp = daemon_mod.call(
                        root, "stats",
                        {"include_stale": True, "include_health": True},
                        timeout=10.0)
                    if resp.get("ok"):
                        sf = resp["result"].get("stale_files") or []
                        stale = len(sf)
                        health = resp["result"].get("health") or {}
                except Exception:
                    stale = None
            row = {"project": discovery.store_name(root), "root": str(root),
                   "daemon_up": st["up"], "stale_files": stale}
            # Only carry health keys that are ACTIONABLE, so a healthy row stays
            # as small as it is today and a sick one is impossible to miss.
            if health.get("memory_read_ok") is False:
                row["memory_read_ok"] = False
                row["memory_read_error"] = health.get("memory_read_error")
            if health.get("slot_bound") is False:
                row["serving_legacy_catalog"] = True
                row["db_file"] = health.get("db_file")
                row["active_slot"] = health.get("active_slot")
            b = health.get("store_bytes")
            if isinstance(b, int) and b > STORE_BYTES_ALERT:
                row["store_bytes"] = b
            out.append(row)
        return out

    def _queue_alert_loop(self) -> None:
        if QUEUE_ALERT_INTERVAL_S <= 0:
            _log("queue-alert disabled (RMX_HUB_QUEUE_ALERT_INTERVAL <= 0)")
            return
        while not self._stop.is_set():
            self._stop.wait(QUEUE_ALERT_INTERVAL_S)
            if self._stop.is_set():
                break
            try:
                queues = self._gather_queues()
                pending_refine = len(self.bus.refinement_queue("pending"))
                hot = [q for q in queues
                       if (q.get("stale_files") or 0) > 0
                       or q.get("memory_read_ok") is False
                       or q.get("serving_legacy_catalog")
                       or q.get("store_bytes")]
                if hot or pending_refine:
                    self.bus.publish(
                        "global:queues",
                        {"queues": queues, "refinement_pending": pending_refine},
                        sender="hub", mtype="alert",
                    )
            except Exception as e:
                _log(f"queue-alert error: {e}")

    # -- shared model workers ----
    def _start_models(self) -> None:
        """Stand up the fleet-wide embedder + reranker.

        Best-effort by design: if the socket cannot be bound, every daemon
        falls back to its own private worker and the fleet keeps serving —
        it just costs the memory this exists to save. The hub must never be
        a single point of failure for dense retrieval.
        """
        if os.environ.get("RMX_HUB_MODELS", "1") in ("0", "false", "False"):
            _log("shared model workers disabled (RMX_HUB_MODELS=0)")
            return
        try:
            from refmatrix.modelsrv import ModelServer
            srv = ModelServer(log=_log)
            if srv.start():
                self._models = srv
                srv.warm()
        except Exception as e:
            _log(f"shared model workers failed to start: {e!r}")

    def _stop_models(self) -> None:
        srv, self._models = self._models, None
        if srv is None:
            return
        try:
            srv.stop()
        except Exception as e:
            _log(f"shared model workers stop failed: {e!r}")

    def _op_models(self, args: dict) -> dict:
        """Status of the shared workers — which are loaded, where they listen."""
        if self._models is None:
            return {"enabled": False}
        return {"enabled": True, **self._models.status()}

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
        # First: every daemon we are about to start or supervise should find
        # the shared socket already listening, or it spawns a private worker
        # pair and keeps it for its lifetime.
        self._start_models()
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
        # Preflight the port. Without this, an orphan still holding it (a
        # zombie hub whose control socket died but whose uvicorn survived)
        # makes uvicorn fail to bind inside its thread; the thread dies, the
        # serve loop falls through to shutdown(), and the user sees "hub
        # started pid=X" immediately followed by "not running". Check for an
        # active LISTENer via lsof rather than a probe bind() — a probe
        # without SO_REUSEADDR false-positives on a port in TIME_WAIT from a
        # just-stopped hub, which uvicorn (SO_REUSEADDR) would bind fine.
        other = _pid_on_port(self.port)
        if other and other != os.getpid():
            _log(f"hub port {self.port} already in use by pid {other} — run "
                 f"`rmx hub stop` (reaps the orphan) or kill it; not starting")
            self.shutdown()
            return
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
        # Models first: they hold ~900 MB across two children and no state,
        # so reaping them early gives the memory back and unlinks the socket
        # so daemons fail over to private workers immediately instead of
        # blocking on a socket nobody is accepting on.
        self._stop_models()
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
