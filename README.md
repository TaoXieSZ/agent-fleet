# agent-fleet

> Hands-free control plane for a fleet of coding agents. Drive Claude Code /
> Cursor sessions running in [cmux](https://github.com/manaflow-ai/cmux) by
> voice or keyboard, with stable per-ship nicknames so addressing never drifts.

```
舰长 ❯ alpha 跑 pytest
大副 ❯ alpha：pytest，舰长。   ✓ stage[alpha] ✓ confirm·fired
```

You name a ship, give an order, the daemon types the verbatim command into
the right cmux pane on your confirm. No retyping, no window-hopping, no
hunting for the right tab.

> 📐 **Architecture:** see [`docs/architecture.md`](docs/architecture.md) for
> diagrams of the system, the stage→confirm flow, the board read loop, and
> the wire protocol.

---

## Why this exists

You run many coding agents at once — a Claude Code on one repo, a Cursor on
another, a deploy shell, a test watcher. Driving them means constant
keyboard + window-switching, and cmux's positional `workspace:N` / `surface:N`
refs **shift as panes open and close**, so any "session 3" rule is broken
the moment you split a pane.

agent-fleet fixes the addressing layer:

- Every cmux terminal pane gets a stable **NATO phonetic nickname** (alpha,
  bravo, charlie, …) keyed by the surface UUID. That name is yours for the
  pane's lifetime; open or close anything else and `alpha` is still `alpha`.
- The board **spans all cmux windows**, so popping the board into its own
  window doesn't hide your agents.
- Each board row shows what the ship is **actually doing** — Claude Code's
  recap or activity verb — not the static "bypass permissions" banner.
- An LLM REPL ("**大副**", First Mate) speaks the same protocol, so you can
  talk in natural language and it picks the focused ship by default.

## Sample board (live, 2-second refresh)

```
FLEET BOARD                                     14:32:05
────────────────────────────────────────────────────────
  alpha   OpenSourceProjects · hi   ➜ ~/repos/app
        ※ recap: Investigating the deploy failure on c081
* bravo   tools · test-runner       ➜ ~/repos/lib
        ✻ Brewed for 7s
  charlie deploy-bot                ➜ ~/repos/infra
        ⏺ Pushed to staging — health check green.
────────────────────────────────────────────────────────
say "alpha <cmd>" / "bravo …"  →  👍  /  confirm.py
```

`*` = focused. Status pulled from the pane's own output, with banners and
HUDs filtered out.

## Quick start

```bash
git clone https://github.com/TaoXieSZ/agent-fleet
cd agent-fleet
pip install -e '.[repl]'

# 1. Daemon (one terminal — keep it running)
agent-fleet-daemon

# 2. Live board (another terminal — keep it visible)
agent-fleet-board --watch

# 3. Drive it
agent-fleet-say -y "alpha echo hello"            # stage + auto-confirm
agent-fleet-say "alpha echo hello"               # stage only → confirm separately
agent-fleet-confirm                              # commit the staged order
agent-fleet-confirm cancel                       # drop it

# 4. Or use the LLM REPL (uses your `claude` CLI for free, no extra key)
agent-fleet-chat
舰长 ❯ bravo 跑 pytest
大副 ❯ bravo：pytest，舰长。
舰长 ❯ 再跑一次                                   # 大副 remembers "bravo" from context
大副 ❯ 默认走 bravo：pytest，舰长。
```

## One-window layout

`fleet_layout.sh` assembles a cmux workspace = live board pane + a browser
surface (set `$FLEET_VOICE_URL`, default `http://localhost:3000`). Your
coding-agent sessions stay as the other cmux workspaces/tabs:

```bash
agent_fleet/fleet_layout.sh
```

The board pane self-registers so it isn't listed as a ship.

## Concepts

| Term | Meaning |
| --- | --- |
| **Ship** | A cmux terminal pane (one Claude Code / Cursor / shell session). |
| **Nickname** | A stable NATO phonetic name (`alpha`…`zulu`) for each ship. |
| **舰长 (Captain)** | You. |
| **大副 (First Mate)** | The LLM persona in `chat.py` that turns your prose into routing actions. |
| **Daemon** | The Unix-socket broker that holds at most one staged command and fires it on confirm. The stage→confirm split is the safety gate. |

Nicknames persist in `~/.cache/agent-fleet/nicknames.json` keyed by surface
UUID and are **never recycled** within the same registry — a closed pane's
name stays retired, so a new pane never inherits a stale association.

## Daemon protocol

Newline-delimited JSON over a Unix socket
(default `/tmp/agent-fleet.sock`, override with `AGENT_FLEET_SOCKET`):

```json
{"action": "stage_route", "target": "alpha", "text": "pytest"}
  → {"ok": true}

{"action": "confirm_route"}
  → {"ok": true, "fired": true}

{"action": "cancel_route"}
  → {"ok": true, "fired": true}
```

`target` is a nickname (`"alpha"`), an unambiguous prefix (`"alph"`), or — for
back-compat with older clients — a 1-based integer / digit string. Resolution
to a surface UUID happens at fire time, so the live board is always the
source of truth.

## Layout

```
agent_fleet/
  cmux_control.py   # enumerate ships across all windows; nicknames; smart status
  stager.py         # stage→confirm/cancel state machine (TTL, last-wins)
  daemon.py         # Unix-socket broker — the long-running process
  board.py          # text + live-watch fleet board
  say.py            # keyboard driver (parses "alpha 跑 ls" → stage)
  confirm.py        # confirm / cancel CLI (keyboard fallback for a gesture)
  chat.py           # Codex-style LLM REPL persona-driven by 大副 (First Mate)
  smoke_test.py     # safe real-cmux round-trip against a throwaway pane
  demo.py           # full board→stage→confirm→execute demo, throwaway target
  fleet_layout.sh   # one-shot cmux window layout (board pane + browser)
tests/              # 33 pure-Python unit tests, no cmux needed
```

## Status

**v0.1 alpha.** Extracted from
[`TaoXieSZ/claude-code-buddy`](https://github.com/TaoXieSZ/claude-code-buddy),
where it was prototyped as `tools/control_plane/` and integrated with a voice
front-end (Agora ConvoAI), camera-gesture confirm, and a desktop StackChan
peripheral. agent-fleet itself is **backend-agnostic** — anything that
speaks the daemon's JSON socket protocol is a client.

## Dependencies

- Core library: **none** (Python ≥ 3.10 standard library only).
- REPL extras (`pip install -e '.[repl]'`): `rich`, `prompt_toolkit`.
- Runtime: [cmux](https://github.com/manaflow-ai/cmux) as the terminal manager.
- Optional LLM in REPL: the `claude` CLI on `$PATH` (uses your Claude Code
  subscription via `--print --json-schema`; swap in any other backend by
  replacing one `_call_claude` function in `chat.py`).

## Tests

```bash
pip install -e '.[dev]'
pytest -q
```

## License

MIT — see [LICENSE](LICENSE).
