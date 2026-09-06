#!/usr/bin/env python3
"""
Strip personal identifiers out of an exported n8n workflow before publishing.

n8n does not export credential secrets, but a downloaded workflow JSON does
contain the spreadsheet id, every sheet gid, credential ids and names, and any
email address typed into a node. None of that should go into a public repo:
the address attracts spam, and the ids make the workflow useless to anyone who
clones it, since they point at documents only you can open.

    python3 tools/sanitise_export.py raw-export.json workflows/01-order-intake.json

Reads the mapping below, rewrites every occurrence, and refuses to write the
output if anything that looks like an email address or a Google file id is
still present afterwards.
"""

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The mapping lives in a separate file, not in this script.
#
# It is the one place your real spreadsheet ids, sheet gids and email address
# are written down - so committing it would publish exactly what this tool
# exists to remove. `sanitise-map.json` is gitignored; copy the example file
# and fill in your own values.
# ---------------------------------------------------------------------------
MAP_FILE = Path(__file__).with_name("sanitise-map.json")
EXAMPLE_FILE = Path(__file__).with_name("sanitise-map.example.json")


def load_replacements() -> dict[str, str]:
    if not MAP_FILE.is_file():
        sys.exit(
            f"No mapping file at {MAP_FILE.name}.\n\n"
            f"  cp {EXAMPLE_FILE.name} {MAP_FILE.name}\n\n"
            "then fill in your spreadsheet ids, sheet gids and email address. "
            "It is gitignored and stays on this machine."
        )
    try:
        mapping = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"{MAP_FILE.name} is not valid JSON: {exc}")

    if not isinstance(mapping, dict) or not mapping:
        sys.exit(f"{MAP_FILE.name} must be a non-empty object of secret -> placeholder.")

    return {str(k): str(v) for k, v in mapping.items()}


REPLACEMENTS: dict[str, str] = {}

# Anything still matching these after replacement is a leak we did not plan for.
LEAK_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "email address"),
    (re.compile(r"\b[A-Za-z0-9_-]{40,}\b"), "possible Google file id"),
]

ALLOWED = {"you@example.com", "REPLACE_WITH_YOUR_CREDENTIAL"}

# Keys stripped from the exported workflow before publishing.
#
#   pinData     - THE IMPORTANT ONE. Pinned nodes store their captured output
#                 verbatim, which for this project means real Gmail message
#                 bodies, sender addresses and customer data. Empty today, but
#                 one forgotten pin would publish a live inbox.
#   meta        - contains instanceId, a fingerprint of your n8n installation.
#   id,
#   versionId   - identifiers local to your instance; meaningless elsewhere.
#   tags        - your own organisation, not the reader's.
STRIP_KEYS = ("pinData", "meta", "id", "versionId", "tags")


def strip_local_metadata(doc: dict) -> tuple[dict, list[str]]:
    """Remove instance-local keys and blank credential ids. Returns what went."""
    removed = []
    for key in STRIP_KEYS:
        if key in doc:
            value = doc.pop(key)
            detail = f"{key}"
            if key == "pinData" and value:
                detail = f"{key} ({len(value)} pinned node(s) - REAL DATA)"
            removed.append(detail)

    # Credential ids are instance-local. Keep the names, so a reader can see
    # which credential each node wants and attach their own on import.
    blanked = 0
    for node in doc.get("nodes", []):
        for cred in (node.get("credentials") or {}).values():
            if isinstance(cred, dict) and cred.get("id"):
                cred["id"] = "REPLACE_WITH_YOUR_CREDENTIAL"
                blanked += 1
    if blanked:
        removed.append(f"{blanked} credential id(s)")

    return doc, removed


def sanitise(text: str) -> str:
    for secret, placeholder in REPLACEMENTS.items():
        text = text.replace(secret, placeholder)
    return text


def find_leaks(text: str) -> list[str]:
    leaks = []
    for pattern, label in LEAK_PATTERNS:
        for match in set(pattern.findall(text)):
            if match in ALLOWED or match in REPLACEMENTS.values():
                continue
            leaks.append(f"{label}: {match}")
    return leaks


def main() -> int:
    if len(sys.argv) != 3:
        return print(__doc__.strip()) or 2

    REPLACEMENTS.update(load_replacements())
    ALLOWED.update(REPLACEMENTS.values())

    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        sys.exit(f"No such file: {src}")

    raw = src.read_text(encoding="utf-8")

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"{src} is not valid JSON: {exc}")

    doc, removed = strip_local_metadata(doc)
    cleaned = sanitise(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    try:
        json.loads(cleaned)
    except json.JSONDecodeError as exc:
        sys.exit(f"A replacement broke the JSON: {exc}")

    leaks = find_leaks(cleaned)
    if leaks:
        print("Refusing to write - unhandled identifiers remain:\n",
              file=sys.stderr)
        for leak in sorted(leaks):
            print(f"  {leak}", file=sys.stderr)
        print("\nAdd them to REPLACEMENTS and run again.", file=sys.stderr)
        return 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(cleaned, encoding="utf-8")

    changed = sum(1 for s in REPLACEMENTS if s in raw)
    print(f"Wrote {dst}")
    print(f"  {changed} identifier(s) replaced")
    if removed:
        print(f"  stripped: {', '.join(removed)}")
    print("  no leaks detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
