"""Agent tool-choice benchmark: headless Claude Code with vs without find-tool.

Stages (all share one prompt shape; the agent must end with `COMMAND: <cmd>` and never perform the task):
  base     NO tools: the model names the command from its own knowledge (run on every task)
  control  Bash, read-only inspection only (no find-tool)
  controlsk  control + the Skill tool with Claude Code's built-in skills (no find-tool): token/cost parity with `skill`
  skill    Bash + find-tool on PATH + the find-tool skill (`--skill v1..v4`, see bench/skill-versions/), neutral prompt
  forced   like skill, but the prompt says to run find-tool first
Non-base stages run on the tasks selected by `--on` from this tag's base results: misses (default), hits, or all.

Isolation (verified): API-key auth, empty HOME and CLAUDE_CONFIG_DIR, `--setting-sources local`, `--strict-mcp-config`,
and an empty git repo as the working directory, so no user/ancestor CLAUDE.md, hooks, plugins, MCP or repo status leak.
State-changing commands are denied by `--permission-mode dontAsk`; read-only ones are auto-allowed.
Scored a hit if any acceptable tool is a command word (also inside `$(...)`) of the final COMMAND line.

Output: bench/runs/<tag>/<stage><suffix>.jsonl (+ raw stream-json per task in bench/runs/<tag>/<stage><suffix>/<n>.jsonl)

Usage (load ANTHROPIC_API_KEY from bench/.env, MOSS_PROJECT_ID/KEY from .env):
  python3 bench/agent_run.py base    --tag sonnet-evalset --model claude-sonnet-5-5 [--tasks eval-set.tsv]
  python3 bench/agent_run.py control --tag sonnet-evalset --model claude-sonnet-5-5
  python3 bench/agent_run.py skill   --tag sonnet-evalset --skill v4 [--on hits --n 26 --suffix=-v4-hits]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from alfa_cases import command_words

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = HERE / "runs"
CWD = RUNS / "cwd"  # empty git repo the agent works in
HOME = RUNS / "home-empty"
PLUGINS = HERE / "skill-versions"  # v1..v4 skill plugins benchmarked against each other
PROMPT = """Task: {task}

