# docker/test/Dockerfile — the T0.9 test image (task-t0.9-test-isolation #a-probe, L170/L171).
#
# WHY. Every test run on the workstation queued behind one lock beside the live fleet. A container
# started `--network none` with no volume, mount, port, host pid or ipc cannot reach a live store,
# so the portable test files can run there side by side. Linux is a TEST lane, not a supported
# runtime: a result from this image never gates a release.
#
# Built ONLY by `scripts/ptest-docker.sh --build`, which stages the build context (this file,
# `requirements.txt` = `.venv-eval`'s `pip freeze` minus the editable `refmatrix` line, and the two
# default models plus cornstack/CodeRankEmbed, copied from the host's HF cache). The base image,
# Debian's packages and PyPI are the build's network steps; nothing in a test run touches the
# network.
#
# The code under test is NOT in the image: a run copies the clone in (`docker cp`) and imports it
# through `PYTHONPATH=<clone>/src`, exactly as a littlebig clone runs the dev interpreter.
FROM --platform=linux/arm64 python:3.14-slim-bookworm

# git: tests drive `git` in their throwaway repos and the runner records the clone's sha.
# gcc + libc6-dev: PyStemmer 3.0.0 has no cp314 linux-aarch64 wheel and builds from source
# (first T0.9 probe build, 2026-11-25: "No such file or directory: 'gcc'").
RUN apt-get update \
 && apt-get install -y --no-install-recommends git gcc libc6-dev \
 && rm -rf /var/lib/apt/lists/*

# An unprivileged user: root ignores file modes, and several tests prove a refusal on an
# unreadable or unwritable path.
RUN useradd --create-home --uid 1000 --shell /bin/bash rmx

# The venv. `--report` records, per package, the file pip installed (a `.whl` = a wheel, else a
# source build); `ptest-docker.sh --build` prints it for the probe table.
COPY requirements.txt /opt/rmx/requirements.txt
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir --report /opt/rmx/pip-report.json \
        -r /opt/rmx/requirements.txt

# The dev `rmx` beside the interpreter, where `tests/devbin.py::dev_rmx` looks. It is the
# console script pip would write for `refmatrix.cli:cli_entry`; `refmatrix` itself comes from
# the copied clone's `src` (`devbin.dev_env` puts it first on PYTHONPATH for every child).
RUN printf '%s\n' '#!/opt/venv/bin/python' 'import sys' \
        'from refmatrix.cli import cli_entry' 'sys.exit(cli_entry())' > /opt/venv/bin/rmx \
 && chmod 0755 /opt/venv/bin/rmx

# The two default models (embedder.DEFAULT_MODEL, reranker.DEFAULT_MODEL) and the eval
# retriever's cornstack/CodeRankEmbed (test_models_offline.py proves it loads offline), in the HF
# hub layout under the real home's cache, where `rmx_sandbox.redirect` points HF_HOME.
COPY --chown=rmx:rmx models/ /home/rmx/.cache/huggingface/hub/

ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HF_HOME=/home/rmx/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# The clone lands here by `docker cp` (its tar carries every directory, owned by uid 1000).
RUN install -d -o rmx -g rmx /home/rmx/work

USER rmx
WORKDIR /home/rmx/work
