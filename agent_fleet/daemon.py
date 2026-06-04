"""Minimal daemon for agent-fleet: a Unix-socket server that brokers
stage_route / confirm_route / cancel_route actions between clients (say,
chat, voice hooks) and the cmux router (RouteStager + CmuxClient.route).

The stage→confirm split is the safety gate: a stage records intent without
sending anything; only `confirm` types the verbatim command into the chosen
ship and submits Enter. A pending command auto-expires after TTL.

Run:
    python -m agent_fleet.daemon                 # blocking, foreground
    python -m agent_fleet.daemon --socket /tmp/agent-fleet.sock  # custom path

Protocol (newline-delimited JSON over Unix socket):
    {"action": "stage_route", "target": "alpha", "text": "pytest"}
      → {"ok": true, "tier": "gray"}          // staged, not yet sent; tier is
                                              //   white|black|gray risk class
    {"action": "confirm_route"}
      → {"ok": true, "fired": true}           // route ran (focus + type + Enter)
    {"action": "cancel_route"}
      → {"ok": true, "fired": true}           // pending dropped (false if nothing was pending)
    {"action": "status_route"}
      → {"ok": true, "staged": {"target": "alpha", "text": "pytest", "age_s": 4.2}}
                                              // or "staged": null when nothing's pending

`target` may be a NATO nickname (alpha/bravo/…), an unambiguous prefix
("alph"), or — for back-compat — a 1-based number (int or digit string).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from agent_fleet.cmux_control import CmuxClient
from agent_fleet.permissions import classify
from agent_fleet.stager import RouteStager

DEFAULT_SOCKET = os.environ.get("AGENT_FLEET_SOCKET", "/tmp/agent-fleet.sock")


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    stager: RouteStager,
    log: logging.Logger,
) -> None:
    """One client connection = one JSON line in, one JSON line out."""
    try:
        line = await reader.readuntil(b"\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        writer.close()
        return
    try:
        head = json.loads(line.decode().strip())
    except json.JSONDecodeError:
        log.warning("bad request JSON: %r", line[:120])
        writer.close()
        return
    action = head.get("action") if isinstance(head, dict) else None

    if action == "stage_route":
        target = head.get("target")
        if target is None:
            target = head.get("session")  # legacy field
        ack: dict = {"ok": False, "error": "missing text"}
        if "text" in head:
            try:
                stager.stage(target, str(head["text"]))
                ack = {"ok": True, "tier": classify(str(head["text"]))}
            except Exception as e:  # noqa: BLE001
                ack = {"ok": False, "error": str(e)}
        log.info("stage_route target=%r text=%r -> %s",
                 target, head.get("text"), ack)
        writer.write((json.dumps(ack) + "\n").encode())

    elif action == "status_route":
        # Read-only snapshot — no lock contention with stage/confirm/cancel
        # beyond the brief peek inside stager.status().
        writer.write((json.dumps({"ok": True, "staged": stager.status()}) + "\n").encode())

    elif action in ("confirm_route", "cancel_route"):
        loop = asyncio.get_running_loop()
        if action == "cancel_route":
            fired = stager.cancel()
        else:
            # cmux send is blocking — run off-loop so the event loop stays free.
            fired = await loop.run_in_executor(None, stager.confirm)
        log.info("%s -> fired=%s", action, bool(fired))
        writer.write((json.dumps({"ok": True, "fired": bool(fired)}) + "\n").encode())

    else:
        writer.write((json.dumps({"ok": False, "error": f"unknown action {action!r}"}) + "\n").encode())

    await writer.drain()
    writer.close()


async def _serve(socket_path: str, log: logging.Logger) -> None:
    # Remove any stale socket file from a prior run.
    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("could not remove stale socket %s: %s", socket_path, e)

    stager = RouteStager(route_fn=CmuxClient().route)

    async def on_client(r, w):
        try:
            await _handle_client(r, w, stager, log)
        except Exception:  # noqa: BLE001 — keep the server up
            log.exception("client handler crashed")

    server = await asyncio.start_unix_server(on_client, path=socket_path)
    os.chmod(socket_path, 0o600)
    log.info("agent-fleet daemon listening on %s", socket_path)
    async with server:
        await server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--socket", default=DEFAULT_SOCKET,
                    help="Unix socket path (env AGENT_FLEET_SOCKET overrides default)")
    ap.add_argument("--log-level", default="INFO",
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("agent-fleet.daemon")

    try:
        asyncio.run(_serve(args.socket, log))
    except KeyboardInterrupt:
        log.info("shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