Give the single shell command, for this macOS machine, that accomplishes the task, using a tool that is installed here.
{how}
End your reply with exactly one line of the form:
COMMAND: <command>"""
INSPECT = "You may inspect the system with read-only commands but do not perform the task itself."
HOW = {
    "base": "Answer from your own knowledge.",
    "control": INSPECT,
    "controlsk": INSPECT,  # control + Skill tool (built-in skills), no find-tool: cost parity for `skill`
    "skill": INSPECT,
    "forced": 'First run find-tool "<what you want to do>" to see which installed tools fit. '
    + INSPECT,
}
ALLOW = [
    "Bash(man:*)",
    "Bash(which:*)",
    "Bash(apropos:*)",
    "Bash(whatis:*)",
    "Bash(ls:*)",
]
LEAK = re.compile(
    r"eval-set|unfamiliar|label|alfa|tldr|bench|\.\./"
)  # answer-key paths an agent must not touch


def used_commands(cmd: str) -> set[str]:
    """Command words, including those inside `$(...)` even when quoted (e.g. eval "$(ssh-agent -s)")."""
    words = command_words(cmd) or set()
    for inner in re.findall(r"\$\(([^()]*)\)", cmd):
        words |= command_words(inner) or set()
    return words


def run(
    task: str, stage: str, raw_dir: Path, n: int, model: str, skill: str, budget: float
) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("MOSS_")}
    env |= {"HOME": str(HOME), "CLAUDE_CONFIG_DIR": str(HOME / ".claude")}
    cmd = [
        "claude",
        "-p",
        PROMPT.format(task=task, how=HOW[stage]),
        "--model",
        model,
        "--setting-sources",
        "local",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-budget-usd",
        str(budget),
    ]
    if stage == "base":
        cmd += ["--tools", ""]
    elif stage == "control":
        cmd += ["--tools", "Bash", "--allowedTools", *ALLOW]
    elif stage == "controlsk":
        cmd += ["--tools", "Bash,Skill", "--allowedTools", *ALLOW]
    else:
        cmd += [
            "--tools",
            "Bash,Skill",
            "--plugin-dir",
            str(PLUGINS / skill),
            "--allowedTools",
            *ALLOW,
            "Bash(find-tool:*)",
        ]
        env |= {k: v for k, v in os.environ.items() if k.startswith("MOSS_")}
        env["PATH"] = f"{ROOT}:{env['PATH']}"
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=CWD, env=env)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{n}.jsonl").write_text(
        p.stdout + (json.dumps({"stderr": p.stderr}) if p.stderr else "")
    )
    events = [json.loads(ln) for ln in p.stdout.splitlines() if ln.startswith("{")]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    uses = [
        b
        for e in events
        if e.get("type") == "assistant"
        for b in e["message"].get("content", [])
        if b.get("type") == "tool_use"
    ]
    bash = [u["input"].get("command", "") for u in uses if u["name"] == "Bash"]
    usage = result.get("usage") or {}
    text = result.get("result") or ""
    final = next(
        (
            ln.split("COMMAND:", 1)[1].strip().strip("`")
            for ln in reversed(text.splitlines())
            if "COMMAND:" in ln
        ),
        "",
    )
    return {
        "n": n,
        "stage": stage,
        "task": task,
        "command": final,
        "commands_run": bash,
        "skill_loaded": any(
            u["name"] == "Skill" and "find-tool" in json.dumps(u["input"]) for u in uses
        ),
        "find_tool_run": any("find-tool" in c for c in bash),
        "probes": sum(
            not c.lstrip().startswith("find-tool") for c in bash
        ),  # guess/inspect commands
        "leak_suspect": any(LEAK.search(c) for c in bash),
        "denials": len(result.get("permission_denials") or []),
        "input_tokens": sum(
            usage.get(k, 0)
            for k in (
                "input_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            )
        ),
        "output_tokens": usage.get("output_tokens", 0),
        "cost": result.get("total_cost_usd", 0.0),
        "turns": result.get("num_turns", 0),
        "secs": (result.get("duration_ms") or 0) / 1000,
        "error": bool(result.get("is_error", True)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=list(HOW))
    ap.add_argument("--tag", required=True, help="run group, e.g. sonnet-evalset")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument(
        "--tasks", default="eval-set.tsv", help="intent<TAB>tool[,tool] file in bench/"
    )
    ap.add_argument(
        "--skill", default="v4", choices=sorted(p.name for p in PLUGINS.iterdir())
    )
    ap.add_argument(
        "--on",
        default="misses",
        choices=["misses", "hits", "all"],
        help="non-base task selection",
    )
    ap.add_argument("--n", type=int, help="limit to N tasks (random sample, --seed)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--suffix", default="", help="appended to the output name, e.g. -v3-hits"
    )
    ap.add_argument("--budget", type=float, default=0.50, help="max USD per run")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    out_dir = RUNS / args.tag
    rows = [
        ln.split("\t")
        for ln in (HERE / args.tasks).read_text().splitlines()
        if ln.strip()
    ]
    if args.stage == "base":
        todo = list(range(len(rows)))
    else:
        base = [
            json.loads(ln)
            for ln in (out_dir / "base.jsonl").read_text().splitlines()
            if ln.startswith("{")
        ]
        todo = [
            r["n"] for r in base if args.on == "all" or r["hit"] == (args.on == "hits")
        ]
    if args.n is not None and args.n < len(todo):
        todo = sorted(random.Random(args.seed).sample(todo, args.n))
    name = args.stage + args.suffix
    for d in (CWD, HOME / ".claude", out_dir):
        d.mkdir(parents=True, exist_ok=True)
    if not (CWD / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=CWD, check=True)
    with ThreadPoolExecutor(args.workers) as pool:
        res = list(
            pool.map(
                lambda i: run(
                    rows[i][0],
                    args.stage,
                    out_dir / name,
                    i,
                    args.model,
                    args.skill,
                    args.budget,
                ),
                todo,
            )
        )
    with (out_dir / f"{name}.jsonl").open("w") as f:
        for r in res:
            want = set(rows[r["n"]][1].split(","))
            r |= {
                "want": sorted(want),
                "hit": bool(want & used_commands(r["command"])),
                "skill": args.skill,
            }
            f.write(json.dumps(r) + "\n")
    n = len(res)
    s = lambda k: sum(r[k] for r in res)  # noqa: E731
    print(
        f"{args.tag}/{name}: hit {s('hit')}/{n}  cost ${s('cost'):.3f}  in-tok {s('input_tokens')}  "
        f"out-tok {s('output_tokens')}  turns {s('turns')}  probes {s('probes')}  skill {s('skill_loaded')}  "
        f"find-tool {s('find_tool_run')}  errors {s('error')}  leaks {s('leak_suspect')}"
    )


if __name__ == "__main__":
    main()
