#!/bin/bash
# scripts/ptest-docker.sh — the Docker test lane (task-t0.9-test-isolation #a-probe, #b-docker).
#
# WHY. Every test run on the workstation queued behind one lock beside the live fleet. A container
# created `--network none`, with no volume, mount, port, host pid or ipc, cannot reach a live store.
# Linux is a TEST lane only: a result from here never gates a release (T0.9 #goal).
#
#   scripts/ptest-docker.sh --build
#       Stage the build context (docker/test/Dockerfile, `.venv-eval`'s `pip freeze` minus the
#       editable refmatrix line, the two default models and cornstack/CodeRankEmbed from the host
#       HF cache) in a temp dir and
#       build `refmatrix-test:latest`, labelled `rmx.deps` = sha256 of the Dockerfile, the pins and
#       the model list. The ONLY network step of the lane: the base image, Debian's git, PyPI.
#       Prints, per pinned package, whether pip installed a wheel or built from source.
#   scripts/ptest-docker.sh --probe NAME FILE [FILE ...]
#       (a)'s one-container run: the clone goes in by `docker cp` (.git and every file git does
#       not ignore, minus .refmatrix/ and .venv*), docker/test/probe.py runs FILE… one by one,
#       results come out by `docker cp` to workflow/review-output/NAME/docker/. The container is
#       removed afterwards. (b) replaces this mode with --files/--select/--shards.
#
# Exit codes: 0 clean; 1 a test failed; 2 usage; 3 the engine is down or the image is missing or
# stale (its rmx.deps label is not the hash of today's Dockerfile, pins and models) — the reason
# and the fix are on stderr.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
IMAGE=refmatrix-test
PY="${RMX_PYTEST_PY:-$REPO/.venv-eval/bin/python}"
HF_HUB="${HF_HOME:-$HOME/.cache/huggingface}/hub"
# embedder.DEFAULT_MODEL and reranker.DEFAULT_MODEL, in the HF hub's directory naming.
# cornstack/CodeRankEmbed is the eval retriever's model: test_models_offline.py proves it loads
# offline (ch-bsd r6 #b-2) and SKIPS without it, and AC a1 needs that file to pass (probe run 1).
MODELS="models--BAAI--bge-small-en-v1.5 models--cross-encoder--ms-marco-MiniLM-L-12-v2
models--cornstack--CodeRankEmbed"

die() { local rc=$1; shift; echo "ptest-docker: $*" >&2; exit "$rc"; }

engine_up() {
  docker info --format '{{.ServerVersion}}' >/dev/null 2>&1 \
    || die 3 "the Docker engine is not reachable (start Docker Desktop, then re-run)"
}

pins() {  # the pins, stable order, the editable refmatrix line dropped
  [ -x "$PY" ] || die 2 "no interpreter at $PY (set RMX_PYTEST_PY)"
  "$PY" -m pip freeze --all 2>/dev/null | grep -v '^-e ' | grep -vE '^(pip|refmatrix)==' | LC_ALL=C sort
}

model_list() {  # one line per model: dir name and the snapshot revisions present
  local m
  for m in $MODELS; do
    [ -d "$HF_HUB/$m/snapshots" ] || die 2 "model $m is not in the host HF cache ($HF_HUB)"
    echo "$m $(ls "$HF_HUB/$m/snapshots" | LC_ALL=C sort | tr '\n' ' ')"
  done
}

deps_hash() {  # $1 = requirements file, $2 = model list file
  cat "$REPO/docker/test/Dockerfile" "$1" "$2" | shasum -a 256 | awk '{print $1}'
}

cmd_build() {
  engine_up
  local ctx
  ctx=$(mktemp -d "${TMPDIR:-/tmp}/rmx-dbuild.XXXXXX") || die 2 "mktemp failed"
  cp "$REPO/docker/test/Dockerfile" "$ctx/Dockerfile"
  pins > "$ctx/requirements.txt" || die 2 "pip freeze failed"
  [ -s "$ctx/requirements.txt" ] || die 2 "pip freeze printed no pins"
  model_list > "$ctx/models.txt" || exit $?
  mkdir -p "$ctx/models"
  local m
  for m in $MODELS; do
    # -R copies the hub's snapshot -> blob symlinks as symlinks; both halves go in.
    cp -R "$HF_HUB/$m" "$ctx/models/" || die 2 "copying $m from $HF_HUB failed"
  done
  local h
  h=$(deps_hash "$ctx/requirements.txt" "$ctx/models.txt")
  echo "ptest-docker: context $ctx ($(du -sh "$ctx" | awk '{print $1}')), rmx.deps=$h"
  local t0=$SECONDS
  docker build --platform linux/arm64 --label "rmx.deps=$h" \
      -t "$IMAGE:latest" -t "$IMAGE:${h:0:12}" "$ctx" || die 1 "docker build failed"
  echo "ptest-docker: built $IMAGE:latest in $((SECONDS - t0)) s; size $(docker image inspect \
-f '{{.Size}}' "$IMAGE:latest") bytes"
  # The wheel / source-build verdict per package, from pip's own install report.
  docker run --rm --network none "$IMAGE:latest" /opt/venv/bin/python -c '
import json
r = json.load(open("/opt/rmx/pip-report.json"))
for it in sorted(r["install"], key=lambda i: i["metadata"]["name"].lower()):
    url = it["download_info"]["url"]
    kind = "wheel" if url.endswith(".whl") else "source build"
    md = it["metadata"]
    print(md["name"] + "==" + md["version"], kind, url.rsplit("/", 1)[-1])
' || die 1 "reading the pip install report failed"
  rm -rf "$ctx"
}

