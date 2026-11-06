"""Control vs find-tool over repeated runs, scored with judge verdicts (bench/judge.py).

H1 (accuracy): per task, correct in the majority of repeats; exact McNemar test on tasks where the conditions differ.
H2 (tokens): over (task, repeat) pairs where both conditions are correct, the per-task mean difference in total
tokens (input incl. cached + output); reported as the median across tasks, plus dollars and turns.

Usage: python3 bench/compare_runs.py --tag haiku-v5-evalset [--control controlsk --treatment skill --repeats 3]
"""

from __future__ import annotations

import argparse
import json
from math import comb
from statistics import mean, median

import agent_run as A
from judge import CACHE, tool_name


def load(tag: str, stage: str, r: int) -> dict[int, dict]:
    f = A.RUNS / tag / f"{stage}-r{r}.jsonl"
    return {x["n"]: x for x in map(json.loads, f.read_text().splitlines()) if x}


def mcnemar(b: int, c: int) -> float:
    n, k = b + c, min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--control", default="controlsk")
    ap.add_argument("--treatment", default="skill")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument(
        "--tasks",
        help="rescore against this task file's current labels (file in bench/)",
    )
    a = ap.parse_args()
    cache = (
        {
            (v["task"], v["tool"]): v["valid"]
            for v in map(json.loads, CACHE.read_text().splitlines())
        }
        if CACHE.exists()
        else {}
    )
    labels = {}
    if a.tasks:  # labels may have been corrected after the runs; rescore both conditions the same way
        rows = (
            ln.split("\t")
            for ln in (A.HERE / a.tasks).read_text().splitlines()
            if ln.strip()
        )
        labels = {task: set(want.split(",")) for task, want in rows}

    def hit(x: dict) -> bool:
        return (
            bool(labels[x["task"]] & A.used_commands(x["tool"])) if labels else x["hit"]
        )

    def ok(x: dict) -> bool:
        return hit(x) or cache.get((x["task"], tool_name(x["tool"])), False)

    R = range(1, a.repeats + 1)
    runs = {s: [load(a.tag, s, r) for r in R] for s in (a.control, a.treatment)}
    # Tasks removed from the file since the runs are dropped from every condition.
    if labels:
        runs = {
            s: [{n: x for n, x in rr.items() if x["task"] in labels} for rr in rs]
            for s, rs in runs.items()
        }
    tasks = sorted(runs[a.control][0])
    unjudged = sum(
        1
        for s in runs
        for rr in runs[s]
        for x in rr.values()
        if not x["hit"]
        and x["tool"].strip()
        and (x["task"], tool_name(x["tool"])) not in cache
    )
    print(
        f"{a.tag}: {len(tasks)} tasks x {a.repeats} repeats  (unjudged misses: {unjudged})"
    )
    for s in runs:
        allr = [x for rr in runs[s] for x in rr.values()]
        print(
            f"  {s:10} correct runs {sum(map(ok, allr))}/{len(allr)} (strict {sum(map(hit, allr))})  "
            f"tokens/run {mean(x['input_tokens'] + x['output_tokens'] for x in allr):,.0f}  "
            f"$/run {mean(x['cost'] for x in allr):.5f}  turns/run {mean(x['turns'] for x in allr):.2f}  "
            f"denials {sum(x['denials'] for x in allr)}  find-tool runs {sum(x['find_tool_run'] for x in allr)}"
        )
    maj = {
        s: {n: sum(ok(rr[n]) for rr in runs[s]) * 2 > a.repeats for n in tasks}
        for s in runs
    }
    b = sum(maj[a.treatment][n] and not maj[a.control][n] for n in tasks)
    c = sum(maj[a.control][n] and not maj[a.treatment][n] for n in tasks)
    print(
        f"  H1 majority-correct tasks: {a.control} {sum(maj[a.control].values())}, {a.treatment} "
        f"{sum(maj[a.treatment].values())}; only {a.treatment} {b}, only {a.control} {c}, McNemar p={mcnemar(b, c):.4f}"
    )
    dt, dd, du = [], [], []
    for n in tasks:
        pairs = [
            (runs[a.control][i][n], runs[a.treatment][i][n]) for i in range(a.repeats)
        ]
        both = [(x, y) for x, y in pairs if ok(x) and ok(y)]
        if both:
            dt.append(
                mean(
                    (y["input_tokens"] + y["output_tokens"])
                    - (x["input_tokens"] + x["output_tokens"])
                    for x, y in both
                )
            )
            dd.append(mean(y["cost"] - x["cost"] for x, y in both))
            du.append(mean(y["turns"] - x["turns"] for x, y in both))
    if dt:
        print(
            f"  H2 both-correct ({len(dt)} tasks): median tokens/task {median(dt):+,.0f} (mean {mean(dt):+,.0f}); "
            f"fewer tokens in {sum(d < 0 for d in dt)}, more in {sum(d > 0 for d in dt)}; "
            f"$/task {mean(dd):+.5f}; turns/task {mean(du):+.2f}"
        )


if __name__ == "__main__":
    main()
