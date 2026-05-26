# agent-fleet architecture

agent-fleet is a tiny addressing + staging layer over [cmux](https://github.com/manaflow-ai/cmux):
it gives every terminal pane a stable nickname, holds at most one staged
command in a long-running daemon, and routes the verbatim command into the
chosen cmux pane on the captain's confirm. Clients (keyboard / LLM REPL /
voice / gesture) all speak the same newline-JSON socket protocol — anything
that can open a Unix socket is a valid driver.

The whole system is ~7 small modules. The diagrams below show how they fit.

> 📐 **Editable / higher-fidelity versions** of all three diagrams live as
> Excalidraw source files in [`diagrams/`](diagrams/) — drag any
> `.excalidraw` file into <https://excalidraw.com> to view or remix.
> Run [`diagrams/generate.py`](diagrams/generate.py) to regenerate after
> layout tweaks.

## System view

```mermaid
flowchart LR
    Captain([舰长 / Captain])

    subgraph Clients["Clients · drive the fleet"]
      Say["say.py<br/>keyboard"]
      Chat["chat.py<br/>大副 · LLM REPL"]
      Confirm["confirm.py<br/>commit / cancel"]
      Voice["(optional)<br/>voice front-end"]
      Gesture["(optional)<br/>gesture detector"]
    end

    subgraph Daemon["daemon.py · long-running process"]
      Socket[/"/tmp/agent-fleet.sock<br/>(Unix socket)"/]
      Stager["RouteStager<br/>one pending slot · TTL · last-wins"]
    end

    subgraph Lib["agent_fleet · library"]
      CmuxControl["cmux_control<br/>CmuxClient · NicknameRegistry<br/>smart_status · resolve_target"]
      Board["board.py<br/>(read-only viewer)"]
    end

    subgraph Persist["~/.cache/agent-fleet/"]
      Nicks[("nicknames.json<br/>surface_uuid → nickname")]
      BoardReg[("board-surfaces/<br/>live board self-registry")]
    end

    subgraph Cmux["cmux · terminal manager"]
      P1["pane: alpha<br/>(Claude Code)"]
      P2["pane: bravo<br/>(Cursor)"]
      P3["pane: charlie<br/>(shell)"]
    end

    LLM["claude --print<br/>subprocess"]

    Captain -->|types| Say
    Captain -->|chats| Chat
    Captain -->|👍 / hotkey| Confirm
    Captain -.->|speaks| Voice
    Captain -.->|gesture| Gesture

    Say -->|stage_route| Socket
    Chat -->|stage_route + confirm| Socket
    Voice -.->|stage_route| Socket
    Gesture -.->|confirm / cancel| Socket
    Confirm -->|confirm / cancel| Socket

    Socket --> Stager
    Stager -->|on confirm| CmuxControl

    Chat -.->|board snapshot| CmuxControl
    Chat -.->|envelope JSON| LLM
    Board -->|polls| CmuxControl

    CmuxControl <-.->|read / write| Nicks
    Board -.->|touches| BoardReg
    CmuxControl -.->|reads| BoardReg

    CmuxControl -->|window.list · workspace.list<br/>surface.list · surface.focus<br/>surface.send_text · surface.send_key| Cmux
    Cmux --- P1
    Cmux --- P2
    Cmux --- P3

    classDef ext fill:#fff,stroke:#888,stroke-dasharray:4 3,color:#444
    class Voice,Gesture,LLM,Cmux,P1,P2,P3 ext
```

The dashed edges are optional / out-of-process. Solid boxes are agent-fleet
itself; everything outside `Clients` + `Daemon` + `Lib` is either user-owned
state or an external system (cmux, the LLM subprocess).

## Stage → confirm → execute (one full order)

```mermaid
sequenceDiagram
    autonumber
    actor Captain as 舰长
    participant Chat as chat.py
    participant LLM as claude --print
    participant Daemon as daemon.py
    participant Stager as RouteStager
    participant Cmux as cmux RPC
    participant Pane as alpha pane

    Captain->>Chat: "alpha 跑 pytest"
    Chat->>Daemon: board snapshot (via cmux_control)
    Daemon-->>Chat: sessions[alpha→S1, bravo→S2, ...]
    Chat->>LLM: prompt + JSON schema (target,text)
    LLM-->>Chat: {reply:"alpha：pytest，舰长。",<br/>actions:[stage(alpha,pytest), confirm]}

    Chat->>Daemon: stage_route {target:"alpha", text:"pytest"}
    Daemon->>Stager: stage(alpha, pytest)
    Stager-->>Daemon: ok
    Daemon-->>Chat: {ok:true}

    Chat->>Daemon: confirm_route
    Daemon->>Stager: confirm()
    Stager->>Cmux: resolve "alpha" → surface UUID S1
    Stager->>Cmux: surface.focus S1
    Stager->>Cmux: surface.send_text S1 "pytest"
    Stager->>Cmux: surface.send_key S1 Enter
    Cmux->>Pane: types "pytest" + Enter
    Pane-->>Captain: pytest output (in cmux)
    Stager-->>Daemon: fired=true
    Daemon-->>Chat: {ok:true, fired:true}
    Chat-->>Captain: renders "✓ stage[alpha] ✓ confirm·fired"
```

The **stage → confirm split is the safety gate**: `stage_route` records intent
but sends nothing; only `confirm_route` actually types into the pane. A
pending command auto-expires after `RouteStager.ttl_s` (default 60 s), so a
stale stage can never fire much later. Captain can also drop it with
`cancel_route` from anywhere (👎 gesture, `confirm.py cancel`, REPL).

