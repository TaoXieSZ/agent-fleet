# Changelog

Notable changes to agent-fleet. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Project is still
pre-1.0 so all entries live under **Unreleased** for now.

## [Unreleased]

### Added (2026-05-27 board v2 — opt-board-tui closeout)

- **Nickname → workspace title sync** (`cmux_control.compute_workspace_renames`
  + `CmuxClient.sync_workspace_titles`, called by `board.watch` per tick,
  [718e2c5](https://github.com/TaoXieSZ/agent-fleet/commit/718e2c5)).
  cmux exposes `workspace.rename` but no `surface.rename`, so the per-
  surface nickname is pushed into the owning workspace's title as
  `"alpha · <original>"`. Only single-ship workspaces are renamed
  (multi-pane is ambiguous, skipped in v1). Idempotent via
  `_strip_nick_prefix` so opening the board twice doesn't accumulate
  `alpha · alpha · …`. Visible in cmux's workspace sidebar / switcher
  (the top tab strip shows *surface* titles, which cmux exposes no RPC
  to rename). Disable with `AGENT_FLEET_SYNC_TITLES=0`.

- **Box-corner TUI + status bar** ([718e2c5]). Header
  `┌─ FLEET BOARD ─── 14:32:05 ─┐`, footer
  `└─ say "alpha <cmd>" / "bravo …"  →  👍  /  confirm.py ─┘`, and a
  status bar between body and footer:
  `├ N ships · K focused · 0 staged ┤`.

- **Full-card focus accent** ([718e2c5]). Focused card body rows are
  prefixed with a bold cyan `│` so the focus indicator extends down
  the whole card instead of dying at the L1 nickname (`_INDENT_FOCUS`).

- **Per-card tail preview + min-height padding** ([718e2c5]).
  `PaneDetails.tail` carries the last 3 non-glyph lines of each pane,
  dimmed below the curated signals. Bare-shell ships (lima-style) gain
  visible context instead of collapsing to one cwd line.
  `_MIN_CARD_HEIGHT = 4` keeps the grid lined up.

- **Visual-width-aware truncation (CJK / emoji)** ([718e2c5]).
  `_vis_width` / `_truncate_vis` / `_ljust_vis` use
  `unicodedata.east_asian_width` to size in terminal columns instead of
  code points. Fixes the HUD chip wrap on CJK-titled cards (the
  `hotel s\nn 20.6h` bug) and aligns the footer `┘` corner with the
  `👍` emoji (was off by one column).

- **`status_route` daemon action + 0-staged segment**
  (`stager.RouteStager.status()`, `daemon.status_route`,
  `board._query_daemon_status`, [718e2c5]). New socket action returns
  `{"ok":true, "staged": {target, text, age_s}|null}`. Board queries
  per tick (0.3s timeout, fail-quiet) and folds into the counts line:
  daemon down → segment dropped; idle → `0 staged`; pending →
  `1 staged: alpha (4s)`.

- **Global metrics row** ([c60594a](https://github.com/TaoXieSZ/agent-fleet/commit/c60594a)).
  One dense line under the top border:
  `⚡ K/N active · 5h max X% (ship) · ctx max X% (ship)`. Surfaces top
  rate-limit / context-window consumer at a glance.
  `_parse_hud_pcts` extracts %s from each card's HUD chip; row is
  dropped when there's nothing useful to aggregate.

- **Startup banner** ([c60594a]). One-line sanity check before the
  watch loop's first `_CLEAR`:
  `⚓ agent-fleet v0.1.0 · 5 ships detected · daemon ok`.
  Disable with `AGENT_FLEET_BANNER=0`.

- **CLAUDE.md** ([bf33bde](https://github.com/TaoXieSZ/agent-fleet/commit/bf33bde)).
  Project guide for future Claude Code sessions: commands, per-module
  architecture, wire protocol, invariants, state locations.

### Added (2026-05-26 / 27)

- **Opt-in Clawd character renderer** (`agent_fleet/clawd.py`,
  [376fda1](https://github.com/TaoXieSZ/agent-fleet/commit/376fda1)).
  Three renderer flavours, none active by default:
  - `PackRenderer` — palette-indexed sprite packs (TeXmeijin
    `claude-code-mascot-statusline` schema) → truecolor `▀` half-block
    ANSI; multi-frame animation cycles on wall clock. Pure-data, no
    Pillow.
  - `KittyRenderer` — Kitty graphics protocol (Ghostty.app / kitty /
    WezTerm / iTerm2 ≥ 3.5). Reads clawd-on-desk GIFs via Pillow with
    bbox auto-crop; image-IDs reused on redraw (first transmit ~3 KB,
    subsequent placements ~30 B).
  - `BlockArtRenderer` — same `▀` half-block rendering, larger
    clawd-on-desk GIF assets.

  Wired into `board.render_board` via `renderer.render_card(state,
  text_lines)`. Default `maybe_renderer()` → `None`; opt in via
  `AGENT_FLEET_CLAWD=pack | kitty | block`. cmux self-reports
  `TERM_PROGRAM=ghostty` but silently eats Kitty APC escapes — detected
  via `CMUX_SURFACE_ID` env and excluded from the Kitty path.

- **Rich multi-line cards + OMC HUD chip**
  ([2203470](https://github.com/TaoXieSZ/agent-fleet/commit/2203470)).
  Each session is now a 3-5 line card: focus + nickname + title (with
  right-aligned OMC HUD `ctx X% · 5h Y% · sn Zh`) · cwd · prompt ·
  response · activity verb. Recap (`※`) only shown when no live signal
  in the tail. PaneDetails + `_extract_details()` walk the surface tail
  once per pane and structure the signals; `_parse_hud()` reformats the
  raw OMC HUD line.

- **Colored ANSI render**
  ([fcf732e](https://github.com/TaoXieSZ/agent-fleet/commit/fcf732e)).
  Visual hierarchy: nicknames bold cyan (reverse-video chip on focus),
  ▶ focus mark bold green, status glyphs colored by meaning (✻ yellow,
  ⏺ green, ❯ blue, ※ dim), cwd/separators/footer dim grey.

- **Live signals beat ※ recap** + **adaptive board width**
  ([341826e](https://github.com/TaoXieSZ/agent-fleet/commit/341826e)).
  Smart-status walker prefers the most recent live signal (✻/⏺/❯) over
  the static recap Claude Code renders below the conversation. Half-
  rendered spinner frames (`✻ C`) filtered as noise. Board width samples
  the live terminal each frame (clamped 56..140).

- **Smart status line**
  ([852cb34](https://github.com/TaoXieSZ/agent-fleet/commit/852cb34)).
  Skips Claude Code's persistent bottom banner, OMC HUD, separator
  rules; prefers `※` recap or `✻` activity verb when present.

- **Excalidraw architecture diagrams + Chinese README**
  ([576f8f5](https://github.com/TaoXieSZ/agent-fleet/commit/576f8f5)).
  `docs/diagrams/{01-system-view,02-stage-confirm-sequence,03-board-read-loop}.excalidraw`
  generated by `docs/diagrams/generate.py` (re-runnable). README
  rewritten in Chinese with the 舰长 / 大副 vocabulary.

- **Architecture document**
  ([951a4aa](https://github.com/TaoXieSZ/agent-fleet/commit/951a4aa)).
  `docs/architecture.md` with three mermaid diagrams (system view,
  stage→confirm sequence, board read loop), wire protocol, where state
  lives, concurrency model, extension points, non-goals.

- **v0.1 baseline**
  ([a6d789d](https://github.com/TaoXieSZ/agent-fleet/commit/a6d789d)).
  Extracted from
  [claude-code-buddy](https://github.com/TaoXieSZ/claude-code-buddy)'s
  `tools/control_plane/` into an installable Python package. Standalone
  daemon (`agent_fleet/daemon.py`, Unix socket at
  `/tmp/agent-fleet.sock`, env `AGENT_FLEET_SOCKET` overrides). 33
  unit tests pass; smoke + demo round-trip works against real cmux.

### Concept-level decisions

- A "session" is a cmux **terminal surface (pane)** addressed by a
  stable **NATO phonetic nickname** keyed by surface UUID. Numbers
  retained for back-compat only. Names persist in
  `~/.cache/agent-fleet/nicknames.json` and are **never recycled**
  within a registry.
- Cross-window enumeration: `CmuxClient.list_sessions` fans out via
  `cmux rpc window.list` so panes in other cmux windows are visible.
- Board self-exclusion: each `board.py --watch` writes its own
  surface UUID into `~/.cache/agent-fleet/board-surfaces/<uuid>` at
  start and `atexit`-removes it — cmux mangles surface titles so a
  title-marker fallback alone misses the running board.
- LLM REPL (`agent-fleet-chat`) is backed by `claude --print
  --output-format json --json-schema` so it uses the user's Claude
  Code subscription with no extra key. Persona = **大副 (First
  Mate)** addressing the **舰长 (Captain)**.

## Roadmap

Tracked as session TODOs (`opt-board-tui` ✅, `hook-voice`,
`build-dashboard`):

1. ~~**Board visual polish** — bring the terminal board up to Claude
   Code CLI tier: box drawing borders, full-row focus highlight,
   bottom command-hint bar, optional startup banner, compact status
   bar (`N ships · 1 focused · 0 staged`).~~ **Done 2026-05-27** —
   see the 2026-05-27 entries above. All five sub-items shipped;
   plus per-card tail preview, visual-width-aware CJK truncation,
   and a global metrics row that wasn't on the original list.
2. **End-to-end voice path** — wire buddy-voice / Agora ConvoAI
   Path B through to the live daemon socket. Backend protocol is
   ready; the parser + persona already support nicknames + two-step
   dictation. Needs a live verify pass (speak → daemon log shows
   `stage_route` → 大副 reads back → confirm → cmux executes).
3. **Real Dashboard** — graduate beyond terminal cells. Per-session
   rich card with real Clawd animation, token / cost progress bar,
   click-to-confirm. Probably a new page in the buddy-voice repo
   (Next.js) or a standalone Tauri app. Speaks the same daemon
   socket protocol.

## License

Code: MIT (see [LICENSE](LICENSE)).

The Clawd renderer scaffolding can load assets from
[clawd-on-desk](https://github.com/AnthropicLabs/clawd-on-desk) —
those artworks are **NOT** bundled (upstream is "All Rights Reserved,
personal use only" per its `assets/LICENSE`). The
TeXmeijin pixel-buddy pack format is MIT and was prototyped briefly
but not shipped; the format spec is implemented in `PackRenderer` for
users who want to drop their own MIT-licensed packs in.
