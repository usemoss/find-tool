# find-tool benchmarks

Scripts to measure (1) whether `find-tool` retrieves the right installed tool, and (2) whether it helps a coding agent
choose the right command. Every generated file (task lists, labels, results) is specific to the machine it was built
on and is git-ignored; rebuild them on yours.

Run all commands from the repository root with the `MOSS_*` variables set (see `.env.example`).

## 1. Build a task set

No public benchmark directly tests "pick the right *installed* tool", so tasks are derived from two
natural-language-to-shell datasets and filtered to your machine:

```sh
mkdir -p bench/data/tldr bench/data/nl2sh-alfa
for s in train dev test; do curl -sfL -o bench/data/tldr/tldr-$s.jsonl \
  https://huggingface.co/datasets/neulab/tldr/resolve/main/tldr-$s.jsonl; done
for f in test.csv train.csv; do curl -sfL -o bench/data/nl2sh-alfa/$f \
  https://huggingface.co/datasets/westenfelder/NL2SH-ALFA/resolve/main/$f; done

python3 bench/tldr_cases.py > bench/tldr-cases.tsv                 # tldr test split
python3 bench/alfa_cases.py test  --stats > bench/alfa-test.tsv    # NL2SH-ALFA (verified)
python3 bench/alfa_cases.py train --stats > bench/alfa-train.tsv   # NL2SH-ALFA (unverified)
```

Filters: the reference tool must be installed, must not be named in the task, and must not be an everyday or famous
tool (`COMMON` / `WELL_KNOWN` in `alfa_cases.py`); tasks with an everyday-only reference solution are dropped.

**Relabeling.** Dataset labels name a single tool, but tasks often have several correct answers (`chown`/`chgrp`,
`realpath`/`readlink`, `dig`/`host`/`nslookup`), and many tldr lines only make sense on their tool's page. So:

```sh
python3 bench/make_label_pool.py        # -> label-tasks.jsonl (task text only) + label-key.jsonl (references)
```

Give `label-tasks.jsonl` to three independent LLM labelers (we used two Sonnet and one Haiku, with no shell, web or
reference answers). Each writes `bench/data/labels/labels-<name>.jsonl`, one line per task:

```json
{"id": "tldr-12", "self_contained": true, "tools": ["zgrep", "gzgrep"], "note": ""}
```

Then merge with rules fixed in advance (≥2/3 self-contained; acceptable = tools named by ≥2 labelers plus the
reference if ≥1 names it; installed only; drop if an everyday tool also works):

```sh
python3 bench/merge_labels.py > bench/eval-set.tsv
```

`LABELERS` in `merge_labels.py` lists the expected label file names.

Also worth writing by hand: an **unfamiliar-tool set** (`intent<TAB>tool[,tool]`, e.g. `bench/unfamiliar.tsv`) of
tasks that only your personal, niche or lesser-known installed tools solve. Phrase tasks from a user's point of view
and never name the tool.

## 2. Retrieval: find-tool vs apropos

```sh
python3 eval.py --moss --queries bench/eval-set.tsv          # top-5 hit rate (+ apropos found-anywhere)
python3 bench/compare_apropos.py > bench/apropos-compare.jsonl         # like-for-like comparison
```

`compare_apropos.py` reports two fair comparisons, since `apropos` output is unranked:
top-level tools deduplicated (find-tool's 5 distinct tools vs all of apropos's distinct commands), and the number of
lines read before the first acceptable answer.

## 3. Agents: with vs without find-tool

`agent_run.py` runs headless Claude Code (`claude -p`) per task. The agent must reply with `COMMAND: <cmd>` and is
never allowed to perform the task (state-changing commands are denied). It needs `ANTHROPIC_API_KEY`
(see `bench/.env.example`).

Isolation: API-key auth with an empty `HOME`/`CLAUDE_CONFIG_DIR`, `--setting-sources local`, `--strict-mcp-config`,
and an empty git repository as the working directory, so no personal `CLAUDE.md`, hooks, plugins or MCP servers
reach the agent. Note that enabling the Skill tool adds Claude Code's built-in skill list to every prompt, so the
fair control for cost is `controlsk` (Skill tool, no find-tool), not bare Bash.

```sh
M=claude-sonnet-5-5
python3 bench/agent_run.py base      --tag sonnet-evalset --model $M   # no tools: answer from memory
python3 bench/agent_run.py controlsk --tag sonnet-evalset --model $M   # misses, read-only shell
python3 bench/agent_run.py skill     --tag sonnet-evalset --model $M
python3 bench/agent_run.py controlsk --tag sonnet-evalset --model $M --on hits --n 26 --suffix=-hits
python3 bench/agent_run.py skill     --tag sonnet-evalset --model $M --on hits --n 26 --suffix=-hits
```

Stages after `base` run only on base misses (`--on misses`) or a sample of base hits (`--on hits`, to measure the
cost of using the skill when it isn't needed). Each run records the final command, whether it's correct, commands
executed, whether find-tool ran, tokens and cost. Results: `bench/runs/<tag>/<stage>.jsonl`.

The `skill` stage uses the shipped plugin (`plugin/`); pass `--plugin DIR` to benchmark a copy with different
wording. Four skill descriptions were compared before choosing the shipped one (v4):

| Version | Description style | Outcome |
|---|---|---|
| v1 | "use when unsure which tool" | never triggered |
| v2 | mandatory; agents load the skill, then run find-tool | best accuracy, +69% cost on tasks the model already knew (Sonnet) |
| v3 | "use instead of guessing; skip tools you know" | rarely triggered |
| v4 | mandatory for non-everyday tools; run find-tool directly, no need to load the skill | near-v2 accuracy at about control cost (shipped) |
