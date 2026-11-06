"""Agent tool-choice benchmark: headless Claude Code with vs without find-tool.

All stages share one prompt (find the best installed tool for the task, end with `TOOL: <name>`, never perform it).

Published design (single lookup):
  base     no tools: the model names the tool from its own knowledge
  lookup   only `find-tool "<text>"` may run (a hook denies every other command); if nothing fits, the agent
           rephrases once, then falls back to its own knowledge
Exploration stages (agent may search the machine with read-only commands; see bench/README.md for the caveats):
  control    Bash, read-only probes only
  controlsk  control + the Skill tool with Claude Code's built-in skills: token parity with `skill`
  skill      Bash + find-tool on PATH + the find-tool skill (`--plugin DIR`, default plugin/)
  forced     like skill, but the prompt says to run find-tool first
Non-base stages run on all tasks with `--on all`, or on base misses/hits (`--on misses|hits`).

Isolation: API-key auth, empty HOME and CLAUDE_CONFIG_DIR, `--setting-sources local`, `--strict-mcp-config`, and an
empty git repo as the working directory, so no user/ancestor CLAUDE.md, hooks, plugins, MCP or repo status leak.
`--permission-mode dontAsk` denies anything not allowed; denials are recorded per run. allow_loops.py (a PreToolUse
hook) approves read-only probes that allow rules can't express, and in the lookup stage allows only find-tool.
Scored a hit if an acceptable tool is a command word of the final TOOL line; judge.py checks other answers blindly.

Output: bench/runs/<tag>/<stage><suffix>.jsonl (+ raw stream-json per task in bench/runs/<tag>/<stage><suffix>/<n>.jsonl)

Usage (load ANTHROPIC_API_KEY from bench/.env, MOSS_PROJECT_ID/KEY from .env):
  python3 bench/agent_run.py base   --tag haiku-mine --model claude-haiku-5-5 --tasks mine.tsv --on all --suffix=-r1
  python3 bench/agent_run.py lookup --tag haiku-mine --model claude-haiku-5-5 --tasks mine.tsv --on all --suffix=-r1
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from alfa_cases import command_words

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = HERE / "runs"
CWD = RUNS / "cwd"  # empty git repo the agent works in
HOME = RUNS / "home-empty"
PROMPT = """Task: {task}

