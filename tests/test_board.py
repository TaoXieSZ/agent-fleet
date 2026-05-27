"""Tests for the board's pure render helpers (no cmux required)."""

from agent_fleet.board import _counts_line, _vis_width, _truncate_vis


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