The captain can skip the LLM entirely — `say.py` runs the same protocol with
a deterministic regex parser, no `claude --print` subprocess, no spinner.

## Board read loop (read-only side path)

```mermaid
sequenceDiagram
    autonumber
    participant Watcher as board.py --watch
    participant Reg as NicknameRegistry
    participant BReg as board-surfaces/
    participant Cmux as cmux RPC

    Note over Watcher: every 2 s
    Watcher->>BReg: list registered board UUIDs (exclude these)
    Watcher->>Cmux: window.list
    loop per window
      Watcher->>Cmux: workspace.list {window_id}
      loop per workspace
        Watcher->>Cmux: surface.list {workspace_id}
      end
    end

    loop per terminal surface
      Watcher->>Reg: assign(surface_uuid) → nickname
      Watcher->>Cmux: surface.read_text {surface_id}
      Note over Watcher: smart_status() walks the tail<br/>skips banner / HUD / separators<br/>prefers ※ recap or ✻ verb
    end

    Watcher-->>Watcher: render & redraw
```

Two things this diagram makes explicit:

1. **Cross-window fanout.** `workspace.list` without `window_id` only returns
   the *caller's* window. The watcher iterates `window.list` first so popping
   the board into its own cmux window doesn't hide agent panes.
2. **Self-exclusion.** Each `board.py --watch` instance writes its own
   surface UUID to `~/.cache/agent-fleet/board-surfaces/<uuid>` on start
   (and removes it on clean exit via `atexit`). The watcher reads that
   directory each pass and skips those surfaces — the board never lists
   itself, no matter how cmux mangles the pane title.

## Wire protocol

Newline-delimited JSON over the Unix socket (default `/tmp/agent-fleet.sock`,
override with `AGENT_FLEET_SOCKET`). One request, one response, connection
closed.

| Action          | Request                                                    | Response                              |
| --------------- | ---------------------------------------------------------- | ------------------------------------- |
| `stage_route`   | `{action, target, text}` — `target` is nickname / prefix / int | `{ok: true}` or `{ok:false, error}`   |
| `confirm_route` | `{action}`                                                 | `{ok: true, fired: bool}`             |
| `cancel_route`  | `{action}`                                                 | `{ok: true, fired: bool}`             |

`fired:false` from confirm/cancel means there was nothing pending (TTL
expired, or it was already confirmed/cancelled by another client).

Legacy clients may still send `{action: "stage_route", session: int, text}`.
The daemon falls back to `session` when `target` is absent so the older
voice-hook / pre-nickname `say.py` keep working through the migration.

## Where state lives

| Location                                          | Lifetime           | Holds                                                                 |
| ------------------------------------------------- | ------------------ | --------------------------------------------------------------------- |
| `~/.cache/agent-fleet/nicknames.json`             | persistent         | `surface_uuid → nickname` (never recycled within a registry)          |
| `~/.cache/agent-fleet/board-surfaces/<uuid>`      | live-pane lifetime | empty marker file per running `board.py --watch` instance             |
| `/tmp/agent-fleet.sock`                           | daemon lifetime    | the broker's listen socket                                            |
| `RouteStager._pending` (in-memory)                | ≤ `ttl_s`          | the one staged `(target, text, staged_at)`                            |
| `chat.py` `ChatState` (per REPL session)          | REPL lifetime      | recent turns + last envelope + last action results                    |
| cmux itself                                       | (out of scope)     | windows, workspaces, surfaces, pane stdout/stdin — the real substrate |

## Concurrency model

- `RouteStager` is **thread-safe by `threading.Lock`**. `stage()` and
  `cancel()` mutate under the lock; `confirm()` takes-and-clears the pending
  slot under the lock, *then* runs the (blocking) cmux send action with the
  lock released. This means a concurrent `stage`/`cancel` is never blocked
  on a slow subprocess, and `route_fn` may safely re-enter the stager.
- The daemon runs `confirm`'s blocking cmux send via
  `loop.run_in_executor(None, …)` so the asyncio event loop is never stalled
  while cmux types characters into a pane.
- The daemon is single-process and accepts one connection at a time per
  client — clients are short-lived (request/response/close), so there's
  no long-poll fanout to worry about.

## Extension points

Adding a new client = open the Unix socket and write one JSON line. No SDK,
no schema generation. Examples:

- **Voice front-end (Web Speech / Whisper / Agora ConvoAI)**: transcribe →
  parse "alpha 跑 pytest" → POST `stage_route` → 👍 / `confirm`.
- **Gesture front-end (camera + thumbs detector)**: write `confirm` on 👍,
  `cancel` on 👎. No knowledge of cmux or nicknames needed.
- **Different LLM backend in chat.py**: swap the single `_call_claude`
  function (subprocess to `claude --print`) for any HTTP client that
  produces the same `{reply, actions[]}` envelope.
- **Different terminal manager**: replace `CmuxClient`. As long as it can
  enumerate "ships" with stable UUIDs and send text + Enter to a chosen one,
  the rest of the stack is unchanged.

## What agent-fleet deliberately does NOT do

- **No keystroke synthesis at the OS level.** Routing is done via cmux's
  RPC — typing into one pane never leaks to whichever window is in front.
  This is the whole reason we don't use AppleScript / Quartz.
- **No exec policy.** It types whatever text it's given; the captain decides.
  Confirm-gating is the only safety, and that's the captain's job.
- **No history or replay.** `RouteStager` holds at most one pending command;
  past stages aren't logged or recoverable.
- **No multi-user / remote.** The socket is `0o600` for the local user.
  Remote drivers should run their own bridge.
