# find-tool

Find the right command-line tool **installed on your machine** by describing what you want to do.

```console
$ find-tool "convert a folder of PNG icon sizes into a macOS .icns file"
tiff2icns (cli, /usr/bin/tiff2icns): tiff2icns: tiff2icns – converts TIFF to icns format ...
iconutil (cli, /usr/bin/iconutil): iconutil: iconutil – Utility to convert between '.iconset' and '.icns' files ...
...
$ find-tool "set an organization secret for specific repositories"
gh secret (cli, /opt/homebrew/bin/gh): gh secret: Manage GitHub secrets. Secrets can be set at the repository, or organization level ...
docker pass (cli, /usr/local/bin/docker): docker pass: Docker Pass Secrets Manager Plugin (beta) ...
...
```

(Real output from a macOS machine, trimmed; results depend on what you have installed.)

`find-tool` indexes every executable on your `$PATH` — their man pages, `--help` output, package descriptions and
subcommands — plus any installed agent skills, into a [Moss](https://moss.dev) semantic search index. Queries are
answered by the [Moss CLI](https://docs.moss.dev/docs/integrations/moss-cli) and return the 5 most relevant
**distinct** tools.

It is built for two audiences:

- **Developers** who know what they want but not which installed tool does it (`apropos` only keyword-matches man
  page one-liners and returns hundreds of unranked lines).
- **Coding agents**, which otherwise guess tool names and probe with `which`/`man` — or don't know that a niche or
  personal tool is installed at all. A bundled agent skill teaches them to run one `find-tool` query instead.

## Requirements

- Python 3.9+ (standard library only)
- [Moss CLI](https://docs.moss.dev/docs/integrations/moss-cli): `pip install moss-cli`
- [`jq`](https://jqlang.org)
- A Moss project (semantic search uses the cloud model; the CLI's offline mode is keyword-only and holds one index)

Developed and tested on macOS. Indexing relies on `man`, `col` and `--help`, so Linux should work too, but it is untested.

## Setup

1. **Credentials.** Create a Moss project, then a project key (`moss login`, `moss keys create --project <id>`).
   Copy `.env.example` to `.env` and fill it in, or export the variables:

   ```sh
   export MOSS_PROJECT_ID=...
   export MOSS_PROJECT_KEY=...
   export FIND_TOOL_INDEX=find-tool   # optional, this is the default
   ```

2. **Build the index** (about a minute for ~1,500 tools; runs `man` and `--help` in parallel):

   ```sh
   python3 build.py --log help-calls.log > docs.json
   moss index create find-tool -f docs.json --wait
   ```

   To refresh after installing tools: rebuild and run `moss doc add find-tool -f docs.json --upsert --wait`.

3. **Put `find-tool` on your `PATH`**, e.g. `ln -s "$PWD/find-tool" ~/.local/bin/find-tool`.

### What gets indexed

| Source | Text |
|---|---|
| Every executable on `$PATH` (first match wins, as in your shell) | man page summary and DESCRIPTION, `--help` output, and the Homebrew or `uv tool` package description when available |
| Subcommands (`gh secret`, `kubectl delete`, `docker compose`, ...) | one document each, from the tool's command list and `<tool> <subcommand> --help` |
| Agent skills (`SKILL.md` under `~/.claude`, `~/.codex`, `~/.agents`) | the skill's name and description |

Safety while indexing: `--help` is only executed for user-installed tools (Homebrew, `/usr/local`, `~/.local`,
`~/.cargo`, `~/go`), never for system binaries; it runs with no stdin, a timeout and an empty scratch working
directory, skips benchmark/test binaries, and every executed command line is written to `--log` for audit.

## Usage

```sh
find-tool "convert a folder of PNG icons into a macOS .icns file"
find-tool "set an organization secret for specific repositories"
```

Or query Moss directly (same index, raw JSON):

```sh
moss --json query find-tool "transcribe a WAV file to text" -k 20 | jq '.docs[].metadata.name'
```

Each query takes about 2–3 seconds: the Moss CLI loads the index on every call.

## Agent skill (Claude Code)

`plugin/` is a Claude Code plugin containing the `find-tool` skill. Load it with
`claude --plugin-dir plugin`, or copy `plugin/skills/find-tool/` into your skills directory.
The agent's shell needs `find-tool` on `PATH` and the `MOSS_*` variables set; allow it with `Bash(find-tool:*)`.

The skill's description tells the agent to run `find-tool` once, directly, before probing for any non-everyday tool,
and to skip it for everyday commands; if nothing fits, the agent rephrases once, then falls back to its own knowledge.
That wording was chosen by benchmark ([`bench/`](bench/README.md)): softer wording was almost never triggered, and
wording that made the agent load the skill first added a round trip to every task.

## How well does it work?

Measured on one macOS developer machine (~1,500 executables). Reproduction scripts and methodology are in
[`bench/`](bench/README.md); your numbers will differ with your installed tools.

**Retrieval** (152 tasks from the [tldr](https://huggingface.co/datasets/neulab/tldr) and
[NL2SH-ALFA](https://huggingface.co/datasets/westenfelder/NL2SH-ALFA) benchmarks, filtered to non-everyday tools
installed on the machine, with acceptable tools agreed by three LLM labelers):

| | Finds an acceptable tool | What you read |
|---|---|---|
| `find-tool` | 114/152 in its top 5 (median rank of first hit: 2) | 5 lines |
| `apropos` | 115/152 anywhere in its output (median first hit: line 176) | median 1,323 lines |

**Agents.** Headless Claude Code was asked to name the best installed tool for each task, in two ways: from memory
(no tools), and after one `find-tool` lookup (the only command it could run; if nothing fit, it fell back to its own
knowledge). Each task was run 3 times per condition. Answers outside a task's accepted list were checked by a blind
judge and counted only if the tool is installed and built for the task.

| Model | Tasks | From memory | One `find-tool` lookup |
|---|---|---|---|
| Haiku 5.5 | 29 unfamiliar tools on this machine | 59 of 87 runs | **80 of 87** |
| Sonnet 5.5 | 29 unfamiliar tools on this machine | 60 of 87 | **87 of 87** |
| Haiku 5.5 | 152 benchmark tasks (public tools) | 420 of 456 | 435 of 456 |
| Sonnet 5.5 | 152 benchmark tasks (public tools) | 422 of 456 | **441 of 456** |

Counting a task as correct when most of its 3 runs were: on the unfamiliar tools, Haiku went from 20 to 27 tasks
(p = 0.039) and Sonnet from 20 to 29 (p = 0.004); on the benchmark tasks, Haiku from 141 to 146 (p = 0.23, not
significant) and Sonnet from 142 to 148 (p = 0.031). p is an exact McNemar test on the tasks where the two conditions
differed.

The unfamiliar tools, by kind:

| Kind (tasks) | Haiku: memory → lookup | Sonnet: memory → lookup |
|---|---|---|
| CLIs written by the machine's owner (3) | 3 → **9** of 9 | 3 → **9** of 9 |
| Niche public tools installed with `uv tool` (5) | 9 → **15** of 15 | 12 → **15** of 15 |
| Less-common Homebrew packages (12) | 23 → **33** of 36 | 23 → **36** of 36 |
| Lesser-known macOS built-ins (9) | 24 → 23 of 27 | 22 → **27** of 27 |

In short: a model can't know the CLIs you or your team wrote, and it often doesn't know which niche tools you have
installed. One `find-tool` lookup fixes that for both a small and a large model. On well-known public tools the gain
is small. The lookup adds one turn per task.

**About the unfamiliar-tool tasks.** These 29 tasks were written for the benchmark machine (macOS, ~1,500
executables) and are not published, since they only make sense there. They use tools a model is unlikely to know or
to expect: three CLIs the machine's owner wrote (discord-time, vid2webp, flowmark-rs), niche tools installed with
`uv tool`, less-common Homebrew packages, and lesser-known macOS built-ins. Tasks never name the tool. Two labelling
fixes were made after the runs and applied to both conditions (a missing equivalent tool added, a non-Apple tool
removed from two "built-in macOS" tasks), and one task was dropped because its answer was not a CLI. The fallback
sentence in the lookup prompt was added after a first run showed the agent dropping correct answers when
`find-tool` missed; it matches the shipped skill.

**Try it with your own tools and agent:** write a few tasks for tools on your machine, especially ones you or your
team wrote (`intent<TAB>tool` in a TSV), and run the single-lookup design in [`bench/`](bench/README.md#3-agents-with-vs-without-find-tool).

## Repository layout

```
find-tool          the query command (moss + jq)
build.py           builds the index documents (JSON on stdout)
eval.py            retrieval eval: find-tool vs apropos on an intent<TAB>tool file
queries.tsv        30 example intents for macOS
plugin/            Claude Code plugin with the find-tool skill
.env.example
bench/             benchmark scripts and methodology (see bench/README.md)
```

## License

Apache-2.0. See [LICENSE](LICENSE).
