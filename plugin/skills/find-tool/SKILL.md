---
name: find-tool
description: REQUIRED before answering with, or probing for, any command-line tool that is not an everyday command. Run `find-tool "<what you want to do>"` directly in Bash (no need to load this skill first) - it prints the 5 best-matching tools installed on this machine, including subcommands. Run it once INSTEAD of guessing names with which/command -v/man/apropos. Not needed for everyday commands you know well (ls, cat, grep, sed, awk, find, sort, cut, xargs, tar, curl, git, ssh).
---

# find-tool

```
find-tool "<what you want to do, in plain words>"
```

Prints the 5 most relevant tools installed on this machine (including subcommands), one per line:
`name [subcommand] (kind): description`.

1. Run it once, describing the goal rather than a guessed tool name (e.g. `find-tool "resize an image to 800px wide"`).
2. Answer with the listed tool that does the job directly; check flags with `<tool> --help` only if needed.
3. If nothing fits, rephrase once, then fall back to your own knowledge.
