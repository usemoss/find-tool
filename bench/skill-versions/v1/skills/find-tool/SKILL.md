---
name: find-tool
description: Find which command-line tool installed on this machine can do a task. Use when you need a shell command but aren't sure which tool does it, when the task needs something beyond everyday commands (ls, grep, sed, find, curl, git), or before concluding that no installed tool can do it.
---

# find-tool

`find-tool` searches every executable on `$PATH` (and their subcommands) by meaning, not by name.

```
find-tool "<what you want to do, in plain words>"
```

It prints the 5 most relevant installed tools, one per line: `name [subcommand] (kind): description`.

## How to use it
1. Describe the goal, not a guessed tool name: `find-tool "show which process is listening on a port"`.
2. Pick the best match. Confirm usage with `man <tool>` or `<tool> --help` if you need flags.
3. If nothing fits, rephrase once with different words (e.g. the object or protocol involved) before giving up.

Skip it for everyday commands you already know well.
