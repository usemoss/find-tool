# find-tool

Find the right command-line tool **installed on your machine** by describing what you want to do.

<img
  width="800"
  height="300"
  alt="example find-tool CLI commands"
  src="https://github.com/user-attachments/assets/0af14c9c-9764-453f-b5c2-b3d5b34784c5"
/>

> `find-tool` indexes every executable on your `$PATH` (man pages, `--help`, package descriptions, subcommands) and
your installed agent skills into a [Moss](https://moss.dev) semantic search index, and answers with the 5 most
relevant tools via the [Moss CLI](https://docs.moss.dev/docs/integrations/moss-cli).

<details><summary><b>Coding Agents</b></summary>

A model can't know the CLIs you or your team wrote, and often doesn't know
which niche tools you have. The bundled Claude Code skill makes the agent run one `find-tool` lookup instead of
guessing.

</details>

## Benchmark results

Measured on one macOS machine (~1,500 executables).

**Agents**: Headless Claude Code named the best installed tool for each task, either from memory or after one
`find-tool` lookup (3 runs per task; answers outside the accepted tool list were checked by a blind judge):

| Tasks | Model | From memory | One `find-tool` lookup |
|---|---|---|---|
| Owner CLI tools (3 tasks) | Haiku 5.5 and Sonnet 5.5 | 3 of 9 runs | **9 of 9** |
| Niche and uncommon tools (29 tasks) | Sonnet 5.5 | 60 of 87 | **87 of 87** |
| | Haiku 5.5 | 59 of 87 | **80 of 87** |
| Public CLIs from tldr / NL2SH-ALFA (152 tasks) | Sonnet 5.5 | 422 of 456 | **441 of 456** |
| | Haiku 5.5 | 420 of 456 | 435 of 456 |

The gain is largest for tools a model can't know (your own and niche CLIs) and small for well-known public tools.

**Retrieval.** On the 152 public tasks, `find-tool` had an acceptable tool in its top 5 for 114 (median rank 2);
`apropos` had one somewhere in its output for 115, but you'd read a median of 1,323 unranked lines to find it.

> [!NOTE]
> Details, methodology, significance tests and caveats are in [`bench/`](bench/README.md).

## Install

Requires:

- Python 3.9+
- [`jq`](https://jqlang.org)
- [Moss CLI](https://docs.moss.dev/docs/integrations/moss-cli) (`pip install moss-cli`)
- [Moss account (free)](https://portal.usemoss.dev/).

> [!NOTE]
> Developed on macOS; Linux should work but is untested.

1. **Moss credentials.**
   - Login to https://portal.usemoss.dev
   - create a project and a project key (or `moss login moss keys create --project <id>`)
   
   Then save them where `find-tool` (and the plugin) will find them in any directory:

   ```sh
   mkdir -p ~/.config/find-tool && touch ~/.config/find-tool/.env && \
       chmod 600 ~/.config/find-tool/.env

   # fill in both values
   printf 'MOSS_PROJECT_ID=<id>\nMOSS_PROJECT_KEY=<key>\n' > ~/.config/find-tool/.env
   ```

   This file overrides any `MOSS_*` variables or `moss init` config your other projects use; point
   `FIND_TOOL_ENV` at another file to move it. Without it, `find-tool` falls back to `MOSS_PROJECT_ID` /
   `MOSS_PROJECT_KEY` and `~/.moss/config.json`. The `moss` commands below need the same credentials: run them
   in a shell where you've loaded the file (`set -a; . ~/.config/find-tool/.env; set +a`).

3. **Build the index** (about a minute for ~1,500 tools):

   ```sh
   git clone https://github.com/usemoss/find-tool && cd find-tool

   # build CLI tool records
   python3 build.py --log help-calls.log > docs.json

   # create Moss CLI tools index
   moss index create find-tool -f docs.json --wait
   ```

   After installing new tools, rebuild and run `moss doc add find-tool -f docs.json --upsert --wait`.

4. **Claude Code plugin** (user scope, all projects). It adds the skill and puts `find-tool` on the agent's `PATH`:

   ```sh
   claude plugin marketplace add usemoss/find-tool
   claude plugin install find-tool@find-tool
   ```

   Or inside Claude Code: `/plugin install find-tool --marketplace usemoss/find-tool`. Update with
   `claude plugin update find-tool@find-tool`. To skip the permission prompt, allow `Bash(find-tool *)` in your
   settings.

5. **On your own command line** (optional):
   ```sh
   ln -s "$PWD/plugin/bin/find-tool" ~/.local/bin/find-tool
   ```

## Usage

```sh
find-tool "transcribe a WAV file to text"
moss --json query find-tool "transcribe a WAV file to text" -k 20 \
    | jq '.docs[].metadata.name'   # raw results
```

Each query takes 2–3 seconds (the Moss CLI loads the index on every call).

## Env Config

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
