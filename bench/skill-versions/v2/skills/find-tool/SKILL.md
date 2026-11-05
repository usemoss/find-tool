---
name: find-tool
description: MANDATORY before choosing any command-line tool. You MUST run `find-tool "<what you want to do>"` FIRST whenever a task needs a shell command or CLI tool, or whenever you are about to check what is installed (before any `which`, `command -v`, `man`, `apropos`, `ls` of bin directories, or guessing tool names). Your memory of tool names is not a check of this machine; find-tool searches every installed tool and subcommand on this machine by meaning. Never answer with, or probe for, a CLI tool without running find-tool first.
---

# find-tool (always run first)

**Rule: before you name, probe for, or answer with any CLI tool, run:**

```
find-tool "<what you want to do, in plain words>"
```

It prints the 5 most relevant tools installed on this machine (including subcommands), one per line:
`name [subcommand] (kind): description`.

## Steps
1. Run `find-tool` with the goal in plain words, not a guessed tool name.
   Example: `find-tool "resize an image to 800px wide"`.
2. Prefer a listed tool that does the task directly over composing everyday commands.
3. Then (optionally) confirm flags with `man <tool>` or `<tool> --help`.
4. If nothing fits, run `find-tool` once more with different words (the object, format or protocol), and only then fall back to your own knowledge or `which`.

Do this even when you think you already know the answer: an installed specialised tool (e.g. `sips`, `textutil`, `caffeinate`) is often a better answer than the familiar one.
