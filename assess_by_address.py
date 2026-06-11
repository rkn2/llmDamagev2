#!/usr/bin/env python3
from __future__ import annotations
"""
assess_by_address.py — Per-building flood damage assessment using before/after photo sets.

Reads address folders from the OneDrive floodREU dataset:
  ref_photo_links/address/before/<address>/*   (pre-flood reference photos)
  ref_photo_links/address/after/<address>/*    (post-flood photos)

For each address, sends ALL before+after images for that building to Claude in a
single multi-image call, asking it to compare baseline vs. post-flood condition.

Processes addresses one at a time (or a --limit-bounded batch): images are copied
to a local temp dir, resized to keep requests small, assessed, then deleted.
Results are appended incrementally to address_assessments.json (resumable —
already-processed addresses are skipped on re-run).

Never reads/writes anything back to OneDrive other than reading the source photos.

Usage:
    python3 assess_by_address.py --limit 2          # test on first 2 addresses
    python3 assess_by_address.py --start 2 --limit 5
    python3 assess_by_address.py                    # process everything remaining
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

from anthropic import AnthropicVertex

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
RESULTS_PATH = BASE_DIR / "address_assessments.json"

ONEDRIVE_ADDR_DIR = (
    Path.home()
    / "Library/CloudStorage/OneDrive-ThePennsylvaniaStateUniversity"
    / "students/undergrads/floodREU/2023_montpelier_noName/ref_photo_links/address"
)
BEFORE_DIR = ONEDRIVE_ADDR_DIR / "before"
AFTER_DIR = ONEDRIVE_ADDR_DIR / "after"

# ── API config ─────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "claude-sonnet-4-6"
VERTEX_PROJECT = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "up-ems-hdr-dsc")
VERTEX_REGION = os.environ.get("CLOUD_ML_REGION", "us-east5")

MAX_DIM = 1568  # Claude's recommended max long-edge dimension
SUPPORTED_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                 ".gif": "image/gif", ".webp": "image/webp"}

DAMAGE_DEFINITIONS = """\
Damage state scale (0–4) for flood damage assessment:

0 — None: Insignificant damage below first-floor elevation. Water enters crawlspace/basement,
    touches foundation only. Minor damage to garage interiors. No sewer backup into living area.

1 — Minor: Water touches floor joists up to minor water entry. Damage to carpets, pads,
    baseboards, flooring. External AC unit damage if not elevated. No drywall damage; potential
    minor mold on subfloor. Minor sewer backup possible.

2 — Moderate: Partial drywall damage. Damage to base electrical outlets, water heater, furnace.
    Complete damage to first-floor appliances, furniture, lower cabinets. Doors/windows may need
    replacement. Major sewer backup and mold likely.

3 — Extensive: Damage to non-structural components throughout entire building including upper
    stories. Mid-wall electrical destroyed. Upper cabinets destroyed. Studs reusable but some
    damaged. Major sewer backup and mold. Upper-floor contents also damaged.

4 — Complete/Collapsed: Significant structural damage to studs, trusses, joists. All interiors
    destroyed. Roof components damaged. Foundation may have shifted. Building must be demolished."""

SYSTEM_PROMPT = f"""\
You are a structural engineer specializing in flood damage assessment.

You will be shown two sets of exterior photos of the SAME building:
  - BEFORE: pre-flood reference photos (e.g. Street View front/back/left/right)
  - AFTER: post-flood photos taken during or after the 2023 Montpelier, VT flood

Compare the two sets and assess the flood damage visible in the AFTER photos,
using the BEFORE photos as a baseline for what is pre-existing vs. flood-caused.

Respond ONLY with a single valid JSON object — no markdown fences, no commentary.

{DAMAGE_DEFINITIONS}

