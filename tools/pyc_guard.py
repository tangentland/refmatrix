#!/usr/bin/env python3
"""Refuse timestamp-invalidated bytecode under a tree we edit (bug-037).

2026-09-16: a mutation check edited `"45"` -> `"20"` in `modelsrv.py` — the
SAME byte length — and the source was then restored from a backup.
`PROBE_TIMEOUT_S` read 20.0 at runtime while the file on disk read 45, same
file, same interpreter, and two tests failed for a reason that had nothing to
do with the code under test. `python -B` does not help: it skips WRITING
bytecode, not reading it.

CPython validates a timestamp `.pyc` against the source's `(mtime, size)`
pair. A same-length edit removes size as a discriminator; a restore that
lands the source on the mtime the `.pyc` recorded removes the other, and the
stale bytecode is served with nothing said. Hash-based bytecode (PEP 552,
`checked-hash`) validates against the source's hash instead, which no
combination of mtime and length can fake.

So: before a suite runs over this tree, every `.pyc` under it is either
absent or `checked-hash`, and the ones that are not are recompiled in place
and NAMED. A silent repair on the path between source and test result is the
same class of failure as a silent skip on a memory path.

`RMX_PYC_GUARD=0` opts a run out.

Standalone use — after any mutation batch:

    python3 tools/pyc_guard.py src/refmatrix
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

# `.pyc` layout (PEP 552): magic[4] | flags[4, little-endian] | 8 bytes that
# are (mtime, size) for a timestamp pyc and the source hash for a hash-based
# one. Bit 0 of flags = hash-based; bit 1 = check_source.
_HEADER = 16
_FLAG_HASH_BASED = 0b01
_FLAG_CHECK_SOURCE = 0b10

# Roots this process has enforced, os.pathsep-joined. Read by the suite to
# prove the session guard ran over the dev tree and not merely that the
# helper works.
ENFORCED_ROOTS_ENV = "RMX_PYC_GUARD_ROOTS"


def pyc_flags(path: "str | Path") -> int:
    """The flags word of a `.pyc`. Raises on a file too short to have one —
    a truncated pyc is not "safe by default"."""
    with open(path, "rb") as fh:
        head = fh.read(_HEADER)
    if len(head) < _HEADER:
        raise ValueError(f"{path}: truncated pyc ({len(head)} bytes)")
    return struct.unpack("<I", head[4:8])[0]


def pyc_is_safe(path: "str | Path") -> bool:
    """True only for `checked-hash` bytecode.

    `unchecked-hash` (bit 0 set, bit 1 clear) is deliberately NOT safe: it
    tells the interpreter to skip validation entirely, which is worse than a
    timestamp pyc rather than better.
    """
    try:
        flags = pyc_flags(path)
    except (OSError, ValueError):
        return False
    return bool(flags & _FLAG_HASH_BASED) and bool(flags & _FLAG_CHECK_SOURCE)


def scan_unsafe(root: "str | Path") -> list[Path]:
    """Every `.pyc` under `root` that is not `checked-hash`, sorted."""
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("__pycache__/*.pyc")
                  if not pyc_is_safe(p))


def stale_timestamp_pycs(root: "str | Path") -> list[Path]:
    """Timestamp `.pyc`s under `root` whose recorded `(mtime, size)` no longer
    matches the source on disk — bytecode the interpreter would REBUILD, not
    serve.

    The invariant worth asserting during a run is not "no timestamp pyc
    exists": the import machinery writes one for every module it compiles, and
    always as a timestamp pyc (`SOURCE_DATE_EPOCH` only reaches `py_compile`,
    never `importlib`). It is that no bytecode on disk disagrees with the
    source beside it. bug-037 is exactly a pyc that AGREED by `(mtime, size)`
    and disagreed in content; `enforce` converts those to `checked-hash` at
    session start, and everything written after that came from the source this
    process just read.
    """
    import importlib.util

    root = Path(root)
    out: list[Path] = []
    for pyc in sorted(root.rglob("__pycache__/*.pyc")):
        try:
            flags = pyc_flags(pyc)
        except (OSError, ValueError):
            out.append(pyc)
            continue
        if flags & _FLAG_HASH_BASED:
            continue                    # validated by hash, not by stat
        try:
            src = Path(importlib.util.source_from_cache(str(pyc)))
        except (ValueError, NotImplementedError):
            continue
        if not src.exists():
            out.append(pyc)
            continue
        with open(pyc, "rb") as fh:
            head = fh.read(_HEADER)
        rec_mtime, rec_size = struct.unpack("<II", head[8:16])
        st = src.stat()
        if (int(st.st_mtime) & 0xFFFFFFFF) != rec_mtime or \
                (st.st_size & 0xFFFFFFFF) != rec_size:
            out.append(pyc)
    return out


def enforce(root: "str | Path", *, out=None) -> int:
    """Recompile every unsafe `.pyc` under `root` as `checked-hash`.

    Returns the number of files acted on, and prints what it did — the count
    is the signal that a mutation batch left bytecode behind.

    Scoped strictly to `root`: recompiling site-packages or the deploy tree
    is not this function's business, and a guard that wandered would be a
    worse bug than the one it fixes.
    """
    out = out or sys.stdout
    if os.environ.get("RMX_PYC_GUARD", "1") in ("0", "false", "False"):
        return 0

    import importlib.util
    import py_compile

    unsafe = scan_unsafe(root)
    done = 0
    for pyc in unsafe:
        try:
            src = Path(importlib.util.source_from_cache(str(pyc)))
        except (ValueError, NotImplementedError) as exc:
            print(f"pyc-guard: cannot map {pyc} to a source ({exc}); left alone",
                  file=out)
            continue
        if not src.exists():
            # Orphan bytecode: the source is gone, so nothing can validate it.
            pyc.unlink()
            done += 1
            print(f"pyc-guard: removed orphan {pyc}", file=out)
            continue
        try:
            py_compile.compile(
                str(src), cfile=str(pyc), doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
            )
        except py_compile.PyCompileError as exc:
            # A source that does not compile is a real failure of this tree,
            # not something to swallow: say it and keep going so the count
            # stays honest.
            print(f"pyc-guard: {src} failed to compile: {exc}", file=out)
            continue
        done += 1
    if done:
        print(f"pyc-guard: recompiled {done} timestamp pyc(s) under {root} "
              f"as checked-hash (bug-037)", file=out)
    # Record the root in the environment so a CHILD process — and a test
    # asserting the wiring rather than the helper — can see that this tree was
    # enforced, and by whom. A guard nobody calls guards nothing.
    seen = [p for p in os.environ.get(ENFORCED_ROOTS_ENV, "").split(os.pathsep) if p]
    here = str(Path(root).resolve())
    if here not in seen:
        seen.append(here)
        os.environ[ENFORCED_ROOTS_ENV] = os.pathsep.join(seen)
    return done


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    roots = args or [str(Path(__file__).resolve().parents[1] / "src")]
    total = 0
    for r in roots:
        total += enforce(r)
    if not total:
        print(f"pyc-guard: clean ({', '.join(roots)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
