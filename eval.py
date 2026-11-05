"""Compare `apropos` vs `moss query` at finding the right tool for each intent in queries.tsv.

Usage: python3 eval.py            # apropos baseline only
       python3 eval.py --moss     # also query the Moss `tools` index (needs MOSS_PROJECT_ID/KEY)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STOP = set(
    "a an and the to of from in on into out for by with without my me i it is are as or what how while".split()
)
K = 5


def apropos(query: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP]
    out = subprocess.run(["apropos", *words], capture_output=True, text=True).stdout
    names = []  # unranked union of matches; keep commands (sections 1, 8) only
    for ln in out.splitlines():
        for name, sect in re.findall(r"([\w.+-]+)\(([18])\)", ln.split(" - ")[0]):
            if name not in names:
                names.append(name)
    return names


def moss(query: str, model_index: str, alpha: float) -> tuple[list[str], float]:
    cmd = ["moss", "--json", "query", model_index, query, "-k", str(K), "--alpha", str(alpha)]
    t = time.perf_counter()
    for attempt in range(3):  # transient failures seen (exit 1) on long runs
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0:
            break
        print(f"  [moss failed, attempt {attempt + 1}: {p.stderr.strip()[:200] or p.stdout.strip()[:200]}]", file=sys.stderr)
    p.check_returncode()
    return [d["metadata"]["name"] for d in json.loads(p.stdout)["docs"]], time.perf_counter() - t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moss", action="store_true")
    ap.add_argument("--queries", type=Path, default=Path(__file__).with_name("queries.tsv"), help="intent<TAB>tool[,tool] file")
    ap.add_argument("--index", default=os.environ.get("FIND_TOOL_INDEX", "find-tool"))
    ap.add_argument("--alpha", type=float, default=0.8, help="semantic weight (CLI default 0.8)")
    ap.add_argument("--workers", type=int, default=4, help="queries run in parallel")
    args = ap.parse_args()
    rows = [
        ln.split("\t")
        for ln in args.queries.read_text().splitlines()
        if ln.strip()
    ]
    def one(row: list[str]) -> tuple[list[str], list[str], float]:
        a = apropos(row[0])
        names, secs = moss(row[0], args.index, args.alpha) if args.moss else ([], 0.0)
        return a, names, secs

    a_hits = m_hits = 0
    a_sizes, lat = [], []
    # Each query is an independent CLI process (index reload ~2s), so run several at once; output keeps input order.
    with ThreadPoolExecutor(args.workers) as pool:
        for (query, expected), (a, names, secs) in zip(rows, pool.map(one, rows)):
            want = set(expected.split(","))
            a_hit = bool(want & set(a))
            a_hits += a_hit
            a_sizes.append(len(a))
            line = f"{'Y' if a_hit else '-'} apropos({len(a):3})"
            if args.moss:
                rank = next((i for i, n in enumerate(names, 1) if n in want), 0)
                m_hits += bool(rank)
                lat.append(secs)
                line += f"  {'Y' if rank else '-'} moss@{rank or '-'} {secs:4.1f}s {','.join(names)}"
            print(f"{line}  | {query} -> {expected}")
    n = len(rows)
    print(
        f"\napropos: found anywhere {a_hits}/{n}, median results to scan {sorted(a_sizes)[n // 2]}"
    )
    if args.moss:
        print(
            f"moss:    hit@{K} {m_hits}/{n}, median latency {sorted(lat)[n // 2]:.2f}s"
        )


if __name__ == "__main__":
    main()
