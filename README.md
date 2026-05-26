# agent-fleet

> Hands-free control plane for a fleet of coding agents — drive Claude Code /
> Cursor sessions running in [cmux](https://github.com/manaflow-ai/cmux) by
> voice or keyboard, with stable per-ship nicknames.

You run many coding agents in parallel (Claude Code / Cursor / Codex panes in
cmux). Driving them means constant keyboard + window-switching. **agent-fleet**
turns that into:

> 舰长 ❯ alpha 跑 pytest
> 大副 ❯ alpha：pytest，舰长。  · ✓ stage[alpha] ✓ confirm·fired

You name a ship, give an order, and a stable daemon routes the verbatim command
into the right cmux pane. No retyping, no window-hopping.

## Why nicknames

cmux's positional `workspace:N` / `surface:N` refs shift as panes open and
close. agent-fleet hands each terminal pane a NATO phonetic nickname (`alpha`,
`bravo`, `charlie`, …) keyed by the stable surface UUID. That name is yours
for the pane's lifetime — open or close anything else, `alpha` is still
`alpha`. The board, the LLM and your typed orders all use the nickname; the
positional number is hidden machinery.

## Status

**v0.1 alpha.** Extracted from
[`TaoXieSZ/claude-code-buddy`](https://github.com/TaoXieSZ/claude-code-buddy),
where it was prototyped as `tools/control_plane/`. Tested live against cmux on
macOS. Voice integration (Agora ConvoAI), camera-gesture confirm, and
StackChan peripheral are tracked separately in that fork; agent-fleet itself
is backend-agnostic — anything that speaks the daemon's JSON socket protocol
is a client.

## Concepts

- **Ship** — a cmux terminal pane (one Claude Code / Cursor / shell session).
- **Nickname** — a stable NATO phonetic name (`alpha` … `zulu`) for each
  ship; persisted in `~/.cache/agent-fleet/nicknames.json` keyed by surface
  UUID, never recycled within a registry.
- **Captain** — you.
- **大副 (First Mate)** — the LLM persona that turns your prose into routing
  actions; lives in `chat.py`.
- **Daemon** — a Unix-socket broker that holds at most one staged command
  and fires it when confirmed. The stage→confirm split is the safety gate.

## Quick start

```bash
# 1. Install (editable, with the REPL extras)
pip install -e '.[repl]'

# 2. Run the daemon (one terminal)
agent-fleet-daemon

# 3. See the fleet (another terminal)
agent-fleet-board                # one-shot
agent-fleet-board --watch        # live, 2s refresh

# 4. Drive it by typing (third terminal)
agent-fleet-say -y "alpha echo hello"          # stage + auto-confirm
agent-fleet-say  "alpha echo hello"            # stage only → 大副-style gate
agent-fleet-confirm                            # commit the staged order
agent-fleet-confirm cancel                     # drop it

# 5. Or use the LLM REPL (needs the `claude` CLI on PATH for v0)
agent-fleet-chat
舰长 ❯ alpha 跑 pytest
大副 ❯ alpha：pytest，舰长。  ✓ stage[alpha] ✓ confirm·fired
```

## The one-window layout

`fleet_layout.sh` assembles a cmux workspace = live board pane + a browser
surface (point at any voice front-end on `$FLEET_VOICE_URL`, default
`http://localhost:3000`). Your coding-agent sessions stay as the other cmux
workspaces in the window:

```bash
agent_fleet/fleet_layout.sh
```

The board now spans **all cmux windows**, so you can pop it out into its own
window without losing the agent enumeration.

## Daemon protocol (newline-delimited JSON over Unix socket)

```json
{"action": "stage_route", "target": "alpha", "text": "pytest"}
  → {"ok": true}

{"action": "confirm_route"}
  → {"ok": true, "fired": true}

{"action": "cancel_route"}
  → {"ok": true, "fired": true}
```

`target` may be a nickname (`alpha`), an unambiguous prefix (`alph`), or — for
back-compat with number-based clients — a 1-based integer / digit string.
Resolution to a surface UUID happens at fire time, so the live board is always
the source of truth.

## Layout

```
agent_fleet/
  cmux_control.py   # enumerate ships across all windows; route via surface UUID
  stager.py         # stage→confirm/cancel state machine (TTL, last-wins)
  daemon.py         # Unix-socket broker — the long-running process
  board.py          # text + live-watch fleet board
  say.py            # keyboard driver (parses "alpha 跑 ls" → stage)
  confirm.py        # confirm / cancel CLI (keyboard fallback for a gesture)
  chat.py           # Codex-style LLM REPL persona-driven by 大副 (First Mate)
  smoke_test.py     # safe real-cmux round-trip against a throwaway pane
  demo.py           # full board→stage→confirm→execute demo, throwaway target
  fleet_layout.sh   # one-shot cmux window layout (board pane + browser)
tests/              # pure-Python unit tests, no cmux needed
```

## Dependencies

Core lib: **none** (Python ≥ 3.10 standard library only).
REPL extras (`pip install -e '.[repl]'`): `rich`, `prompt_toolkit`.
Runtime: [cmux](https://github.com/manaflow-ai/cmux) (the terminal manager).
Optional LLM in REPL: the `claude` CLI on `$PATH` (uses your Claude Code
subscription via `--print --json-schema`).

## Tests

```bash
pip install -e '.[dev]'
pytest -q
```

## License

MIT — see [LICENSE](LICENSE).
