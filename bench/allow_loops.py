"""PreToolUse hook: approve Bash commands made only of read-only probes.

Claude Code's allow rules never cover a loop body, a `$(...)` or a tool's own `--help`, so in dontAsk mode such
probes are denied and the agent answers without the information. This hook approves a command when every part of it
is a read-only probe: lookup commands (`command -v`, `which`, `type`, `ls`, `man`, ...), `<tool> [sub] --help` /
`--version` with no other arguments, `$(command -v NAME)`, and loops over those. Output may only go to /dev/null or
another descriptor. For anything else it stays silent, so the normal permission rules decide (deny rules always win).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

READ_ONLY = {
    "echo",
    "printf",
    "type",
    "which",
    "ls",
    "man",
    "apropos",
    "whatis",
    "head",
    "tail",
    "grep",
    "col",
    "file",
    "mdfind",
    "wc",
    "true",
    "test",
    "[",
    "basename",
    "dirname",
    "SUBST",
}
KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!"}
SEPARATORS = {";", "&&", "||", "|"}
HELP_FLAGS = {"--help", "-help", "-h", "--version", "-version", "-V"}
# Never run these even with a help flag (some ignore unknown flags; test/benchmark binaries may treat args as paths).
NO_EXEC = re.compile(
    r"^(shutdown|reboot|halt|rm|rmdir|kill|killall|pkill|dd|diskutil|launchctl|sudo|su)$|bench|test|fate|trasher",
    re.I,
)
SUBST = re.compile(
    r'"?\$\((?:command -v|which) +(?:"\$\w+"|\$\w+|[\w.+-]+)(?: +2>/dev/null)?\)"?'
)
# Package listings agents use to find installed tools: (command, allowed first arguments).
LISTINGS = {
    "pip3": {"list", "show"},
    "pip": {"list", "show"},
    "pipx": {"list"},
    "npm": {"ls", "list"},
}


def segment_ok(words: list[str]) -> bool:
    while words and words[0] in KEYWORDS:
        words = words[1:]
    if not words or words[0] in {"done", "fi"}:
        return True
    w0 = words[0]
    if w0 in {"eval", "exec", "source", "."}:
        return False
    if w0 == "for":  # `for VAR in WORDS`
        return len(words) >= 3 and words[2] == "in"
    if w0 == "command":
        return len(words) > 1 and words[1] == "-v"
    if re.fullmatch(r"\w+=SUBST", w0):  # p=$(command -v "$t")
        return len(words) == 1
    if os.path.basename(w0) == "brew":
        return len(words) > 1 and words[1] in {"list", "info", "desc"}
    if w0 in LISTINGS:
        return len(words) > 1 and words[1] in LISTINGS[w0]
    if w0 == "uv":
        return words[1:3] in (["tool", "list"], ["pip", "list"])
    if w0 in READ_ONLY:
        return True
    name = os.path.basename(w0)  # `<tool> [subcommand ...] --help`, nothing else
    return (
        words[-1] in HELP_FLAGS
        and not NO_EXEC.search(name)
        and len(words) <= 4  # tool + up to 2 subcommand words + flag
        and all(re.fullmatch(r"[a-z][a-z0-9-]*", w) for w in words[1:-1])
    )


def decide(cmd: str) -> bool:
    s = SUBST.sub("SUBST", cmd).replace("\n", ";")
    if "`" in s or "$(" in s or "<(" in s:
        return False
    try:
        lex = shlex.shlex(s, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:  # unbalanced quotes
        return False
    segments, words, i = [], [], 0
    while i < len(tokens):
        t = tokens[i]
        if t in SEPARATORS:
            segments.append(words)
            words = []
        elif t in {">", "&>"} and i + 1 < len(tokens) and tokens[i + 1] == "/dev/null":
            if words and words[-1].isdigit():
                words.pop()  # the fd in `2>/dev/null`
            i += 1
        elif t == ">&" and i + 1 < len(tokens) and tokens[i + 1].isdigit():
            if words and words[-1].isdigit():
                words.pop()  # `2>&1`
            i += 1
        elif set(t) <= set("<>&()"):  # any other redirect, background `&` or subshell
            return False
        else:
            words.append(t)
        i += 1
    segments.append(words)
    return all(segment_ok(w) for w in segments)


def self_test() -> None:
    allow = [
        'for t in ntfy viu flowmark; do printf "%s: " $t; command -v $t || echo "not found"; done',
        "for b in lua luajit; do command -v $b 2>/dev/null && echo ok; done",
        "for t in a b; do command -v $t; done; ls /opt/homebrew/bin | grep -i -E 'kube|k3s|helm'",
        "command -v gh && gh label delete --help | head -n 20",
        'command -v chgrp; ls -l "$(command -v chgrp)" 2>/dev/null; chgrp --version 2>&1 | head -1',
        "iconutil --help 2>&1 | head -n 20",
        "/opt/homebrew/bin/ffprobe -version | head -1",
        "command -v viu",
        "kubectl exec --help | head -n 5",
        'for t in a b; do p=$(command -v "$t" 2>/dev/null); echo "$t: ${p:-not found}"; done',
        "/opt/homebrew/bin/brew list --formula 2>/dev/null | grep -Ei 'fish|fzf'",
        "pip3 list 2>/dev/null | grep -i md; npm ls -g --depth=0 2>/dev/null; uv tool list",
    ]
    deny = [
        "for f in *; do rm $f; done",
        "for t in a; do echo $t > out; done",
        "for t in a; do echo $t >> out; done",
        "for t in $(ls); do command -v $t; done",
        "for t in a; do eval $t; done",
        "exec rm x",
        "for t in a; do exec $t; done",
        "for t in a; do brew install $t; done",
        "for t in a; do command $t; done",
        "echo hi | tee out",
        "gh label delete bug --help",
        "shutdown -h",
        "trasher --help",
        "command -v a\nrm -rf x",
        "command -v a & rm x",
        "(rm x)",
        "ls > out",
        "cat < /etc/hosts",
        "p=$(command -v a > out)",
        "p=$(rm x)",
        "pip3 install x",
        "npm install -g x",
        "uv tool install x",
        "uv run x",
    ]
    bad = [c for c in allow if not decide(c)] + [c for c in deny if decide(c)]
    assert not bad, bad
    print("allow_loops self-test ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--only-find-tool"]:  # single-lookup stage: a plain `find-tool "<text>"`, nothing else
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
        ok = re.fullmatch(r"""find-tool +("[^"`$\\]*"|'[^']*')""", cmd.strip())
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "allow" if ok else "deny",
                                                 "permissionDecisionReason": "only find-tool is available"}}))
        sys.exit()
    if sys.argv[1:] == ["--test"]:
        self_test()
        sys.exit()
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    if decide(
        cmd
    ):  # ponytail: probe allowlist over shlex tokens, not a full shell parser; unknown shapes fall to deny
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "permissionDecisionReason": "read-only probe",
                    }
                }
            )
        )
