"""Tests for the board's pure render helpers (no cmux required)."""

from agent_fleet.board import (
    _counts_line, _vis_width, _truncate_vis,
    _metrics_line, _parse_hud_pcts,
)


def _row(selected: bool = False) -> dict:
    return {
        "nickname": "alpha", "number": 1, "title": "x", "cwd": "/",
        "selected": selected, "activity": "", "response": "", "prompt": "",
        "recap": "", "hud": "", "tail": (), "status": "",
    }


# ── _counts_line: daemon tri-state ──────────────────────────────────────

def test_counts_line_drops_staged_segment_when_daemon_unreachable():
    line = _counts_line([_row()], daemon_reply=None)
    assert line == "1 ship · 0 focused"
    assert "staged" not in line


def test_counts_line_shows_zero_staged_when_daemon_up_and_idle():
    line = _counts_line([_row(selected=True), _row()],
                        daemon_reply={"ok": True, "staged": None})
    assert line == "2 ships · 1 focused · 0 staged"


def test_counts_line_shows_target_and_age_when_pending():
    line = _counts_line([_row()],
                        daemon_reply={"ok": True,
                                      "staged": {"target": "alpha",
                                                 "text": "pytest",
                                                 "age_s": 4.7}})
    assert line == "1 ship · 0 focused · 1 staged: alpha (5s)"


def test_counts_line_treats_daemon_error_as_unreachable():
    # `ok: false` (daemon replied with an error) → drop the segment rather
    # than print a lie. Same behaviour as `daemon_reply=None`.
    line = _counts_line([_row()],
                        daemon_reply={"ok": False, "error": "boom"})
    assert "staged" not in line


# ── visual-width helpers ────────────────────────────────────────────────

def test_vis_width_counts_cjk_as_two_cols():
    # ASCII = 1 col each; CJK = 2.
    assert _vis_width("abc") == 3
    assert _vis_width("检查") == 4
    assert _vis_width("a检b") == 4


def test_truncate_vis_respects_visual_width_not_char_count():
    # 5 CJK chars = 10 visual cols; cap at 6 cols → 2 CJK + ellipsis = 5 cols.
    s = "检查一下我"
    out = _truncate_vis(s, 6)
    assert _vis_width(out) <= 6
    assert out.endswith("…")


# ── _metrics_line: fleet-wide aggregate ─────────────────────────────────

def _r(nick: str, hud: str = "", **flags) -> dict:
    base = _row()
    base.update({"nickname": nick, "hud": hud, **flags})
    return base


def test_parse_hud_pcts_extracts_ctx_5h_wk_and_ignores_sn():
    assert _parse_hud_pcts("ctx 5% · 5h 24% · wk 5% · sn 17.8h") == {
        "ctx": 5, "5h": 24, "wk": 5,
    }
    assert _parse_hud_pcts("") == {}


def test_metrics_line_reports_top_5h_and_ctx_with_owning_ship():
    rows = [
        _r("alpha", hud="ctx 5% · 5h 24%", activity="✻ x"),
        _r("bravo", hud="ctx 10% · 5h 8%"),
        _r("charlie", hud=""),  # no HUD reported
    ]
    line = _metrics_line(rows)
    # bravo wins ctx (10% > 5%); alpha wins 5h (24% > 8%).
    assert "1/3 active" in line
    assert "5h max 24% (alpha)" in line
    assert "ctx max 10% (bravo)" in line


def test_metrics_line_empty_when_nothing_to_say():
    # No HUDs anywhere AND no live signals → drop the row entirely rather
    # than print a useless "0/N active".
    assert _metrics_line([_r("a"), _r("b")]) == ""
    assert _metrics_line([]) == ""


def test_metrics_line_kept_when_only_signals_no_hud():
    # Live signal present but no HUD → still worth showing the active count.
    assert _metrics_line([_r("a", activity="✻ x"), _r("b")]) == "1/2 active"
