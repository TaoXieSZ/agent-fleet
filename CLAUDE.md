# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e '.[dev,repl]'   # editable install with test + REPL extras
pytest -q                       # run all tests (33 pure-Python unit tests, no cmux required)
pytest tests/test_stager.py::test_name   # single test
```

No linter is configured. Core lib has zero runtime deps (stdlib only, Python ≥ 3.10); `[repl]` adds `rich` + `prompt_toolkit`.

Entry points (defined in `pyproject.toml`):
- `agent-fleet-daemon` — long-running Unix-socket broker (must run first)
- `agent-fleet-board [--watch]` — text fleet board
- `agent-fleet-say [-y] "<nickname> <cmd>"` — keyboard driver (stage; `-y` auto-confirms)
- `agent-fleet-confirm [cancel]` — commit / drop the staged command
- `agent-fleet-chat` — LLM REPL ("大副" / First Mate); shells out to the `claude` CLI on `$PATH`
- `agent-fleet-demo`, `agent_fleet/smoke_test.py` — end-to-end demos against a real cmux

## Architecture

agent-fleet is a thin addressing + staging layer over [cmux](https://github.com/manaflow-ai/cmux). Read `docs/architecture.md` for the full picture (with mermaid diagrams) before non-trivial changes.

**Module roles** (everything lives in `agent_fleet/`):
- `cmux_control.py` — `CmuxClient` (shells out to the `cmux` CLI), `NicknameRegistry` (stable NATO phonetic names keyed by **surface UUID**, persisted to `~/.cache/agent-fleet/nicknames.json`, **never recycled**), `smart_status` (parses pane tail, skips banner/HUD, prefers `※ recap` / `✻ verb`), `resolve_target` (nickname / unambiguous prefix / 1-based int → surface UUID).
- `stager.py` — `RouteStager`: holds **at most one** pending `(target, text, staged_at)` slot with a TTL (default 60s, last-wins). Thread-safe via `threading.Lock`. `confirm()` takes-and-clears under the lock, then runs the blocking cmux send with the lock released so concurrent `stage`/`cancel` aren't blocked on subprocesses.
- `daemon.py` — asyncio Unix-socket server on `/tmp/agent-fleet.sock` (override `AGENT_FLEET_SOCKET`), socket is `0o600`, runs blocking cmux sends via `loop.run_in_executor` so the event loop never stalls.
- `board.py` — read-only viewer. On `--watch`, registers its own surface UUID in `~/.cache/agent-fleet/board-surfaces/<uuid>` (removed via `atexit`) so it never lists itself. **Cross-window**: iterates `window.list` then per-window `workspace.list` — calling `workspace.list` bare only returns the caller's window.
- `say.py` — deterministic regex parser, same wire protocol as `chat.py`.
- `chat.py` — LLM REPL. Builds a board snapshot, sends to `claude --print` with a JSON schema, parses `{reply, actions[]}` envelope, dispatches `stage`/`confirm`/`cancel` actions. To swap the LLM backend: replace `_call_claude`.
- `confirm.py` — hot-path CLI for the captain's 👍 / 👎.
- `clawd.py` — opt-in Clawd character renderer for the board (Kitty / BlockArt / Pack).
- `fleet_layout.sh` — one-shot cmux layout (left: board pane; right: browser surface at `$FLEET_VOICE_URL`, default `http://localhost:3000`).

**Wire protocol** (newline-JSON, one request/response/close per connection):
- `{action:"stage_route", target, text}` → `{ok:true}` — `target` is nickname / unambiguous prefix / 1-based int. Legacy clients may send `session:int` instead of `target` — daemon falls back.
- `{action:"confirm_route"}` → `{ok:true, fired:bool}` — `fired:false` means nothing pending (TTL expired or already fired/cancelled).
- `{action:"cancel_route"}` → `{ok:true, fired:bool}`.

**Nickname resolution happens at fire time** in `confirm()`, not at `stage()` — the live board is always source of truth.

## Invariants worth preserving

- The **stage→confirm split is the safety gate**. Never short-circuit `stage_route` into an immediate send; `say.py -y` chains two protocol calls, it does not bypass.
- `NicknameRegistry` is append-only per registry file. Don't add a "recycle dead surfaces" path — a future surface inheriting `alpha` would silently misroute commands.
- The board self-exclusion contract relies on `~/.cache/agent-fleet/board-surfaces/<uuid>` markers; if you add a new long-running viewer, follow the same pattern.
- Core lib stays stdlib-only. Anything new that needs `rich`/`prompt_toolkit` belongs behind the `[repl]` extra.

## State locations

| Path | Lifetime | Holds |
| --- | --- | --- |
| `~/.cache/agent-fleet/nicknames.json` | persistent | `surface_uuid → nickname` |
| `~/.cache/agent-fleet/board-surfaces/<uuid>` | live pane | empty marker, written by `board.py --watch` |
| `/tmp/agent-fleet.sock` (or `$AGENT_FLEET_SOCKET`) | daemon | broker listen socket |
| `RouteStager._pending` (in-memory) | ≤ TTL | single staged command |
