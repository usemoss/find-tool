# find-tool

Find the right command-line tool **installed on your machine** by describing what you want to do.

```console
$ find-tool "convert a folder of PNG icon sizes into a macOS .icns file"
tiff2icns (cli): tiff2icns: tiff2icns – converts TIFF to icns format ...
iconutil (cli): iconutil: iconutil – Utility to convert between '.iconset' and '.icns' files ...
...
$ find-tool "set an organization secret for specific repositories"
gh secret (cli): gh secret: Manage GitHub secrets. Secrets can be set at the repository, or organization level ...
docker pass (cli): docker pass: Docker Pass Secrets Manager Plugin (beta) ...
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
and to skip it for everyday commands. That wording was chosen by benchmark (below): softer wording was almost never
triggered, and wording that made the agent load the skill first added a round trip to every task.

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

**Agents** (headless Claude Code; tasks the model got wrong from memory, then retried with read-only shell access,
with vs without `find-tool` + skill):

| Model | Task set | Control fixes | With find-tool | Cost per fix |
|---|---|---|---|---|
| Sonnet | unfamiliar tools (personal, niche, lesser-known OS utilities) | 5/12 | 9/12 | $0.032 → $0.018 |
| Haiku | unfamiliar tools | 1/14 | 8/14 | $0.016 → $0.002 |
| Haiku | benchmark tasks | 5/29 | 13/29 | $0.0063 → $0.0027 |
| Sonnet | benchmark tasks | 12/26 | 12/26 | $0.026 → $0.027 |

On tasks the model already answers correctly, the skill added about 6% cost for Sonnet and 12% for Haiku.
In short: `find-tool` helps most when the model doesn't know the tool — niche or personal tools, or smaller models —
and costs little when it isn't needed. A strong model on well-known tools gains nothing.

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
