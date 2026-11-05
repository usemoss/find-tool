---
name: find-tool
description: Use INSTEAD of guessing which command-line tool to use. When a task needs a CLI tool and you are not certain which installed tool does it, run `find-tool "<what you want to do>"` once BEFORE probing guessed names with `which`/`command -v`, searching `apropos`, or reading man pages to discover a tool. It searches every tool and subcommand installed on this machine by meaning and returns the 5 best matches, which is faster and cheaper than trial-and-error. Skip it when you already know the exact tool and are sure it is installed (everyday commands such as ls, grep, find, sed, curl, git).
---

# find-tool

Replace guess-and-check with one search:

```
find-tool "<what you want to do, in plain words>"
```

Output: the 5 most relevant installed tools (including subcommands), one per line: `name [subcommand] (kind): description`.

1. Run it once with the goal in plain words (e.g. `find-tool "resize an image to 800px wide"`).
2. Pick the listed tool that does the job directly and answer. Check flags with `<tool> --help` only if you need them.
3. If nothing fits, rephrase once; then fall back to your own knowledge.

Don't run it for commands you already know well.
