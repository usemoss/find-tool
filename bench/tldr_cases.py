"""Filter the DocPrompting tldr test split to tasks whose reference tool is installed here and not named in the task.

Usage: python3 bench/tldr_cases.py > bench/tldr-cases.tsv   (intent<TAB>tool, the format eval.py reads)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

DATA = Path(__file__).parent / "data" / "tldr" / "tldr-test.jsonl"


def installed() -> set[str]:
    return {n for d in os.environ.get("PATH", "").split(":") if os.path.isdir(d)
            for n in os.listdir(d) if os.access(os.path.join(d, n), os.X_OK)}


if __name__ == "__main__":
    have = installed()
    for line in DATA.open():
        r = json.loads(line)
        tool, nl = r["cmd_name"], " ".join(r["nl"].split())
        if tool in have and not re.search(rf"\b{re.escape(tool)}\b", nl, re.I):
            print(f"{nl}\t{tool}")
