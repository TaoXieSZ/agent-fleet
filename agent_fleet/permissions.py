"""Command risk classification for the chat permission gate.

`classify(text)` sorts a verbatim shell command into one of three tiers:

    "white"  — read-only / safe; the chat REPL auto-fires without asking.
    "black"  — matches a dangerous pattern; chat double-confirms before firing.
    "gray"   — everything else; chat pops an approve / deny prompt.

Black takes priority over white: a command that *contains* a dangerous
pattern is black even if it starts with an otherwise-safe word. Stdlib-only
(regex + string), so it stays in the core lib and is trivially unit-testable.

The daemon classifies on `stage_route` and returns the tier in its ack; the
policy lives here (one place to maintain the white/black lists), while the
approve/deny UI and the per-REPL always-allow set live in chat.py.
"""
from __future__ import annotations

import re

Tier = str  # "white" | "black" | "gray"

# Dangerous patterns — matched anywhere in the command (case-insensitive).
# Keep this list conservative: a false "black" only costs one extra keystroke,
# but a missed dangerous command defeats the gate.
_BLACK_PATTERNS = [
    r"\brm\s+-[a-z]*[rf][a-z]*\b",      # rm -rf / -fr / -r -f variants
    r"\bsudo\b",                          # any sudo
    r"\bgit\s+push\b.*(--force|--force-with-lease|\s-f\b)",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[a-z]*f",          # git clean -fd
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",                       # writing to a raw disk
    r"\bchmod\s+-R\b",
    r"\bchown\s+-R\b",
    r"\bcurl\b[^|]*\|\s*(sh|bash|zsh)\b", # curl ... | sh
    r"\bwget\b[^|]*\|\s*(sh|bash|zsh)\b",
    r":\(\)\s*\{",                        # fork bomb :(){
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bkill\s+-9\s+-1\b",
    r"\btruncate\b",
    r"\b>\s*/dev/null\s+2>&1\s*;\s*rm",   # sneaky cleanup
]
_BLACK_RE = [re.compile(p, re.IGNORECASE) for p in _BLACK_PATTERNS]

# Read-only commands whose first token is always safe.
_WHITE_CMDS = {
    "ls", "ll", "la", "pwd", "cat", "less", "more", "head", "tail",
    "echo", "printf", "grep", "rg", "ag", "find", "fd", "which", "type",
    "whoami", "id", "date", "env", "printenv", "ps", "df", "du", "tree",
    "wc", "stat", "file", "uname", "hostname", "uptime", "history",
}

# git subcommands that are read-only.
_WHITE_GIT_SUB = {
    "status", "diff", "log", "show", "branch", "remote", "blame",
    "describe", "rev-parse", "ls-files", "shortlog", "tag", "stash",
}


def classify(text: str) -> Tier:
    """Return the risk tier ("white" | "black" | "gray") for a command."""
    cmd = (text or "").strip()
    if not cmd:
        return "gray"

    # Black wins over everything — scan the whole command for danger.
    for rx in _BLACK_RE:
        if rx.search(cmd):
            return "black"

    tokens = cmd.split()
    first = tokens[0].lower()

    # git is read-only only for specific subcommands.
    if first == "git":
        sub = tokens[1].lower() if len(tokens) > 1 else ""
        return "white" if sub in _WHITE_GIT_SUB else "gray"

    if first in _WHITE_CMDS:
        return "white"

    return "gray"