Return exactly these fields:
{{
  "damage_state": integer 0–4, or null if the after-photos cannot support a building-level
                   assessment,
  "confidence": "high" | "medium" | "low",
  "water_depth_ft_exterior": float — estimated water depth in feet at building exterior in the
                             after-photos, or null,
  "is_assessable": true if a building-level damage assessment can be made from the after photos,
  "rationale": "1–2 sentence explanation citing specific visual evidence and how it compares to the before photos",
  "caveats": "key limitations — e.g. exterior only, no after photos for this facade, oblique angle"
}}"""


# ── Image prep ─────────────────────────────────────────────────────────────────

def prep_image(src: Path, dest_dir: Path) -> Path | None:
    """Copy + resize/convert an image into dest_dir. Returns the new path, or None if unsupported."""
    suffix = src.suffix.lower()
    out_path = dest_dir / (src.stem + ".png" if suffix == ".avif" else src.name)

    if suffix == ".avif":
        result = subprocess.run(
            ["sips", "-s", "format", "png", str(src), "--out", str(out_path)],
            capture_output=True,
        )
        if result.returncode != 0:
            return None
    elif suffix in SUPPORTED_EXT:
        shutil.copy2(src, out_path)
    else:
        return None

    # Resize to keep well under the 5MB API limit and Claude's recommended max dimension
    subprocess.run(
        ["sips", "-Z", str(MAX_DIM), str(out_path)],
        capture_output=True,
    )
    return out_path


def load_image_block(path: Path) -> dict:
    import base64
    media_type = SUPPORTED_EXT.get(path.suffix.lower(), "image/png")
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


# ── Address matching ───────────────────────────────────────────────────────────

def _street_parts(address: str) -> tuple[str, str]:
    """Split 'NUM Street Name, City, ST ZIP' into (house_number, street_name)."""
    first = address.split(",")[0].strip()
    m = re.match(r"(\d+)\s+(.*)", first)
    if not m:
        return "", first.lower()
    return m.group(1), m.group(2).strip().lower()


def find_before_dir(after_address: str, before_dirs: list[str]) -> str | None:
    """Find the before-photo dir for the same building (matching house number
    is required — addresses on the same street with different numbers are
    different buildings, even if the strings are otherwise very similar)."""
    if after_address in before_dirs:
        return after_address
    after_num, after_street = _street_parts(after_address)
    best, best_score = None, 0.0
    for b in before_dirs:
        b_num, b_street = _street_parts(b)
        if b_num != after_num:
            continue
        score = SequenceMatcher(None, after_street, b_street).ratio()
        if score > best_score:
            best, best_score = b, score
    return best if best_score >= 0.9 else None


# ── Assessment ─────────────────────────────────────────────────────────────────

def assess_address(client: AnthropicVertex, address: str, before_paths: list[Path],
                    after_paths: list[Path], model: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="flood_addr_") as tmp:
        tmp_dir = Path(tmp)
        content = []

        if before_paths:
            content.append({"type": "text", "text": "BEFORE (pre-flood reference) photos:"})
            for p in before_paths:
                prepped = prep_image(p, tmp_dir)
                if prepped:
                    content.append(load_image_block(prepped))

        if after_paths:
            content.append({"type": "text", "text": "AFTER (post-flood) photos:"})
            for p in after_paths:
                prepped = prep_image(p, tmp_dir)
                if prepped:
                    content.append(load_image_block(prepped))

        content.append({"type": "text", "text": f"Building address: {address}\n\nAssess the flood damage."})

        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

    raw = message.content[0].text.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # Model sometimes prefixes the JSON object with prose explanation
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise
            result = json.loads(match.group(0))

    result["address"] = address
    result["before_image_count"] = len(before_paths)
    result["after_image_count"] = len(after_paths)
    result["model"] = model
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def load_results() -> list[dict]:
    if RESULTS_PATH.exists():
        return json.loads(RESULTS_PATH.read_text())
    return []


def save_results(results: list[dict]) -> None:
    RESULTS_PATH.write_text(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Per-address flood damage assessment")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--start", type=int, default=0, help="Skip the first N addresses")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N addresses")
    args = parser.parse_args()

    after_addresses = sorted(p.name for p in AFTER_DIR.iterdir() if p.is_dir())
    before_addresses = sorted(p.name for p in BEFORE_DIR.iterdir() if p.is_dir())

    results = load_results()
    done = {r["address"] for r in results}

    todo = [a for a in after_addresses if a not in done]
    todo = todo[args.start:]
    if args.limit is not None:
        todo = todo[:args.limit]

    print(f"Total after-addresses : {len(after_addresses)}")
    print(f"Already processed     : {len(done)}")
    print(f"Processing this run   : {len(todo)}")
    print(f"Model                 : {args.model}")
    print(f"Vertex project        : {VERTEX_PROJECT} / {VERTEX_REGION}\n")

    client = AnthropicVertex(project_id=VERTEX_PROJECT, region=VERTEX_REGION)

    for i, address in enumerate(todo, 1):
        after_dir = AFTER_DIR / address
        after_paths = sorted(p for p in after_dir.iterdir() if p.is_file() and not p.name.startswith("."))

        before_match = find_before_dir(address, before_addresses)
        before_paths = []
        if before_match:
            before_dir = BEFORE_DIR / before_match
            before_paths = sorted(p for p in before_dir.iterdir() if p.is_file() and not p.name.startswith("."))

        print(f"[{i}/{len(todo)}] {address}  (before: {len(before_paths)}, after: {len(after_paths)})")

        if not after_paths:
            print("    SKIP: no after-flood photos for this address")
            results.append({
                "address": address,
                "damage_state": None,
                "confidence": "low",
                "water_depth_ft_exterior": None,
                "is_assessable": False,
                "rationale": "No after-flood photos available for this address.",
                "caveats": "after-photo folder is empty; nothing to assess",
                "before_image_count": len(before_paths),
                "after_image_count": 0,
                "model": args.model,
            })
            save_results(results)
            continue

        try:
            result = assess_address(client, address, before_paths, after_paths, args.model)
            ds = result.get("damage_state")
            conf = result.get("confidence")
            print(f"    → DS {ds} ({conf} confidence)")
        except Exception as exc:
            print(f"    ERROR: {exc}")
            result = {
                "address": address,
                "error": str(exc),
                "is_assessable": False,
                "damage_state": None,
                "confidence": "low",
                "before_image_count": len(before_paths),
                "after_image_count": len(after_paths),
                "model": args.model,
            }

        results.append(result)
        save_results(results)

    print(f"\nDone. {len(results)} total addresses in {RESULTS_PATH.name}")


if __name__ == "__main__":
    main()
