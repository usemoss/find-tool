"""Emit Moss documents (JSON array on stdout) for every CLI on $PATH and every installed agent skill.

Usage: python3 build.py [--limit N] [--log FILE] [--skip FILE] > docs.json
(`find-tool --init` / `--add-new` run this and load the result into Moss.)
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOME = Path.home()
MAX_CHARS = (
    1000  # ponytail: fixed trim; tune once the embedding model's input limit is known
)
# Only binaries from these dirs get `--help` run on them; system dirs are never executed.
USER_DIRS = (
    "/opt/homebrew/",
    "/usr/local/",
    f"{HOME}/.local/",
    f"{HOME}/.cargo/",
    f"{HOME}/go/",
)
# Benchmarks/test harnesses may ignore `--help` and start work; don't execute them.
SKIP_HELP = re.compile(r"bench|test|fate|trasher", re.I)
SKILL_ROOTS = {
    "claude": HOME / ".claude",
    "codex": HOME / ".codex",
    "agents": HOME / ".agents",
}


def run(cmd: list[str], timeout: float = 5) -> str:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return p.stdout if p.returncode == 0 else ""


def path_executables() -> dict[str, str]:
    """name -> first path on $PATH (shell resolution order)."""
    found: dict[str, str] = {}
    for d in os.environ.get("PATH", "").split(":"):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if (
                name not in found
                and not name.startswith(".")
                and os.path.isfile(p)
                and os.access(p, os.X_OK)
            ):
                found[name] = p
    return found


def man_text(name: str) -> str:
    if not run(["man", "-w", name]):
        return ""
    page = run(["sh", "-c", 'man "$1" 2>/dev/null | col -b', "_", name], timeout=10)
    whatis = next((ln for ln in page.splitlines() if " - " in ln or " – " in ln), "")
    m = re.search(r"^DESCRIPTION\s*$(.*?)(?=^[A-Z][A-Z ]+\s*$)", page, re.M | re.S)
    desc = m.group(1) if m else ""
    return f"{whatis.strip()}\n{desc}".strip()


EXECUTED: list[str] = []  # audit trail of every binary run with --help


def help_text(path: str, sandbox: str, *sub: str) -> str:
    """`<tool> [sub] --help` output (stdout+stderr, any exit code; many tools print usage to stderr).

    Runs in an empty scratch cwd: some tools (e.g. ffmpeg's test utilities) treat
    `--help` as a file path, so any file they create lands in the sandbox.
    """
    if not path.startswith(USER_DIRS) or SKIP_HELP.search(os.path.basename(path)):
        return ""
    EXECUTED.append(" ".join([path, *sub, "--help"]))
    try:
        p = subprocess.run(
            [path, *sub, "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
            errors="replace",
            cwd=sandbox,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return p.stdout + p.stderr


# "  codespace:     Connect to and manage codespaces" / "  delete   Delete resources by ..." in a help's command list
SUBCOMMAND = re.compile(
    r"^ {2,}([a-z][a-z0-9-]*)[:*]?(?:,\s*[a-z-]+)? {2,}([A-Z].{8,})$", re.M
)
MAX_SUBS, MAX_CHUNKS, CHUNK = 60, 3, 1200


# A help section heading that introduces a command list: "CORE COMMANDS", "Commands:", "Basic Commands (Beginner):"
COMMANDS_HEADING = re.compile(r"^\S.*\bcommands?\b.*$", re.I | re.M)


def subcommands(help_out: str) -> list[tuple[str, str]]:
    """Subcommands listed under a "...commands..." heading (avoids option values and positionals)."""
    m = COMMANDS_HEADING.search(help_out)
    if not m:
        return []
    seen, out = set(), []
    for sub, desc in SUBCOMMAND.findall(help_out[m.start() :]):
        if sub not in seen and sub not in {"help", "completion", "version"}:
            seen.add(sub)
            out.append((sub, desc.strip()))
    return out[:MAX_SUBS]


def chunks(text: str) -> list[str]:
    """Up to MAX_CHUNKS ~CHUNK-char pieces with 200-char overlap (Moss chunking guidance)."""
    text = re.sub(r"\s+", " ", text).strip()
    return [text[i : i + CHUNK] for i in range(0, max(len(text), 1), CHUNK - 200)][
        :MAX_CHUNKS
    ]


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:MAX_CHARS]


def frontmatter(md: Path) -> dict[str, str]:
    """Minimal YAML frontmatter reader: `key: value` plus folded/literal (`>`/`|`) blocks."""
    lines = md.read_text(errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    key = ""
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", ln)
        if m:
            key, val = m.group(1), m.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val.strip("\"'")
        elif key and ln.startswith((" ", "\t")):
            out[key] += " " + ln.strip()
    return out


@functools.cache
def brew_descs() -> dict[str, str]:
    """Homebrew formula -> one-line description (installed formulae only; empty if brew is absent)."""
    out = run(["brew", "info", "--json=v2", "--installed"], timeout=60)
    return (
        {f["name"]: f["desc"] or "" for f in json.loads(out)["formulae"]} if out else {}
    )


def package_desc(path: str) -> str:
    """Purpose-style summary from the package manager that installed the binary (brew or uv tool)."""
    real = os.path.realpath(path)
    if m := re.search(r"/Cellar/([^/]+)/", real):
        return brew_descs().get(m.group(1), "")
    if m := re.search(r"/uv/tools/([^/]+)/", real):
        dist = m.group(1).replace("-", "_").lower()
        for meta in Path(real.split("/bin/")[0]).glob(
            "lib/python*/site-packages/*.dist-info/METADATA"
        ):
            if meta.parent.name.lower().startswith(dist + "-"):
                return next(
                    (
                        ln[9:]
                        for ln in meta.read_text(errors="replace").splitlines()
                        if ln.startswith("Summary: ")
                    ),
                    "",
                )
    return ""


def cli_doc(name: str, path: str, sandbox: str) -> list[dict]:
    man, help_out = man_text(name), help_text(path, sandbox)
    source = "+".join(k for k, v in (("man", man), ("help", help_out)) if v) or "name"
    head = f"{name}: {desc}." if (desc := package_desc(path)) else f"{name}:"
    meta = {"kind": "cli", "name": name, "path": path, "source": source}
    docs = [
        {
            "id": f"cli:{name}" + (f"#{i}" if i else ""),
            "text": f"{head} {c}".strip(),
            "metadata": meta,
        }
        for i, c in enumerate(chunks(f"{man}\n{help_out}"))
    ]
    for sub, line in subcommands(help_out):
        detail = squash(help_text(path, sandbox, sub))
        docs.append(
            {
                "id": f"cli:{name}:{sub}",
                "text": squash(f"{name} {sub}: {line}. {detail}"),
                "metadata": {**meta, "source": "subcommand", "sub": sub},
            }
        )
    return docs


def cli_docs(
    limit: int | None, workers: int, skip: set[str] = frozenset()
) -> list[dict]:
    exes = [e for e in path_executables().items() if e[0] not in skip][:limit]
    sandbox = tempfile.mkdtemp(prefix="find-tool-help-")
    docs = []
    # Each tool is a short-lived man/--help subprocess, so threads are enough.
    with ThreadPoolExecutor(workers) as pool:
        for i, tool_docs in enumerate(
            pool.map(lambda e: cli_doc(*e, sandbox), exes), 1
        ):
            print(f"\r[cli {i}/{len(exes)}]", end="", file=sys.stderr)
            docs.extend(tool_docs)
    print(
        f"\n--help sandbox: {sandbox} ({len(os.listdir(sandbox))} stray files)",
        file=sys.stderr,
    )
    return docs


def skill_docs() -> list[dict]:
    docs, seen = [], set()
    for harness, root in SKILL_ROOTS.items():
        for md in sorted(root.rglob("SKILL.md")):
            if "/.tmp/" in str(md):  # uninstalled plugin catalogue (codex)
                continue
            fm = frontmatter(md)
            name = fm.get("name") or md.parent.name
            if (harness, name) in seen or not fm.get("description"):
                continue
            seen.add((harness, name))
            docs.append(
                {
                    "id": f"skill:{harness}:{name}",
                    "text": squash(f"{name}: {fm['description']}"),
                    "metadata": {
                        "kind": "skill",
                        "name": name,
                        "harness": harness,
                        "path": str(md),
                    },
                }
            )
    return docs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N CLIs (dry runs)")
    ap.add_argument(
        "--workers", type=int, default=8, help="parallel man/--help lookups"
    )
    ap.add_argument(
        "--log", type=Path, help="write every executed `--help` command line here"
    )
    ap.add_argument(
        "--skip",
        type=Path,
        help="file of CLI names to leave out (one per line; e.g. already indexed)",
    )
    args = ap.parse_args()
    skip = set(args.skip.read_text().split()) if args.skip else set()
    docs = cli_docs(args.limit, args.workers, skip) + skill_docs()
    if args.log:
        args.log.write_text("\n".join(sorted(EXECUTED)) + "\n")
    json.dump(docs, sys.stdout)
    print(f"{len(docs)} docs", file=sys.stderr)
