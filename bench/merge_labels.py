"""Merge three blind labelers into our find-tool eval set.

Rules (fixed before labels were seen):
1. keep a task only if >=2 of 3 labelers say self_contained
2. acceptable = tools named by >=2 labelers, plus the dataset reference tool if >=1 labeler names it; installed only
3. drop if acceptable is empty
4. drop if acceptable contains an everyday/famous tool (COMMON / WELL_KNOWN): an easy solution exists
5. drop if the task text names an acceptable tool

Usage: python3 bench/merge_labels.py > bench/eval-set.tsv   (stats on stderr)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

from alfa_cases import COMMON, WELL_KNOWN, installed

HERE = Path(__file__).parent
LABELERS = ["sonnet-a", "sonnet-b", "haiku"]


def load(path: Path) -> dict[str, dict]:
    return {r["id"]: r for r in map(json.loads, path.read_text().splitlines()) if r}


def main() -> None:
    key = load(HERE / "label-key.jsonl")
    labs = {n: load(HERE / "data" / "labels" / f"labels-{n}.jsonl") for n in LABELERS}
    have = installed()
    funnel, ref_votes, kept_by_src = Counter(), Counter(), Counter()
    pair_overlap: dict[str, list[float]] = {
        f"{a}~{b}": [] for a, b in combinations(LABELERS, 2)
    }
    sc_agree = Counter()
    for tid, k in key.items():
        votes = [labs[n][tid] for n in LABELERS]
        tool_sets = [{t.strip().lower() for t in v["tools"]} for v in votes]
        for (a, sa), (b, sb) in combinations(zip(LABELERS, tool_sets), 2):
            if sa or sb:
                pair_overlap[f"{a}~{b}"].append(len(sa & sb) / len(sa | sb))
        sc = sum(bool(v["self_contained"]) for v in votes)
        sc_agree[sc] += 1
        refs = set(k["reference"])
        ref_votes[max(sum(r in s for s in tool_sets) for r in refs)] += 1
        if sc < 2:
            funnel["drop: not self-contained"] += 1
            continue
        counts = Counter(t for s in tool_sets for t in s)
        accept = {t for t, c in counts.items() if c >= 2} | {
            r for r in refs if counts[r] >= 1
        }
        accept &= have
        if not accept:
            funnel["drop: no agreed installed tool"] += 1
            continue
        if accept & (COMMON | WELL_KNOWN):
            funnel["drop: easy tool works"] += 1
            continue
        if any(re.search(rf"\b{re.escape(t)}\b", k["task"], re.I) for t in accept):
            funnel["drop: tool named"] += 1
            continue
        funnel["kept"] += 1
        kept_by_src[k["source"]] += 1
        print(f"{k['task']}\t{','.join(sorted(accept))}")
    err = sys.stderr
    print("funnel:", dict(funnel), "| kept by source:", dict(kept_by_src), file=err)
    print("self_contained votes (0-3):", dict(sorted(sc_agree.items())), file=err)
    print(
        "labelers naming the dataset reference tool (0-3):",
        dict(sorted(ref_votes.items())),
        file=err,
    )
    for pair, vals in pair_overlap.items():
        print(f"tool-set Jaccard {pair}: mean {sum(vals) / len(vals):.2f}", file=err)


if __name__ == "__main__":
    main()
