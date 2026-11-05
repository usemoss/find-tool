"""Like-for-like comparison of find-tool (moss) vs apropos on bench/eval-set.tsv.

1. Top-level, deduplicated: moss top-5 *distinct tools* (from a -k 20 query) vs apropos distinct section 1/8 commands.
   Reports hit rate and how many distinct candidates each makes you scan.
2. Lines read to reach the answer (subcommand docs count as lines): moss rank of the first acceptable doc in the
   -k 20 list vs the first acceptable line in apropos's printed output, plus apropos's expected position if its
   output order were random: (N+1)/(m+1) for N printed lines with m matching.

Usage: python3 bench/compare_apropos.py [--index NAME] [--workers 4] > bench/apropos-compare.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval import STOP  # noqa: E402  (same keyword extraction as the main eval)

DEEP, TOP = 20, 5


def apropos_lines(query: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP]
    return subprocess.run(
        ["apropos", *words], capture_output=True, text=True
    ).stdout.splitlines()


def line_names(line: str) -> set[str]:
    """Command names a printed apropos line offers (sections 1 and 8 only)."""
    return {n for n, _ in re.findall(r"([\w.+-]+)\(([18])\)", line.split(" - ")[0])}


def moss_docs(query: str, index: str) -> list[str]:
    cmd = ["moss", "--json", "query", index, query, "-k", str(DEEP)]
    for _ in range(3):
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            return [d["metadata"]["name"] for d in json.loads(p.stdout)["docs"]]
    p.check_returncode()
    return []


def score(row: list[str], index: str) -> dict:
    query, want = row[0], set(row[1].split(","))
    lines, docs = apropos_lines(query), moss_docs(query, index)
    distinct_apropos = list(
        dict.fromkeys(n for ln in lines for n in sorted(line_names(ln)))
    )
    distinct_moss = list(dict.fromkeys(docs))[:TOP]
    hits = [i for i, ln in enumerate(lines, 1) if line_names(ln) & want]
    return {
        "task": query,
        "want": sorted(want),
        "moss_top5_distinct": distinct_moss,
        "moss_hit_distinct": bool(want & set(distinct_moss)),
        "moss_first_rank": next(
            (i for i, n in enumerate(docs, 1) if n in want), 0
        ),  # 0 = not in top 20
        "apropos_distinct": len(distinct_apropos),
        "apropos_hit_distinct": bool(want & set(distinct_apropos)),
        "apropos_lines": len(lines),
        "apropos_first_line": hits[0] if hits else 0,
        "apropos_expected_line": (len(lines) + 1) / (len(hits) + 1) if hits else 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=os.environ.get("FIND_TOOL_INDEX", "find-tool"))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    rows = [
        ln.split("\t")
        for ln in (Path(__file__).parent / "eval-set.tsv").read_text().splitlines()
        if ln.strip()
    ]
    with ThreadPoolExecutor(args.workers) as pool:
        res = list(pool.map(lambda r: score(r, args.index), rows))
    for r in res:
        print(json.dumps(r))
    n = len(res)
    mh = [r for r in res if r["moss_first_rank"]]
    ah = [r for r in res if r["apropos_first_line"]]
    err = sys.stderr
    print(f"index={args.index}  n={n}", file=err)
    print("1. top-level, deduplicated", file=err)
    print(
        f"   moss   : hit {sum(r['moss_hit_distinct'] for r in res)}/{n} scanning {TOP} distinct tools",
        file=err,
    )
    print(
        f"   apropos: hit {sum(r['apropos_hit_distinct'] for r in res)}/{n} scanning median "
        f"{median(r['apropos_distinct'] for r in res):.0f} distinct commands",
        file=err,
    )
    print(
        "2. lines read to the first acceptable answer (hits only; misses listed separately)",
        file=err,
    )
    print(
        f"   moss   : found in top {DEEP} for {len(mh)}/{n}; median rank {median(r['moss_first_rank'] for r in mh):.0f}",
        file=err,
    )
    print(
        f"   apropos: found for {len(ah)}/{n}; median line {median(r['apropos_first_line'] for r in ah):.0f} "
        f"(random-order expectation {median(r['apropos_expected_line'] for r in ah):.0f}) "
        f"of median {median(r['apropos_lines'] for r in res):.0f} lines",
        file=err,
    )


if __name__ == "__main__":
    main()