Find the best command-line tool on this macOS machine for this task. Prefer a tool built for the task; use a
general-purpose tool only if no specific tool is installed. Prefer a simple command over chained pipelines or inline
scripts (perl -e, python -c).
{how}
End your reply with exactly one line:
TOOL: <name>"""
INSPECT = (
    "If you don't know an installed tool for this, search this machine for it. "
    "You may run read-only commands, but do not perform the task itself."
)
HOW = {
    "base": "Answer from your own knowledge.",
    "control": INSPECT,
    "controlsk": INSPECT,  # control + Skill tool (built-in skills), no find-tool: cost parity for `skill`
    "skill": INSPECT,
    "forced": 'First run find-tool "<what you want to do>" to see which installed tools fit. '
    + INSPECT,
    # Single-lookup design: the only command is find-tool (enforced by a hook); compare against `base`.
    "lookup": 'You can run `find-tool "<what you want to do>"` in Bash: it lists the tools installed on this machine '
    "that best match. No other commands are available. If nothing fits, rephrase once, then fall back to your own "
    "knowledge. Do not perform the task itself.",
}
# Read-only probes agents use, beyond Claude Code's built-in read-only set (ls, cat, echo, head, grep, which, ...).
# Every part of a compound command must be allowed. Narrow rules only: a generic `* --version` would also match
# `rm -rf x --version`.
ALLOW = [
    "Bash(man *)",
    "Bash(which *)",
    "Bash(apropos *)",
    "Bash(whatis *)",
    "Bash(ls *)",
    "Bash(command -v *)",
    "Bash(type *)",
    "Bash(printf *)",
    "Bash(echo *)",
    "Bash(col *)",
    "Bash(file *)",
    "Bash(mdfind *)",
    "Bash(brew list *)",
    "Bash(brew info *)",
    "Bash(brew desc *)",
]


def read_dirs() -> list[str]:
    """Install locations agents search: $PATH dirs, their parents (/opt/homebrew, ~/.local) and /Applications.

    Reads outside the working directory are denied even for allowed commands (`ls /usr/bin/x`), so these are added
    as working directories; writes there still match no allow rule. Never /, $HOME or this repo (answer files).
    """
    home, out = Path.home(), []
    for d in os.environ["PATH"].split(":") + ["/Applications"]:
        for p in (Path(d), Path(d).parent):
            if p.is_dir() and p not in (Path("/"), home) and ROOT not in (p, *p.parents) and p not in ROOT.parents:
                out.append(str(p))
    return list(dict.fromkeys(out))


READ_DIRS = read_dirs()
def hook_settings(*args: str) -> str:
    cmd = " ".join(shlex.quote(a) for a in ("python3", str(HERE / "allow_loops.py"), *args))
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd, "timeout": 10}]}]}})


LOOKUP_HOOKS = hook_settings("--only-find-tool")
HOOKS = json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
    {"type": "command", "command": f"python3 {shlex.quote(str(HERE / 'allow_loops.py'))}", "timeout": 10}]}]}})
LEAK = re.compile(
    r"eval-set|unfamiliar|label|alfa|tldr|bench|\.\./"
)  # answer-key paths an agent must not touch


def used_commands(cmd: str) -> set[str]:
    """Command words, including those inside `$(...)` even when quoted (e.g. eval "$(ssh-agent -s)")."""
    words = command_words(cmd) or set()
    for inner in re.findall(r"\$\(([^()]*)\)", cmd):
        words |= command_words(inner) or set()
    return words


def claude_cmd(
    prompt: str, stage: str, model: str, plugin: Path, budget: float
) -> tuple[list[str], dict[str, str]]:
    """The isolated `claude -p` command line and environment for a stage."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("MOSS_")}
    env |= {"HOME": str(HOME), "CLAUDE_CONFIG_DIR": str(HOME / ".claude")}
    cmd = [
        "claude",
        "-p",
        prompt,
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
        "--settings",
        LOOKUP_HOOKS if stage == "lookup" else HOOKS,  # probe stages: approve read-only probes allow rules can't cover
        "--add-dir",
        *READ_DIRS,
    ]
    if stage == "base":
        cmd += ["--tools", ""]
    elif stage == "control":
        cmd += ["--tools", "Bash", "--allowedTools", *ALLOW]
    elif stage == "lookup":
        cmd += ["--tools", "Bash", "--allowedTools", "Bash(find-tool *)"]
        env |= {k: v for k, v in os.environ.items() if k.startswith("MOSS_")}
        env["PATH"] = f"{ROOT}:{env['PATH']}"
    elif stage == "controlsk":
        cmd += ["--tools", "Bash,Skill", "--allowedTools", *ALLOW]
    else:
        cmd += [
            "--tools",
            "Bash,Skill",
            "--plugin-dir",
            str(plugin),
            "--allowedTools",
            *ALLOW,
            "Bash(find-tool:*)",
        ]
        env |= {k: v for k, v in os.environ.items() if k.startswith("MOSS_")}
        env["PATH"] = f"{ROOT}:{env['PATH']}"
    return cmd, env


def run(
    task: str, stage: str, raw_dir: Path, n: int, model: str, plugin: Path, budget: float
) -> dict:
    prompt = PROMPT.format(task=task, how=HOW[stage])
    cmd, env = claude_cmd(prompt, stage, model, plugin, budget)
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
            ln.split("TOOL:", 1)[1].strip().strip("`*")
            for ln in reversed(text.splitlines())
            if "TOOL:" in ln
        ),
        "",
    )
    return {
        "n": n,
        "stage": stage,
        "task": task,
        "tool": final,
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
        "--plugin",
        type=Path,
        default=ROOT / "plugin",
        help="skill plugin dir (skill/forced stages); point at a copy to test other wording",
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
    if args.stage == "base" or args.on == "all":
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
                    args.plugin.resolve(),
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
                "hit": bool(want & used_commands(r["tool"])),
                "plugin": str(args.plugin),
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
