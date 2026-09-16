---
gmd: "0.1"
id: cli-startup-gap-0916
title: "Attribution: the 8.5 s between build_context and the CLI"
tags: [measurement, performance, bug-033, longmemeval]
metadata:
  node_type: measurement
  created: 2026-09-16
---

# Attribution: where the daemonless `rmx context` seconds go {#root}

rel: evidence-for -> [[task-12.6-cli-startup-gap]]
rel: part-of -> [[plan-12-open-bug-remediation]]
rel: derives-from -> [[feedback_causal_story_before_evidence]]

## Instrument {#instrument}

`RMX_TIME_PHASES=1` emits one line to **stderr** (never stdout — that is the hook payload):

```
rmx phases: import=0.027s click-parse=0.000s context-import=0.012s dispatch=0.000s
            route-decision=0.000s replica-build_context=0.668s exit=0.000s total=0.707s
```

Each number is the cost of the phase it NAMES. `import` is module-import to CLI entry;
`exit` is the tail after the last mark. Everything before `import` belongs to the interpreter and
is measured with `-X importtime` (refmatrix 21 ms, rich 10 ms, click 4 ms — not the cost).

> The first version of this instrument labelled each interval with the phase that ended at its
> START, so it billed `store-bind` for `build_context`'s seconds, and the first version of THIS
> document told the reader to shift the labels instead of the code shifting them (ch-bsd plan-12
> #b-2). Fixed in `render_phase_report`; `test_each_interval_carries_the_phase_that_produced_it`
> pins costs in advance and asserts which label carries which interval. The figures below were
> re-taken after the fix.

## Finding 1: a real defect, and it was not in retrieval {#backstop}

On a store whose root resolves to the GLOBAL `~/.refmatrix`, `rmx context "<phrase>"` took
**15.09 s, twice, reproducibly** — and `--no-grep` took **0.133 s**.

The grep backstop greps `s.root.parent`. For the memory-only global store that parent is
**`$HOME`**. So the floor was `rg`-ing an entire home directory for a phrase that, by construction,
is not indexed in a store that tracks no filesystem paths — hitting the hard 15 s subprocess
timeout, returning **zero hits**, and swallowing the timeout as "no match". Almost none of it was
CPU, which is exactly the signature bug-033 recorded (2.8 s of 8.5 s).

Fixed (logged as bug-040): the backstop is skipped for a memory-only store, and a timeout is
printed instead of swallowed. Measured after: **15.13 s -> 0.09 s**.

## Finding 2: the LongMemEval 8.5 s is cold I/O on an SD card {#cold-io}

| run | total | `replica-build_context` |
|---|---|---|
| first invocation after idle | **8.75 s** | 8.72 s |
| immediately after | **0.72 s** | 0.69 s |
| again | 0.71 s | 0.67 s |

(The first row was taken before the label fix, where the same interval printed under the
neighbouring name; the interval itself is the one reported here.)

The store lives on `/Volumes/littlebig` — `diskutil`: **Protocol: Secure Digital**. Measured
sequential read on that volume: **94.7 MB/s** (400 MB via `dd`, 4.43 s).

`.refmatrix/adjacency.cache.npz` is **432 MB**. At 94.7 MB/s that is **4.6 s of pure I/O**, against
**0.09 s** to `np.load` + materialize the same file warm. Add cold DuckDB pages from a 2.4 GB
catalog slot on the same card and the ~8.5 s first-touch is accounted for, with the CPU share small
— matching the "only 2.8 s is CPU" in the original row.

So the gap is **first-touch I/O against an SD-hosted 9.5 GB store**, not a defect in the retrieval
path, and not the CLI's own startup: warm, the whole command is 0.71 s of which 0.67 s is
`build_context` — consistent with the 0.45 s profiled core plus store binding.

## What would change the reading {#caveats}

- One cold observation per store state; the cold case cannot be re-run on demand without evicting
  the page cache, so the 8.75 s figure is **one measurement plus arithmetic that fits it**, not a
  repeated mean.
- A store on internal NVMe would not show this, which is the practical advice: benchmark stores do
  not belong on removable media if first-touch latency is being measured.
