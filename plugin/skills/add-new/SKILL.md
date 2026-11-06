---
name: add-new
description: Add newly installed CLIs (and refresh agent skills) in the find-tool index without rebuilding it.
disable-model-invocation: true
allowed-tools: Bash(find-tool --add-new)
---

Run `find-tool --add-new` in Bash with a 10-minute timeout (600000 ms). It indexes only CLIs on PATH that aren't in
the index yet and refreshes the agent skills; the index stays online. It doesn't remove uninstalled tools or update
changed ones; `/find-tool:init` rebuilds everything.

Then report how many documents were added and the directory with the `--help` log, both printed at the end. If it
fails because the index doesn't exist, suggest `/find-tool:init`. If it fails with a credentials error, tell the user
to put `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY` in `~/.config/find-tool/.env`.
