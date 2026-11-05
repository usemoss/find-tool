"""Filter NL2SH-ALFA to tasks that test *finding* a tool: runnable here, needing a non-everyday command not named in the task.

A task's commands are the command words of its reference command(s) (`bash`, plus `bash2` in the test split).
Keep a task when, for at least one reference command:
  - every command word is installed on this machine ($PATH or shell builtin), and
  - it uses at least one "key" tool (a command word not in COMMON or WELL_KNOWN), and
  - no key tool is named in the task text.
Drop the task if any runnable reference command needs only everyday tools (an easy solution exists).
Acceptable answers = key tools of every reference command that passes.

Usage: python3 bench/alfa_cases.py {test,train} [--stats] > bench/alfa-<split>.tsv   (intent<TAB>tool[,tool])
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shlex
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).parent / "data" / "nl2sh-alfa"
# Everyday commands any model already knows; a task needing only these doesn't test tool finding.
COMMON = set(
    """
ls cd pwd cat echo printf head tail grep egrep fgrep find sort uniq wc cut tr sed awk xargs cp mv rm mkdir rmdir
touch chmod chown ln du df ps kill killall date sleep which whoami id env export true false test expr basename dirname
tee diff cmp file stat less more read set unset source alias history clear exit seq yes rev nl paste join split
comm tac tar gzip gunzip zcat time nohup sudo bash sh zsh exec eval for while if do done then fi else in case esac
uname hostname whereis type command mount umount top free uptime w who last
""".split()
)
# Famous developer tools: a model reaches for these unprompted, so they don't test finding either.
WELL_KNOWN = set(
    """
git curl wget ssh scp sftp rsync docker npm npx node python python3 pip pip3 make man ping zip unzip perl ruby brew
go java javac gcc g++ cc clang vim vi nano emacs openssl
""".split()
)
# Shell keywords after which the next word is a command again.
RESTART = {"do", "then", "else", "!", "{"}
WRAPPERS = {"sudo", "time", "nohup", "env", "xargs", "exec", "command", "nice"}
BUILTINS = {
    "cd",
    "export",
    "read",
    "set",
    "unset",
    "source",
    "alias",
    "history",
    "exit",
    "for",
    "while",
    "if",
    "do",
    "done",
    "then",
    "fi",
    "else",
    "in",
    "case",
    "esac",
    "eval",
    "exec",
    "type",
    "command",
    "test",
    "true",
    "false",
}
SEPARATORS = {"|", "||", "&&", ";", "&", "(", ")", "$(", "`", "|&"}


def command_words(cmd: str) -> set[str] | None:
    """Command names used in a shell command (first word of each pipeline/list segment, through wrappers)."""
    cmd = cmd.replace("$(", " ( ").replace("`", " ( ")
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:  # unbalanced quotes
        return None
    words, start = set(), True
    for i, t in enumerate(toks):
        if t in SEPARATORS or t == "-exec" or t == "-execdir":
            start = True
            continue
        if not start:
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t) or (
            t.startswith("-") and toks[i - 1] in WRAPPERS
        ):
            continue  # VAR=val prefix, or a wrapper's flag
        name = os.path.basename(t)
        if not re.fullmatch(r"[A-Za-z0-9][\w.+-]*", name):
            start = False
            continue
        words.add(name)
        start = name in WRAPPERS or name in RESTART
    return words


def installed() -> set[str]:
    return BUILTINS | {
        n
        for d in os.environ.get("PATH", "").split(":")
        if os.path.isdir(d)
        for n in os.listdir(d)
        if os.access(os.path.join(d, n), os.X_OK)
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["test", "train"])
    ap.add_argument(
        "--stats",
        action="store_true",
        help="print filter funnel and tool counts to stderr",
    )
    args = ap.parse_args()
    have = installed()
    funnel, tools = Counter(), Counter()
    seen = set()
    for r in csv.DictReader((DATA / f"{args.split}.csv").open(newline="")):
        nl = " ".join(r["nl"].split())
        funnel["total"] += 1
        accept: set[str] = set()
        reasons = set()
        for cmd in filter(None, (r.get("bash"), r.get("bash2"))):
            words = command_words(cmd)
            if not words:
                reasons.add("unparsable")
                continue
            if not words <= have:
                reasons.add("not installed")
                continue
            key = words - COMMON - WELL_KNOWN - WRAPPERS - RESTART
            if not key:
                reasons.add("everyday only")
                continue
            if any(re.search(rf"\b{re.escape(k)}\b", nl, re.I) for k in key):
                reasons.add("tool named")
                continue
            accept |= key
        if not accept or "everyday only" in reasons:  # an everyday-only solution exists: too easy
            funnel["drop: " + " / ".join(sorted(reasons))] += 1
            continue
        if nl.lower() in seen:
            funnel["drop: duplicate"] += 1
            continue
        seen.add(nl.lower())
        funnel["kept"] += 1
        tools.update(accept)
        print(f"{nl}\t{','.join(sorted(accept))}")
    if args.stats:
        for k, v in funnel.most_common():
            print(f"{v:6}  {k}", file=sys.stderr)
        print(
            "tools:",
            " ".join(f"{t}({n})" for t, n in tools.most_common(60)),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
