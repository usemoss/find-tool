# find-tool

Find the right command-line tool **installed on your machine** by describing what you want to do.

![find-tool answering three queries on a macOS machine](demo/find-tool.gif)

`find-tool` indexes every executable on your `$PATH` (man pages, `--help`, package descriptions, subcommands) and
your installed agent skills into a [Moss](https://moss.dev) semantic search index, and answers with the 5 most
relevant tools via the [Moss CLI](https://docs.moss.dev/docs/integrations/moss-cli).

It matters most for **coding agents**: a model can't know the CLIs you or your team wrote, and often doesn't know
which niche tools you have. The bundled Claude Code skill makes the agent run one `find-tool` lookup instead of
guessing.

| Headless Claude Code, 3 runs per task | From memory | One `find-tool` lookup |
|---|---|---|
| CLIs the machine's owner wrote (3 tasks), Haiku and Sonnet | 3 of 9 runs | **9 of 9** |
| Niche and unfamiliar tools (29 tasks), Sonnet 5.5 | 60 of 87 | **87 of 87** |
| Niche and unfamiliar tools (29 tasks), Haiku 5.5 | 59 of 87 | **80 of 87** |
| Public CLIs from tldr / NL2SH-ALFA (152 tasks), Sonnet 5.5 | 422 of 456 | 441 of 456 |

Measured on one macOS machine; methodology, significance tests and caveats are in [`bench/`](bench/README.md).

## Install

Requires Python 3.9+, [`jq`](https://jqlang.org), the [Moss CLI](https://docs.moss.dev/docs/integrations/moss-cli)
(`pip install moss-cli`) and a [Moss account (free)](https://portal.usemoss.dev/). Developed on macOS; Linux should
work but is untested.

1. **Moss credentials.** At https://portal.usemoss.dev, create a project and a project key (or `moss login`, then
   `moss keys create --project <id>`). Then run `moss init` to save them to `~/.moss/config.json`, where `find-tool`
   and your agent's shell will find them. (Alternatively export `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`; see
   `.env.example`.)

2. **Build the index** (about a minute for ~1,500 tools):

   ```sh
   git clone https://github.com/usemoss/find-tool && cd find-tool
   python3 build.py --log help-calls.log > docs.json
   moss index create find-tool -f docs.json --wait
   ```

   After installing new tools, rebuild and run `moss doc add find-tool -f docs.json --upsert --wait`.

3. **Claude Code plugin** (user scope, all projects). It adds the skill and puts `find-tool` on the agent's `PATH`:

   ```sh
   claude plugin marketplace add usemoss/find-tool
   claude plugin install find-tool@find-tool
   ```

   Or inside Claude Code: `/plugin install find-tool --marketplace usemoss/find-tool`. Update with
   `claude plugin update find-tool@find-tool`. To skip the permission prompt, allow `Bash(find-tool *)` in your
   settings.

4. **On your own command line** (optional): `ln -s "$PWD/plugin/bin/find-tool" ~/.local/bin/find-tool`.

## Usage

```sh
find-tool "transcribe a WAV file to text"
moss --json query find-tool "transcribe a WAV file to text" -k 20 | jq '.docs[].metadata.name'   # raw results
```

Each query takes 2–3 seconds (the Moss CLI loads the index on every call).

On a terminal, tool names are colored and each description is on its own line, fitted to the terminal width. When
piped (scripts, agents), each tool is one line: `name [subcommand] (kind, path): description`. Options:

| Variable | Default |
|---|---|
| `FIND_TOOL_INDEX` | `find-tool` |
| `FIND_TOOL_COLOR` | `1;36` (bold cyan, any ANSI color code); empty, or `NO_COLOR` set, turns color off |
| `FIND_TOOL_DESC_CHARS` | terminal width − 2, or 160 when piped |

**What gets indexed:** the first match for every name on `$PATH` (as your shell resolves it), one document per
subcommand (`gh secret`, `kubectl delete`, ...), and skills under `~/.claude`, `~/.codex` and `~/.agents`. `--help` is
only run for user-installed tools (never system binaries), with no stdin, a timeout and an empty working directory;
every executed command is written to `--log`.

## Repository layout

```
plugin/            Claude Code plugin: the find-tool skill and bin/find-tool (the query command)
demo/              the README GIF and its vhs tape (vhs demo/find-tool.tape)
build.py           builds the index documents (JSON on stdout)
eval.py            retrieval eval: find-tool vs apropos on an intent<TAB>tool file
queries.tsv        30 example intents for macOS
bench/             agent and retrieval benchmarks (see bench/README.md)
```

## License

Apache-2.0. See [LICENSE](LICENSE).