image_current() {
  engine_up
  local tmp want have
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/rmx-dhash.XXXXXX") || die 2 "mktemp failed"
  pins > "$tmp/r.txt"; model_list > "$tmp/m.txt" || exit $?
  want=$(deps_hash "$tmp/r.txt" "$tmp/m.txt"); rm -rf "$tmp"
  have=$(docker image inspect -f '{{index .Config.Labels "rmx.deps"}}' "$IMAGE:latest" 2>/dev/null) \
    || die 3 "no image $IMAGE:latest; run scripts/ptest-docker.sh --build"
  [ "$have" = "$want" ] \
    || die 3 "image $IMAGE:latest is stale (rmx.deps $have, want $want); run scripts/ptest-docker.sh --build"
}

clone_tar() {  # the clone as a tar on stdout (paths relative), owned by the image's rmx user
  # EVERY directory is its own entry (`-n`, no recursion): a directory the tar only implies is
  # created by `docker cp` as root, and the unprivileged user then cannot write in it. First probe
  # run, 2026-11-25: the sandbox's refusal could not append to the root-owned
  # workflow/review-output/, and the PermissionError (an OSError) was swallowed by read_pid, so
  # two test_sandbox_children tests failed in the container and passed on the host.
  ( cd "$REPO" && {
      git ls-files -z --cached --others --exclude-standard \
        | tr '\0' '\n' | grep -vE '^(\.refmatrix/|\.venv)' | while IFS= read -r p; do
            [ -e "$p" ] || [ -L "$p" ] && printf '%s\n' "$p"; done \
        | awk '{ n = split($0, a, "/"); d = a[1]
                 for (i = 2; i <= n; i++) { print d; d = d "/" a[i] }
                 print $0 }' | LC_ALL=C sort -u
      find .git
    } | COPYFILE_DISABLE=1 tar -c -n -f - --no-mac-metadata --no-xattrs --uid 1000 --gid 1000 \
          -T - )
}

cmd_probe() {
  local name=${1:-}; [ -n "$name" ] || die 2 "--probe needs a NAME and files"; shift
  [ $# -gt 0 ] || die 2 "--probe needs test files"
  image_current
  local out="$REPO/workflow/review-output/$name/docker"
  mkdir -p "$out"
  local sha dirty cid
  sha=$(git -C "$REPO" rev-parse HEAD); dirty=$(git -C "$REPO" status --porcelain | wc -l | tr -d ' ')
  cid=$(docker create --network none -w /home/rmx/work "$IMAGE:latest" \
        /opt/venv/bin/python /home/rmx/work/docker/test/probe.py /home/rmx/out "$@") \
    || die 1 "docker create failed"
  echo "ptest-docker: container ${cid:0:12} sha=$sha uncommitted=$dirty image=$(docker image \
inspect -f '{{.Id}}' "$IMAGE:latest")" | tee "$out/header.txt"
  clone_tar | docker cp -a - "$cid:/home/rmx/work" || { docker rm -f "$cid" >/dev/null; die 1 "docker cp in failed"; }
  echo "# start $(date '+%F %T') host load $(sysctl -n vm.loadavg)" >> "$out/header.txt"
  docker start -a "$cid" | tee "$out/stdout.txt"
  local rc
  rc=$(docker inspect -f '{{.State.ExitCode}}' "$cid")
  echo "# end $(date '+%F %T') host load $(sysctl -n vm.loadavg) exit $rc" >> "$out/header.txt"
  docker inspect -f 'NetworkMode={{.HostConfig.NetworkMode}} Mounts={{len .Mounts}}' "$cid" \
    | tee -a "$out/header.txt"
  docker cp "$cid:/home/rmx/out/." "$out/" || echo "ptest-docker: docker cp out failed" >&2
  docker rm "$cid" >/dev/null
  echo "ptest-docker: results in $out (exit $rc)"
  return "$rc"
}

case "${1:-}" in
  --build) cmd_build ;;
  --probe) shift; cmd_probe "$@" ;;
  *) die 2 "usage: ptest-docker.sh --build | --probe NAME FILE [FILE ...]" ;;
esac
