<div align="center">

# oc-simple-starter

**A simple launcher for OpenCode — start sessions via the native folder picker, search & resume sessions across projects**

[简体中文](README.md) | English

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](pyproject.toml)
[![CI](https://github.com/huangchen/oc-simple-starter/actions/workflows/ci.yml/badge.svg)](https://github.com/huangchen/oc-simple-starter/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/huangchen/oc-simple-starter)](https://github.com/huangchen/oc-simple-starter/releases)

Single file, Python standard library only, zero third-party dependencies.

</div>

## Why

[OpenCode](https://opencode.ai) is a great terminal AI coding agent, but:

- Starting a session in a specific directory means `cd`-ing there first — not as handy
  as a native folder picker;
- `opencode session list` only shows sessions of the **current project**, so finding
  "that conversation from last week in another repo" means digging through SQLite by hand.

`ocs` turns both into two Enter presses: one entry pops the native folder picker and
starts OpenCode there, the other live-searches **all historical sessions** and resumes
the one you pick.

## Features

- **New session** — pops the native folder picker (macOS `osascript`, Linux `zenity`),
  launches `opencode` in the chosen directory, and remembers it as next run's default
- **Search / resume sessions** — read-only queries OpenCode v2's local `opencode.db`,
  lists top-level sessions across all projects (newest first), live filtering as you
  type (multiple keywords matched against title/directory/id/model), resumes the
  selected session with `opencode -s <id> <directory>`
- **Non-interactive subcommands** — `list` / `new` / `resume`, scriptable
- CJK-aware column alignment (full-width = 2 columns); safe to query while OpenCode is
  running (WAL mode)

## Install

```bash
# Option 1: one-liner (macOS / Linux)
curl -fsSL https://raw.githubusercontent.com/huangchen/oc-simple-starter/main/install.sh | bash

# Option 2: from source
git clone https://github.com/huangchen/oc-simple-starter.git
cd oc-simple-starter && ./install.sh

# Option 3: pipx
pipx install git+https://github.com/huangchen/oc-simple-starter.git
```

Requires Python ≥ 3.8 and [OpenCode v2](https://opencode.ai) (`opencode --version` ≥ 2.x).
Uninstall: `./install.sh --uninstall`.

## Usage

```bash
ocs          # interactive UI
```

```
 OpenCode Launcher (oc-simple-starter)
   ◆ New session      — pick a working directory
   ↺ Resume session   — search and enter past sessions
 ↑↓/jk select  Enter confirm  Esc quit   |   12 sessions
```

Inside the session browser:

```
 Resume session — 12 total (all projects, newest first)
 2h ago   09-23 10:21  Fix pagination in session list     ~/code/webapp
 3d ago   09-20 18:40  Research SQLite WAL concurrency    ~/code/dbdoc
 type to filter (space-separated keywords match title/dir/id)  Enter resume  Esc back
 搜索: _
```

| Key | Action |
| --- | --- |
| `↑` `↓` / `k` `j` | Move selection |
| `PgUp` `PgDn` | Page |
| type anything | Live filter (space-separated keywords) |
| `Enter` | Confirm / resume selected session |
| `Esc` | Clear query → back → quit |

### Non-interactive subcommands

```bash
ocs list [keyword]      # list all sessions (optional keyword filter)
ocs new [directory]     # new session; without directory, pops the folder picker
ocs resume <id-prefix>  # resume by session id (prefix allowed)
ocs --version
```

## How it works

- Opens `~/.local/share/opencode/opencode.db` (OpenCode v2's session database) in
  **read-only** mode, merges `session_v2` with the legacy `session` table (dedup by id),
  excludes child and archived sessions — the same scope OpenCode itself lists; nothing
  is ever written to OpenCode's data
- The only local state is `~/.config/oc-simple-starter/state.json` (last working directory)
- Launching replaces the current process (`execvp`), so the terminal is clean after you
  quit opencode

## Development

```bash
python3 tests/test_units.py        # unit tests (helpers + data access + subcommands)
python3 tests/test_tui_smoke.py    # TUI smoke tests (pty-driven, bundled fixtures, CI-ready)
./release.sh -n                    # release dry run: tests + version check, writes nothing
./release.sh minor                 # release: bump → commit & tag → dist/ archives → optional --publish
```

Tests don't require real OpenCode data on the machine; the `OC_SIMPLE_DRY_RUN` and
`OC_SIMPLE_FAKE_PICKER` environment variables are provided for automation.

## Roadmap

- [ ] `ocs delete` (wraps `opencode session delete`)
- [ ] zsh / bash completions
- [ ] Homebrew formula

## Contributing

Issues and PRs are welcome. Please run the tests above before submitting; commit
messages should follow [Conventional Commits](https://www.conventionalcommits.org/).

## License

[MIT](LICENSE)
