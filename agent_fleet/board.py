"""Mac-side session board: numbered cmux sessions + a status line each.

  python -m agent_fleet.board          # one-shot text board
  python -m agent_fleet.board --watch  # live board, auto-refresh (glanceable)
  python -m agent_fleet.board --json   # machine-readable

The numbers shown here are what you say to the voice secretary ("two, run the
tests"). Status is each session's last non-empty screen line (via read-screen).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime

from agent_fleet.cmux_control import (  # noqa: E402
    BOARD_REGISTRY_DIR,
    CmuxClient,
    DEFAULT_CMUX,
)
from agent_fleet import clawd as _clawd  # noqa: E402


def build_board(client, sessions=None) -> list[dict]:
    """Return one row dict per cmux session.

    Pure of argv/printing — takes any object exposing list_sessions() plus
    either read_surface_details() (preferred) or just read_surface(). Pass
    `sessions` to avoid a redundant `cmux workspace.list` round-trip when the
    caller already fetched them (e.g. the watch loop after a title sync).
    Each row carries:
      nickname, number, title, cwd, selected      # session identity
      activity, response, prompt, recap, hud      # rich card fields
      status                                       # legacy single line (smart-status)
    """
    rows = []
    if sessions is None:
        sessions = client.list_sessions()
    for s in sessions:
        details = None
        status = ""
        if hasattr(client, "read_surface_details"):
            try:
                details = client.read_surface_details(s.surface)
            except Exception:
                details = None
        if hasattr(client, "read_surface"):
            try:
                status = client.read_surface(s.surface)
            except Exception:
                status = ""
        rows.append({
            "nickname": s.nickname,
            "number": s.number,
            "title": s.title,
            "cwd": s.cwd,
            "selected": s.selected,
            "activity": getattr(details, "activity", ""),
            "response": getattr(details, "response", ""),
            "prompt":   getattr(details, "prompt", ""),
            "recap":    getattr(details, "recap", ""),
            "hud":      getattr(details, "hud", ""),
            "tail":     tuple(getattr(details, "tail", ())),
            "status":   status,
        })
    return rows


def render_text(rows: list[dict]) -> str:
    if not rows:
        return "(no cmux sessions)"
    lines = []
    for r in rows:
        mark = "*" if r["selected"] else " "
        nick = (r.get("nickname") or "").ljust(8)
        lines.append(f"{mark} {nick}{r['title'][:38]:38}  {r['status'][:48]}")
    return "\n".join(lines)


# --- live watch board ------------------------------------------------------

# Default board width when no terminal is attached (JSON output, pipes, tests).
# The watch loop overrides this from the live terminal size each frame so the
# board fills the pane and status lines don't get clipped at 50 chars.
_WIDTH = 80
_MIN_WIDTH = 56
_MAX_WIDTH = 140

# Minimum body rows per ship card (excluding L1 title). Bare-shell ships
# (no Claude signals, no tail) would otherwise collapse to a single cwd line
# and look ragged next to full Claude cards; padding evens the grid.
_MIN_CARD_HEIGHT = 4

# ANSI sequences. Truncation is always computed on the plain visible text so
# fixed-width columns line up; colors are wrapped around the already-sized
# segments.
_CLEAR    = "\033[2J\033[H"   # clear screen + home cursor
_HIDE     = "\033[?25l"
_SHOW     = "\033[?25h"
_RESET    = "\033[0m"
_BOLD     = "\033[1m"
_DIM      = "\033[2m"
_REVERSE  = "\033[7m"
_FG_CYAN     = "\033[36m"
_FG_GREEN    = "\033[32m"
_FG_YELLOW   = "\033[33m"
_FG_BLUE     = "\033[34m"
_FG_MAGENTA  = "\033[35m"

# Per-status-glyph color (what each Claude Code signal "means" at a glance).
_STATUS_COLOR = {
    "✻": _FG_YELLOW,   # actively thinking
    "⏺": _FG_GREEN,    # just spoke
    "❯": _FG_BLUE,     # user prompt
    ">": _FG_BLUE,
    "※": _DIM,         # idle recap (most muted on purpose)
}


def _short_cwd(cwd: str) -> str:
    home = os.path.expanduser("~")
    return "~" + cwd[len(home):] if cwd.startswith(home) else cwd


def _wrap(s: str, *codes: str) -> str:
    """Wrap `s` in the given ANSI codes (no-op if `s` empty)."""
    if not s:
        return s
    return "".join(codes) + s + _RESET


_INDENT = "     "  # 5 spaces — under "▶ alpha " column (unfocused body rows)
# Focused cards swap the first space for a cyan `│`, so the focus indicator
# extends down the full card instead of dying at the L1 nickname. Same total
# width as `_INDENT`, so columns still line up.
_INDENT_FOCUS = "│    "


def _truncate(s: str, max_w: int) -> str:
    """Truncate a plain-text string to `max_w` visible chars, adding `…` if cut."""
    return s if len(s) <= max_w else s[: max(0, max_w - 1)] + "…"


# ── visual-width helpers ───────────────────────────────────────────────
# Terminal columns ≠ Python char count when CJK / emoji are involved: each
# wide char eats 2 columns. The old `_truncate` + `ljust` math was sized in
# code points, so a card with a Chinese title pushed the right-hand HUD past
# the pane edge and wrapped (e.g. hotel's `… s\nn 20.6h`). These helpers do
# the same operations in terminal columns.
import unicodedata


def _vis_width(s: str) -> int:
    """Approximate the number of terminal columns `s` will occupy.

    Wide / Fullwidth chars (most CJK, fullwidth punctuation) count as 2;
    plane-1 symbols (emoji range) also 2; everything else 1. Inputs here are
    always pre-ANSI (sizing happens before wrapping in escape codes), so we
    don't need to strip escapes.
    """
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        elif ord(ch) >= 0x1F300:  # emoji / pictograph range
            w += 2
        else:
            w += 1
    return w


def _truncate_vis(s: str, max_w: int) -> str:
    """Truncate `s` so its visual width is ≤ `max_w`, suffixing `…` if cut."""
    if _vis_width(s) <= max_w:
        return s
    out = ""
    w = 0
    # Reserve 1 col for the ellipsis.
    budget = max(0, max_w - 1)
    for ch in s:
        cw = 2 if (unicodedata.east_asian_width(ch) in ("W", "F")
                   or ord(ch) >= 0x1F300) else 1
        if w + cw > budget:
            break
        out += ch
        w += cw
    return out + "…"


def _ljust_vis(s: str, max_w: int) -> str:
    """Pad `s` with spaces on the right until its visual width is `max_w`."""
    pad = max(0, max_w - _vis_width(s))
    return s + (" " * pad)


def _counts_line(rows: list[dict], daemon_reply: "Optional[dict]" = None) -> str:
    """Footer status: `N ships · K focused [· staged-fragment]`.

    `daemon_reply` is the daemon's `status_route` JSON, or None when the
    daemon wasn't reachable. Tri-state on purpose:
      - None                              → daemon down / not queried: drop the staged segment.
      - {"ok":True, "staged": None}       → daemon up, nothing pending: `0 staged`.
      - {"ok":True, "staged": {...}}      → daemon up, something staged: `1 staged: alpha (4s)`.
    """
    n = len(rows)
    focused = sum(1 for r in rows if r.get("selected"))
    ship_word = "ship" if n == 1 else "ships"
    base = f"{n} {ship_word} · {focused} focused"
    if not daemon_reply or not daemon_reply.get("ok"):
        return base
    staged = daemon_reply.get("staged")
    if staged is None:
        return f"{base} · 0 staged"
    target = staged.get("target") or "?"
    age = staged.get("age_s") or 0.0
    return f"{base} · 1 staged: {target} ({age:.0f}s)"


def render_board(rows: list[dict], width: int = _WIDTH, color: bool = True,
                 renderer: "Optional[_clawd.ClawdRenderer]" = None,
                 daemon_reply: "Optional[dict]" = None) -> str:
    """Rich multi-line card per session.

    Each card:
      L1  ▶ <nickname>   <title>           [HUD right-aligned, if present]
      L2  ➜ <cwd>                                         (dim)
      L3  ❯ <last user prompt>                            (if any, blue)
      L4  ⏺ <last assistant response>                     (if any, green)
      L5  ✻ <current activity verb>                       (if any, yellow)
      L*  ※ <recap>                                       (only when L3-L5 all empty)

    When `renderer` is supplied (Kitty-graphics terminal + clawd-on-desk
    assets), a small live Clawd image sits at the left of each card and the
    text is right-positioned past it via ANSI cursor moves. Otherwise an
    emoji glyph stands in for the Clawd (zero-graphics fallback).

    `color=False` drops ANSI so the output is plain (tests, pipes, non-TTY).
    """
    bar_plain = "─" * width
    clock = datetime.now().strftime("%H:%M:%S")
    title = "FLEET BOARD"

    # Box-corner header: `┌─ FLEET BOARD ──── 14:32:05 ─┐`. No side rails on
    # body rows (the renderer cards / image columns would fight them); top
    # and bottom corners alone are enough to bracket the board visually.
    inner_w = max(0, width - 2)  # space between corners
    label = f" {title} "
    clock_seg = f" {clock} "
    fill_w = max(0, inner_w - len(label) - len(clock_seg))
    header_plain = "┌" + label + ("─" * fill_w) + clock_seg + "┐"
    out: list[str] = []
    if color:
        out.append(
            f"{_DIM}┌{_RESET}{_BOLD} {title} {_RESET}"
            f"{_DIM}{'─' * fill_w}{_RESET}"
            f"{_DIM} {clock} ┐{_RESET}"
        )
    else:
        out.append(header_plain)

    if not rows:
        out.append(_wrap("  (no cmux sessions)", _DIM) if color else "  (no cmux sessions)")

    # When a Clawd renderer is present, text is laid out beside the image
    # (left margin = renderer.indent_cols). Without, the title sits at col 1
    # and content rows have the legacy 5-space indent.
    text_offset = renderer.indent_cols if renderer else 0

    for i, r in enumerate(rows):
        sel = bool(r["selected"])
        nick = (r.get("nickname") or "?").ljust(8)
        focus_mark = "▶" if sel else " "
        hud = (r.get("hud") or "").strip()
        cwd = _short_cwd(r.get("cwd") or "")

        # ── L1 (title): focus + nickname + title  [HUD right-aligned]
        # CJK / emoji chars in the title take 2 columns each; sizing must be
        # in visual columns (not code points) or the HUD chip gets pushed off
        # the pane and wraps to a second line (the hotel `s\nn 20.6h` bug).
        lead_visible = 2 + _vis_width(nick)
        hud_visible = _vis_width(hud) if hud else 0
        max_title = max(8, width - text_offset - lead_visible - hud_visible - 1)
        title_trunc = _truncate_vis(r.get("title") or "", max_title)
        title_padded = _ljust_vis(title_trunc, max_title)
        if color:
            mark_c = f"{_BOLD}{_FG_GREEN}{focus_mark}{_RESET}" if sel else focus_mark
            nick_c = (f"{_REVERSE}{_BOLD}{_FG_CYAN}{nick}{_RESET}"
                      if sel else f"{_BOLD}{_FG_CYAN}{nick}{_RESET}")
            hud_c = _wrap(hud, _DIM, _FG_MAGENTA) if hud else ""
            l1 = f"{mark_c} {nick_c}{title_padded}{hud_c}"
        else:
            l1 = f"{focus_mark} {nick}{title_padded}{hud}"

        # ── L2 (cwd) + L3+ (glyph rows) — content only, no leading indent.
        cwd_content = _wrap(f"➜ {cwd}", _DIM) if color else f"➜ {cwd}"
        max_status = max(20, width - text_offset - len(_INDENT) - 2)
        glyph_rows = [
            ("prompt",   r.get("prompt") or ""),
            ("response", r.get("response") or ""),
            ("activity", r.get("activity") or ""),
        ]
        body_contents: list[str] = [cwd_content]
        any_live = False
        for _kind, line in glyph_rows:
            if not line:
                continue
            any_live = True
            s_trunc = _truncate_vis(line, max_status)
            head = s_trunc[:1]
            disp = _wrap(s_trunc, _STATUS_COLOR.get(head, _DIM)) if color else s_trunc
            body_contents.append(disp)
        recap = r.get("recap") or ""
        if not any_live and recap:
            s_trunc = _truncate_vis(recap, max_status)
            body_contents.append(_wrap(s_trunc, _DIM) if color else s_trunc)

        # ── Raw tail (B): last few non-glyph lines, dim. Fills the card with
        # actual recent output (shell echoes, build progress) the curated
        # signals above don't show — and turns lima-style bare-shell cards
        # from 2 lines into something glanceable.
        for tline in (r.get("tail") or ()):
            t_trunc = _truncate_vis(tline, max_status)
            body_contents.append(_wrap(t_trunc, _DIM) if color else t_trunc)

        # ── Min-height pad (E): every card is at least MIN_CARD_HEIGHT body
        # rows so lima-style bare-shell ships line up with full Claude cards
        # and the grid doesn't look ragged.
        while len(body_contents) < _MIN_CARD_HEIGHT:
            body_contents.append("")

        # ── Emit. Renderer (Kitty or BlockArt) composes image alongside text;
        # without one we keep the legacy text-only layout (title at col 1,
        # content rows 5-space-indented).
        if renderer is not None:
            state = _clawd.state_for(r.get("activity") or "", r.get("response") or "",
                                     r.get("prompt") or "",   r.get("recap") or "")
            out.extend(renderer.render_card(state, [l1] + body_contents))
        else:
            out.append(l1)
            # Focused card: colored `│` left bar on every body row so the
            # focus indicator extends down the whole card, not just L1.
            indent = (_wrap(_INDENT_FOCUS, _BOLD, _FG_CYAN) if (color and sel)
                      else _INDENT)
            for c in body_contents:
                out.append(f"{indent}{c}")

        # Thin separator between ships (not after the last one).
        if i < len(rows) - 1:
            out.append(_wrap(bar_plain, _DIM) if color else bar_plain)

    # Status bar + box-corner footer mirror the header.
    counts = _counts_line(rows, daemon_reply)
    hint = 'say "alpha <cmd>" / "bravo …"  →  👍  /  confirm.py'

    def _segment_line(left_cap: str, right_cap: str, content: str) -> str:
        """`<left> <content> ─...─ <right>` clipped/padded to `width` (visual cols).

        Uses visual width — the footer hint contains `👍` (emoji, 2 cols) and
        `→` (1 col but non-ASCII); sizing in code points would push the
        right-hand `┘` corner one column past the pane edge.
        """
        inner = max(0, width - 2)
        body = f" {content} "
        if _vis_width(body) > inner:
            body = _truncate_vis(body, inner)
        fill = "─" * max(0, inner - _vis_width(body))
        return f"{left_cap}{body}{fill}{right_cap}"

    if color:
        out.append(
            f"{_DIM}├{_RESET} {_BOLD}{counts}{_RESET} "
            f"{_DIM}{'─' * max(0, width - 4 - _vis_width(counts))}┤{_RESET}"
        )
        out.append(_wrap(_segment_line("└", "┘", hint), _DIM))
    else:
        out.append(_segment_line("├", "┤", counts))
        out.append(_segment_line("└", "┘", hint))
    return "\n".join(out)


def register_self_as_board(surface_id: str) -> None:
    """Touch a marker file so the enumerator skips this pane.

    cmux overwrites surface titles based on rendered content (and ignores OSC
    escape sequences), so the title-marker fallback alone misses the live board
    pane once the watcher starts drawing frames. The registry under
    BOARD_REGISTRY_DIR is the durable signal — one empty file per live board
    pane, keyed by surface UUID. Removed via atexit on clean shutdown.
    """
    import atexit
    sid = (surface_id or "").strip()
    if not sid:
        return
    BOARD_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    marker = BOARD_REGISTRY_DIR / sid
    try:
        marker.touch(exist_ok=True)
    except OSError:
        return
    atexit.register(lambda: marker.unlink(missing_ok=True))


def _query_daemon_status() -> "Optional[dict]":
    """Best-effort `status_route` query — returns the parsed reply or None.

    Failure modes (daemon not running, stale socket, JSON error, timeout) all
    collapse to None so the watch loop can render the rest of the board even
    when the daemon's down. Short timeout because this runs on every tick.
    """
    import socket as _socket
    sock_path = os.environ.get("AGENT_FLEET_SOCKET", "/tmp/agent-fleet.sock")
    try:
        s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        s.settimeout(0.3)
        s.connect(sock_path)
        s.sendall(b'{"action": "status_route"}\n')
        resp = s.recv(4096).decode().strip()
        s.close()
    except OSError:
        return None
    try:
        return json.loads(resp) if resp else None
    except json.JSONDecodeError:
        return None


def _term_width() -> int:
    """Live terminal width, clamped to a sensible range for the board."""
    cols = shutil.get_terminal_size((_WIDTH, 24)).columns
    return max(_MIN_WIDTH, min(_MAX_WIDTH, cols - 2))


def watch(client, interval: float = 2.0, color: bool = True,
          self_surface: str = "") -> None:
    """Re-render the board every `interval` seconds until Ctrl-C.

    Pass `self_surface` (this pane's cmux surface UUID, supplied by the
    launcher) so the enumerator excludes this pane from the session list.
    Board width is sampled from the live terminal each frame so the layout
    follows pane resizes. When the terminal speaks the Kitty graphics
    protocol AND clawd-on-desk assets are available, a small live Clawd is
    embedded in each card (env: AGENT_FLEET_CLAWD, AGENT_FLEET_CLAWD_ASSETS).
    """
    register_self_as_board(self_surface)
    renderer = _clawd.maybe_renderer() if color else None
    if renderer is not None:
        renderer.preload()  # avoid first-frame stutter from cold PNG decode
    sync_titles = os.environ.get("AGENT_FLEET_SYNC_TITLES", "1") != "0"
    try:
        if color:
            sys.stdout.write(_HIDE)
        while True:
            # Fetch sessions once per tick so the workspace-title sync and the
            # board render see the same snapshot (and we save one cmux RPC).
            sessions = client.list_sessions()
            if sync_titles:
                try:
                    client.sync_workspace_titles(sessions)
                except Exception:
                    pass  # one bad rename never sinks the watch loop
            board = render_board(build_board(client, sessions=sessions),
                                 width=_term_width(),
                                 color=color, renderer=renderer,
                                 daemon_reply=_query_daemon_status())
            sys.stdout.write(_CLEAR + board + "\n")
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        if color:
            sys.stdout.write(_SHOW)
            sys.stdout.flush()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--watch", action="store_true", help="live auto-refreshing board")
    ap.add_argument("--interval", type=float, default=2.0, help="--watch refresh seconds")
    ap.add_argument("--self-surface", default=os.environ.get("CONTROL_PLANE_BOARD_SURFACE", ""),
                    help="this pane's cmux surface UUID (so the board excludes itself)")
    args = ap.parse_args()

    cmux = shutil.which("cmux") or DEFAULT_CMUX
    if not os.path.exists(cmux):
        print("cmux not installed")
        return 0

    client = CmuxClient(binary=cmux)
    if args.watch:
        watch(client, interval=args.interval, color=sys.stdout.isatty(),
              self_surface=args.self_surface)
        return 0

    rows = build_board(client)
    print(json.dumps(rows, indent=2) if args.json else render_text(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
