---
name: init
description: Build or fully rebuild the find-tool index from every CLI on PATH and the installed agent skills, replacing any existing index.
disable-model-invocation: true
allowed-tools: Bash(find-tool --init)
---

Run `find-tool --init` in Bash with a 10-minute timeout (600000 ms). It takes 1-2 minutes: it reads man pages, runs
`--help` for user-installed tools (never system binaries), deletes the existing index and creates a new one.

Then report the document count and the directory with the `--help` log, both printed at the end. If it fails with a
credentials error, tell the user to put `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` in `~/.config/find-tool/.env`.
