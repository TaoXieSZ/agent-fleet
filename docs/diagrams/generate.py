#!/usr/bin/env python3
"""Generate the agent-fleet architecture .excalidraw files.

Hand-writing Excalidraw JSON for 3 diagrams (≈3000 lines) is error-prone, so
this script builds them with tiny helpers (rect / text / arrow). Re-run to
regenerate after layout tweaks; the .excalidraw outputs are committed
alongside so people can open them on excalidraw.com without running anything.

  python3 docs/diagrams/generate.py
  → writes:
      docs/diagrams/01-system-view.excalidraw
      docs/diagrams/02-stage-confirm-sequence.excalidraw
      docs/diagrams/03-board-read-loop.excalidraw

Each file is plain JSON; open at https://excalidraw.com (drag & drop).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT_DIR = Path(__file__).parent

# Color palette — keep tight so the three diagrams feel like a set.
INK    = "#1e1e1e"   # default stroke + text
BG     = "#ffffff"   # canvas
ACTOR  = "#ffd43b"   # the captain (and other human actors)
CLIENT = "#a5d8ff"   # client processes
CORE   = "#b2f2bb"   # daemon + library — agent-fleet's own boxes
EXT    = "#e9ecef"   # external systems (cmux, LLM)
DATA   = "#ffe0b2"   # persistence files / state
ACCENT = "#ffc9c9"   # alerts / non-goals (used sparingly)


# ─── id + element helpers ──────────────────────────────────────────────

def _id(seed: str) -> str:
    """Deterministic short id from a semantic seed (keeps diff stable on regen)."""
    return hashlib.sha1(seed.encode()).hexdigest()[:16]


def _base(seed: str, kind: str) -> dict:
    return {
        "id": _id(seed),
        "type": kind,
        "x": 0, "y": 0, "width": 0, "height": 0,
        "angle": 0,
        "strokeColor": INK,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": int(hashlib.sha1(seed.encode()).hexdigest()[:8], 16),
        "version": 1,
        "versionNonce": int(hashlib.sha1((seed + "n").encode()).hexdigest()[:8], 16),
        "isDeleted": False,
        "boundElements": [],
        "updatedAt": 1700000000000,
        "link": None,
        "locked": False,
    }


def rect(seed, x, y, w, h, *, fill=None, stroke=INK, dashed=False, round=True) -> dict:
    e = _base(seed, "rectangle")
    e.update(x=x, y=y, width=w, height=h, strokeColor=stroke,
             backgroundColor=fill or "transparent",
             strokeStyle="dashed" if dashed else "solid",
             roundness={"type": 3} if round else None)
    return e


def ellipse(seed, x, y, w, h, *, fill=None, stroke=INK) -> dict:
    e = _base(seed, "ellipse")
    e.update(x=x, y=y, width=w, height=h, strokeColor=stroke,
             backgroundColor=fill or "transparent")
    return e


def text(seed, x, y, w, h, content, *, size=18, color=INK, align="center",
         container=None) -> dict:
    e = _base(seed, "text")
    e.update(x=x, y=y, width=w, height=h, strokeColor=color,
             text=content, fontSize=size, fontFamily=5,   # 5 = Excalifont
             textAlign=align, verticalAlign="middle",
             baseline=int(size * 0.85),
             containerId=container,
             originalText=content,
             lineHeight=1.25)
    return e


def boxed_text(seed, x, y, w, h, content, *, fill=None, size=18, stroke=INK,
               dashed=False) -> list[dict]:
    """A rectangle + its centered text label, properly bound together."""
    rid = _id(seed + "rect")
    tid = _id(seed + "txt")
    r = rect(seed + "rect", x, y, w, h, fill=fill, stroke=stroke, dashed=dashed)
    r["boundElements"] = [{"id": tid, "type": "text"}]
    t = text(seed + "txt", x, y, w, h, content, size=size, container=rid)
    return [r, t]


def arrow(seed, x1, y1, x2, y2, *, label=None, dashed=False, color=INK,
          start_arrow=None, end_arrow="arrow") -> list[dict]:
    """Straight arrow from (x1,y1) to (x2,y2). Optional centered label."""
    e = _base(seed, "arrow")
    e.update(x=x1, y=y1, width=abs(x2 - x1), height=abs(y2 - y1),
             strokeColor=color,
             strokeStyle="dashed" if dashed else "solid",
             points=[[0, 0], [x2 - x1, y2 - y1]],
             lastCommittedPoint=None,
             startBinding=None, endBinding=None,
             startArrowhead=start_arrow, endArrowhead=end_arrow,
             elbowed=False)
    out = [e]
    if label:
        mx, my = (x1 + x2) // 2, (y1 + y2) // 2
        out.append(text(seed + "lbl", mx - 60, my - 14, 120, 22, label,
                        size=14, color="#495057"))
    return out


def write_diagram(name: str, elements: list[dict]) -> Path:
    path = OUT_DIR / f"{name}.excalidraw"
    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "agent-fleet/docs/diagrams/generate.py",
        "elements": elements,
        "appState": {"viewBackgroundColor": BG, "gridSize": 20},
        "files": {},
    }
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ─── Diagram 1: system view ────────────────────────────────────────────

def diagram_system_view() -> list[dict]:
    els: list[dict] = []

    # Title
    els.append(text("sv-title", 480, 20, 480, 30,
                    "agent-fleet · system view", size=24))

    # Captain (top center) — actor
    els += boxed_text("sv-captain", 600, 70, 240, 60,
                      "舰长 (Captain)", fill=ACTOR, size=20)

    # Clients row (5 boxes) — under captain
    cx0, cy = 60, 180
    cw, ch, gap = 200, 70, 30
    client_specs = [
        ("sv-say",     "say.py\nkeyboard",          False),
        ("sv-chat",    "chat.py\n大副 LLM REPL",     False),
        ("sv-confirm", "confirm.py\n👍 / 👎",        False),
        ("sv-voice",   "voice front-end\n(optional)", True),
        ("sv-gesture", "gesture\n(optional)",       True),
    ]
    client_centers = []
    for i, (seed, label, dashed) in enumerate(client_specs):
        x = cx0 + i * (cw + gap)
        els += boxed_text(seed, x, cy, cw, ch, label,
                          fill=CLIENT if not dashed else "#dee2e6",
                          dashed=dashed, size=15)
        client_centers.append((x + cw // 2, cy))

    # Group rectangle around clients
    els.append(rect("sv-clients-frame", cx0 - 20, cy - 36,
                    5 * cw + 4 * gap + 40, ch + 60,
                    stroke="#adb5bd", round=False, dashed=True))
    els.append(text("sv-clients-lbl", cx0 - 10, cy - 32, 180, 22,
                    "Clients · drive the fleet", size=14, color="#495057",
                    align="left"))

    # Captain → each client
    cap_x, cap_y = 600 + 120, 70 + 60
    for i, (seed, _, _) in enumerate(client_specs):
        cxc, cyc = client_centers[i]
        els += arrow(f"sv-cap-{seed}", cap_x, cap_y, cxc, cy - 4,
                     color="#868e96")

    # Daemon row
    dx, dy = 380, 330
    dw, dh = 380, 110
    els.append(rect("sv-daemon-frame", dx - 10, dy - 6, dw + 20, dh + 12,
                    fill=CORE, stroke="#2f9e44", round=True))
    els.append(text("sv-daemon-title", dx, dy, dw, 24,
                    "daemon.py · long-running broker", size=16))
    els += boxed_text("sv-socket", dx + 20, dy + 38, 150, 52,
                      "/tmp/agent-fleet.sock\n(Unix socket)", fill="#ffffff", size=12)
    els += boxed_text("sv-stager", dx + 200, dy + 38, 160, 52,
                      "RouteStager\nstage·confirm·TTL", fill="#ffffff", size=12)

    # Clients → daemon socket (one big collector arrow per client)
    sock_target_x = dx + 20 + 75
    sock_target_y = dy + 38
    for i, (seed, _, _) in enumerate(client_specs):
        cxc = client_centers[i][0]
        els += arrow(f"sv-{seed}-d", cxc, cy + ch, sock_target_x, sock_target_y,
                     dashed=client_specs[i][2], color="#1971c2")

    # Library box — to the right of daemon
    lx, ly = 820, 330
    lw, lh = 280, 170
    els.append(rect("sv-lib-frame", lx, ly, lw, lh,
                    fill=CORE, stroke="#2f9e44"))
    els.append(text("sv-lib-title", lx, ly + 6, lw, 24,
                    "agent_fleet · library", size=16))
    els += boxed_text("sv-cmuxctl", lx + 20, ly + 40, 240, 64,
                      "cmux_control\nCmuxClient · NicknameRegistry\nsmart_status · resolve_target",
                      fill="#ffffff", size=12)
    els += boxed_text("sv-board", lx + 20, ly + 114, 240, 42,
                      "board.py (read-only viewer)",
                      fill="#ffffff", size=13)

    # Daemon → Library (on confirm: route)
    els += arrow("sv-d-lib", dx + dw + 10, dy + 60, lx - 4, ly + 70,
                 label="route(target,text)", color="#2f9e44")

    # Persistence — bottom-right
    px, py = 820, 540
    els.append(rect("sv-persist-frame", px, py, lw, 130,
                    fill=DATA, stroke="#e67700"))
    els.append(text("sv-persist-title", px, py + 6, lw, 22,
                    "~/.cache/agent-fleet/", size=14))
    els += boxed_text("sv-nicks", px + 20, py + 34, 240, 38,
                      "nicknames.json\nsurface_uuid → nickname",
                      fill="#ffffff", size=11)
    els += boxed_text("sv-bdreg", px + 20, py + 80, 240, 38,
                      "board-surfaces/\nlive board self-registry",
                      fill="#ffffff", size=11)

    # Library ↔ Persistence (read+write)
    els += arrow("sv-lib-pers", lx + lw // 2, ly + lh, px + lw // 2, py,
                 color="#e67700", start_arrow="arrow")

    # cmux — bottom center
    mx, my = 380, 540
    mw, mh = 380, 130
    els.append(rect("sv-cmux-frame", mx, my, mw, mh, fill=EXT, stroke="#868e96"))
    els.append(text("sv-cmux-title", mx, my + 6, mw, 22,
                    "cmux · terminal manager (external)", size=14))
    # ships
    sh_w = 100
    sh_specs = [("alpha", "Claude\nCode"), ("bravo", "Cursor"), ("charlie", "shell")]
    for i, (n, role) in enumerate(sh_specs):
        sx = mx + 20 + i * (sh_w + 16)
        els += boxed_text(f"sv-ship-{n}", sx, my + 36, sh_w, 80,
                          f"{n}\n{role}", fill="#ffffff", size=12)

    # Library → cmux RPC
    els += arrow("sv-lib-cmux", lx, ly + lh, mx + mw, my + 60,
                 label="cmux rpc", color="#868e96")

    # LLM (left of cmux, dashed since optional)
    llmx, llmy = 60, 540
    els.append(rect("sv-llm-frame", llmx, llmy, 280, 130,
                    fill=EXT, stroke="#adb5bd", dashed=True))
    els.append(text("sv-llm-title", llmx, llmy + 6, 280, 22,
                    "claude --print · subprocess", size=14))
    els.append(text("sv-llm-desc", llmx + 16, llmy + 38, 248, 80,
                    "JSON-schema-validated\nenvelope: {reply, actions[]}\n(only used by chat.py)",
                    size=12, color="#495057", align="left"))

    # chat.py → LLM (dashed, optional)
    chat_x = client_centers[1][0]
    els += arrow("sv-chat-llm", chat_x, cy + ch, llmx + 140, llmy,
                 label="prompt", dashed=True, color="#adb5bd")

    return els


# ─── Diagram 2: stage→confirm→execute sequence ─────────────────────────

def diagram_sequence() -> list[dict]:
    els: list[dict] = []
    els.append(text("sq-title", 280, 20, 720, 30,
                    "agent-fleet · stage → confirm → execute (one full order)", size=22))

    # 5 actors across the top (kept compact: skip LLM and Stager — they live
    # inside chat/daemon respectively, footnoted instead).
    actors = [
        ("舰长", "Captain", ACTOR),
        ("chat.py", "client", CLIENT),
        ("daemon.py", "broker", CORE),
        ("cmux RPC", "transport", EXT),
        ("alpha pane", "Claude Code", "#ffffff"),
    ]
    col_w, col_gap = 200, 60
    x0, header_y = 100, 80
    cols = []
    for i, (name, sub, fill) in enumerate(actors):
        x = x0 + i * (col_w + col_gap)
        els += boxed_text(f"sq-hdr-{i}", x, header_y, col_w, 56,
                          f"{name}\n{sub}", fill=fill, size=14)
        cols.append(x + col_w // 2)

    # Lifelines (vertical dashed)
    lifeline_top = header_y + 56
    lifeline_bot = 700
    for i, cx in enumerate(cols):
        els += arrow(f"sq-life-{i}", cx, lifeline_top, cx, lifeline_bot,
                     dashed=True, color="#adb5bd", end_arrow=None)

    # Messages (top to bottom). (from_col, to_col, label, dashed?)
    messages = [
        (0, 1, '"alpha 跑 pytest"',                       False),
        (1, 2, "board snapshot (cmux RPC via lib)",        False),
        (2, 1, "sessions[alpha→S1, bravo→S2, ...]",        True),
        (1, 1, "→ claude --print (subprocess, schema)",    False),
        (1, 2, "stage_route {target:alpha, text:pytest}",  False),
        (2, 2, "RouteStager.stage(alpha, pytest)",         False),
        (2, 1, "{ok: true}",                               True),
        (1, 2, "confirm_route",                            False),
        (2, 2, "RouteStager.confirm() → resolve alpha→S1", False),
        (2, 3, "surface.focus S1",                         False),
        (2, 3, "surface.send_text S1 'pytest'",            False),
        (2, 3, "surface.send_key S1 Enter",                False),
        (3, 4, "types 'pytest' + Enter",                   False),
        (4, 0, "pytest output (in cmux pane)",             False),
        (2, 1, "{ok:true, fired:true}",                    True),
        (1, 0, "renders '✓ stage[alpha] ✓ confirm·fired'", True),
    ]

    msg_y0 = lifeline_top + 24
    step_h = 36
    for i, (a, b, lbl, dashed) in enumerate(messages):
        y = msg_y0 + i * step_h
        if a == b:  # self-loop
            # tiny right-then-down-then-left, rendered as a single right-pointing arrow + label
            els += arrow(f"sq-msg-{i}", cols[a] - 6, y, cols[a] + 60, y,
                         color="#1c7ed6", dashed=dashed, end_arrow="arrow")
            els.append(text(f"sq-msg-{i}-lbl", cols[a] + 64, y - 12, 320, 22,
                            lbl, size=12, color="#495057", align="left"))
        else:
            x1, x2 = cols[a], cols[b]
            # offset so the line doesn't overlap the lifeline tick marks
            sx = x1 + (6 if x2 > x1 else -6)
            ex = x2 + (-6 if x2 > x1 else 6)
            els += arrow(f"sq-msg-{i}", sx, y, ex, y,
                         color="#1c7ed6", dashed=dashed)
            mx = (sx + ex) // 2
            els.append(text(f"sq-msg-{i}-lbl", mx - 200, y - 22, 400, 20,
                            lbl, size=12, color="#495057", align="center"))

    # Footnote
    els.append(text("sq-fn", 100, lifeline_bot + 16, 1120, 50,
                    "Note: stage_route ≠ execute. Only confirm_route fires the cmux send. "
                    "Pending command auto-expires after RouteStager.ttl_s (60s). Captain can "
                    "drop with cancel_route from any client.",
                    size=12, color="#495057", align="left"))
    return els


# ─── Diagram 3: board read loop ────────────────────────────────────────

def diagram_board_loop() -> list[dict]:
    els: list[dict] = []
    els.append(text("bl-title", 240, 20, 720, 30,
                    "agent-fleet · board read loop (every 2 s)", size=22))

    # The watcher in the center
    wx, wy = 480, 100
    els += boxed_text("bl-watcher", wx, wy, 240, 70,
                      "board.py --watch\n(every interval)", fill=ACTOR, size=15)

    # Step boxes laid out in a clockwise loop
    steps = [
        ("bl-s1", 760, 180, "1. read board-surfaces/\n→ skip these UUIDs",   DATA),
        ("bl-s2", 760, 290, "2. cmux window.list",                            EXT),
        ("bl-s3", 760, 400, "3. for each window:\n   workspace.list",         EXT),
        ("bl-s4", 480, 510, "4. for each workspace:\n   surface.list",        EXT),
        ("bl-s5", 200, 400, "5. for each terminal:\n   NicknameRegistry.assign", CORE),
        ("bl-s6", 200, 290, "6. surface.read_text",                           EXT),
        ("bl-s7", 200, 180, "7. smart_status()\n   skip banner/HUD, prefer ※ / ✻",
         CORE),
    ]
    step_centers = []
    for seed, x, y, label, fill in steps:
        els += boxed_text(seed, x, y, 240, 70, label, fill=fill, size=13)
        step_centers.append((x + 120, y + 35))

    # Arrows watcher → step 1 → step 2 → ... → step 7 → back to watcher (render)
    wcx, wcy = wx + 120, wy + 70
    # watcher → step 1
    els += arrow("bl-w-1", wcx + 60, wcy - 10, step_centers[0][0], step_centers[0][1] - 30,
                 color="#1971c2")
    # step n → step n+1
    for i in range(len(steps) - 1):
        a = step_centers[i]
        b = step_centers[i + 1]
        els += arrow(f"bl-{i}-{i+1}", a[0], a[1] + 36, b[0], b[1] - 36,
                     color="#1971c2")
    # last step → watcher (render & redraw)
    els += arrow("bl-render", step_centers[-1][0], step_centers[-1][1] + 36,
                 wcx - 60, wcy - 10,
                 label="render & redraw", color="#2f9e44")

    # Highlight callouts
    els.append(rect("bl-fanout-cal", 720, 280, 320, 130,
                    stroke=ACCENT, dashed=True, round=False))
    els.append(text("bl-fanout-lbl", 720, 416, 320, 20,
                    "cross-window fanout (the new bit)",
                    size=12, color="#c92a2a", align="center"))

    els.append(rect("bl-smart-cal", 160, 170, 320, 90,
                    stroke=ACCENT, dashed=True, round=False))
    els.append(text("bl-smart-lbl", 160, 264, 320, 20,
                    "smart_status — readable rows",
                    size=12, color="#c92a2a", align="center"))

    # Footnote
    els.append(text("bl-fn", 120, 620, 1080, 60,
                    "Self-exclusion: each --watch instance writes its surface UUID into "
                    "~/.cache/agent-fleet/board-surfaces/<uuid> at start and atexit-removes "
                    "it. cmux overrides surface titles, so the title-marker fallback alone "
                    "isn't enough — the registry is the source of truth.",
                    size=12, color="#495057", align="left"))
    return els


# ─── main ───────────────────────────────────────────────────────────────

def main() -> int:
    diagrams = [
        ("01-system-view",            diagram_system_view),
        ("02-stage-confirm-sequence", diagram_sequence),
        ("03-board-read-loop",        diagram_board_loop),
    ]
    for name, builder in diagrams:
        els = builder()
        p = write_diagram(name, els)
        print(f"  wrote {p.relative_to(OUT_DIR.parent.parent)}  ({len(els)} elements)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
