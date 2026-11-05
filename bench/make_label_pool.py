"""Build the blind labeling pool from the filtered benchmark tasks.

Inputs (from tldr_cases.py / alfa_cases.py): tldr-cases.tsv, alfa-test.tsv, alfa-train.tsv
Outputs:
  label-tasks.jsonl  {"id", "task"}                          -> give ONLY this to the labelers (no answers)
  label-key.jsonl    {"id", "source", "task", "reference"}   -> dataset reference tools, used by merge_labels.py

Usage: python3 bench/make_label_pool.py [--train-sample 150] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(name: str) -> list[list[str]]:
    return [
        ln.split("\t") for ln in (HERE / name).read_text().splitlines() if ln.strip()
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-sample", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    train = rows("alfa-train.tsv")
    random.Random(args.seed).shuffle(train)
    sources = [
        ("alfa-test", rows("alfa-test.tsv")),
        ("tldr", rows("tldr-cases.tsv")),
        ("alfa-train", train[: args.train_sample]),
    ]
    with (
        (HERE / "label-tasks.jsonl").open("w") as tasks,
        (HERE / "label-key.jsonl").open("w") as key,
    ):
        for src, rs in sources:
            for i, (nl, ref) in enumerate(rs):
                tid = f"{src}-{i}"
                tasks.write(json.dumps({"id": tid, "task": nl}) + "\n")
                key.write(
                    json.dumps(
                        {
                            "id": tid,
                            "source": src,
                            "task": nl,
                            "reference": ref.split(","),
                        }
                    )
                    + "\n"
                )
    print(f"{sum(len(rs) for _, rs in sources)} tasks")


if __name__ == "__main__":
    main()
