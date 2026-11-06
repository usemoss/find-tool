"""Blind judge for answers that aren't in a task's acceptable-tool list.

For every run record whose TOOL answer missed the label, the judge sees only the task, the answered tool and that
tool's own man/--help text (never the condition, the label, or other answers) and decides whether the tool is built
for the task. The tool must also be installed on this machine (checked deterministically, not by the judge).
Verdicts are cached per (task, tool), so every condition and repeat gets the same verdict.

Usage: python3 bench/judge.py bench/runs/<tag>/*.jsonl [--model claude-sonnet-5-5]
Writes bench/runs/judge-cache.jsonl and prints strict vs judged hits per file.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import agent_run as A

sys.path.insert(0, str(A.ROOT))
import build  # noqa: E402  (same man/--help extraction as the index)

CACHE = A.RUNS / "judge-cache.jsonl"
PROMPT = """You are judging one answer in a benchmark about choosing command-line tools.

Task: {task}
Answered tool: {tool}

Documentation of the answered tool (from its man page and --help on this machine):
<docs>
{docs}
</docs>

Is "{tool}" a tool built for this kind of task, so that a simple command with it accomplishes the task? Answer "no"
if it would need inline scripting (perl -e, python -c, awk programs), a long pipeline, or if it is a general-purpose
tool that merely can be bent to the task. Judge from the documentation and your general knowledge.

End with exactly one line: VERDICT: yes  or  VERDICT: no"""


def tool_name(answer: str) -> str:
    words = A.used_commands(answer)
    first = answer.split()[0] if answer.split() else ""
    return first if first in words else (sorted(words)[0] if words else first)


def docs(name: str, path: str, sandbox: str) -> str:
    return (
        build.squash(f"{build.man_text(name)}\n{build.help_text(path, sandbox)}")[:3000]
        or "(no documentation found)"
    )


def judge(task: str, name: str, model: str, sandbox: str) -> dict:
    path = shutil.which(name)
    if not path:
        return {
            "task": task,
            "tool": name,
            "installed": False,
            "valid": False,
            "reason": "not installed",
        }
    prompt = PROMPT.format(task=task, tool=name, docs=docs(name, path, sandbox))
    cmd, env = A.claude_cmd(prompt, "base", model, A.ROOT / "plugin", 0.5)
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=A.CWD, env=env)
    events = [json.loads(ln) for ln in p.stdout.splitlines() if ln.startswith("{")]
    res = next((e for e in reversed(events) if e.get("type") == "result"), {})
    text = res.get("result") or ""
    verdict = next(
        (
            ln.split(":", 1)[1].strip().lower()
            for ln in reversed(text.splitlines())
            if "VERDICT:" in ln
        ),
        "",
    )
    return {
        "task": task,
        "tool": name,
        "installed": True,
        "valid": verdict.startswith("yes"),
        "reason": text.strip()[-400:],
        "cost": res.get("total_cost_usd", 0.0),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    cache = (
        {
            (r["task"], r["tool"]): r
            for r in map(json.loads, CACHE.read_text().splitlines())
        }
        if CACHE.exists()
        else {}
    )
    runs = {
        f: [json.loads(ln) for ln in f.read_text().splitlines() if ln.startswith("{")]
        for f in args.files
    }
    todo = sorted(
        {
            (r["task"], tool_name(r["tool"]))
            for rs in runs.values()
            for r in rs
            if not r["hit"] and r["tool"].strip()
        }
        - set(cache)
    )
    print(f"judging {len(todo)} new (task, tool) pairs", file=sys.stderr)
    sandbox = tempfile.mkdtemp(prefix="find-tool-judge-")
    with ThreadPoolExecutor(args.workers) as pool:
        for v in pool.map(lambda tt: judge(*tt, args.model, sandbox), todo):
            cache[(v["task"], v["tool"])] = v
            with CACHE.open("a") as f:
                f.write(json.dumps(v) + "\n")
    for f, rs in runs.items():
        judged = sum(
            r["hit"]
            or cache.get((r["task"], tool_name(r["tool"])), {}).get("valid", False)
            for r in rs
        )
        print(
            f"{f}: strict {sum(r['hit'] for r in rs)}/{len(rs)}  judged {judged}/{len(rs)}"
        )


if __name__ == "__main__":
    main()
