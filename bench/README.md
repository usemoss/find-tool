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

`agent_run.py` runs headless Claude Code (`claude -p`) once per task. The agent is asked for the best tool installed
on this machine (a tool built for the task over a general-purpose one; a simple command over inline scripts) and must
end with `TOOL: <name>`. It never performs the task. It needs `ANTHROPIC_API_KEY` (see `bench/.env.example`).

Isolation: API-key auth with an empty `HOME`/`CLAUDE_CONFIG_DIR`, `--setting-sources local`, `--strict-mcp-config`,
and an empty git repository as the working directory, so no personal `CLAUDE.md`, hooks, plugins or MCP servers
reach the agent.

**Design: one lookup vs memory.** Two conditions, same prompt:

- `base`: no tools; the model names the tool from what it knows.
- `lookup`: the agent may run only `find-tool "<what you want to do>"` (a PreToolUse hook, `allow_loops.py
  --only-find-tool`, denies every other command). If nothing fits, it rephrases once, then falls back to its own
  knowledge, as the shipped skill says.

Neither condition can be blocked part-way through a search, so the comparison is clean. Run each condition several
times (`--suffix=-r1`, `-r2`, ...), because answers vary between runs:

```sh
M=claude-haiku-5-5
for r in 1 2 3; do
  python3 bench/agent_run.py base   --tag haiku-mine --model $M --tasks mine.tsv --on all --suffix=-r$r
  python3 bench/agent_run.py lookup --tag haiku-mine --model $M --tasks mine.tsv --on all --suffix=-r$r
done
python3 bench/judge.py bench/runs/haiku-mine/*-r?.jsonl            # blind check of answers not in the labels
python3 bench/compare_runs.py --tag haiku-mine --control base --treatment lookup --tasks mine.tsv
```

**Write your own tasks** (`mine.tsv`, `intent<TAB>tool[,tool]`, in `bench/`): pick tools on your machine, especially
ones you or your team wrote, describe the job from a user's point of view, and never name the tool. List every
installed tool that does the job.

**Scoring.** An answer is correct if its tool is in the task's list. Other answers go to `judge.py`: a judge model
(Sonnet by default) sees only the task, the answered tool and that tool's man/`--help` text, never the condition or
the label, and decides whether the tool is built for the task; the tool must also be on `$PATH` (checked directly).
Verdicts are cached per (task, tool), so both conditions get the same verdict. `compare_runs.py` counts a task as
correct when most repeats are, and reports an exact McNemar test on the tasks where the conditions differ.
`--tasks` rescores stored runs against the current labels if you correct them later.

**Exploration stages** (`control`, `controlsk`, `skill`, `forced`) let the agent search the machine with read-only
commands. They are harder to make fair: `--permission-mode dontAsk` denies anything not explicitly allowed, every part
of a compound command must be allowed, and reads outside the working directory are denied. `ALLOW`, `--add-dir` (the
`$PATH` directories, their parents and `/Applications`) and the `allow_loops.py` hook (loops, `$(command -v x)`,
`<tool> --help`) cover the common probes, but agents invent many one-off commands, and a denied probe makes the agent
answer without the information. In our runs the control agent hit a denial far more often than the find-tool agent,
so check `denials` per condition before trusting an exploration result.

The `skill` stage uses the shipped plugin (`plugin/`); pass `--plugin DIR` to benchmark a copy with different
wording. Four skill descriptions were compared before choosing the shipped one (v4). These runs used an earlier
setup that blocked many of the control's probes, so read the table for how often each wording got find-tool used,
not for accuracy:

| Version | Description style | Outcome |
|---|---|---|
| v1 | "use when unsure which tool" | never triggered |
| v2 | mandatory; agents load the skill, then run find-tool | best accuracy; +$0.0069 per task on tasks the model already knew (Sonnet) |
| v3 | "use instead of guessing; skip tools you know" | rarely triggered, so no accuracy gain |
| v4 | mandatory for non-everyday tools; run find-tool directly, no need to load the skill | nearly v2's accuracy; +$0.0006 per task on tasks the model already knew (Sonnet); shipped |
