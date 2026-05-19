# llmDamagev2 — LLM-Assisted Flood Damage Assessment

A Python pipeline that uses the Claude Vision API (Anthropic) to assess flood damage states from building images and write structured results into a research building inventory spreadsheet.

Built for the **2023 Montpelier, VT flood event** as part of a broader IN-CORE / NSI-based loss estimation workflow, but designed to generalize to any flood image dataset.

---

## What it does

1. **Reads images** from a folder (JPG, PNG, WebP, GIF, AVIF)
2. **Sends each image to Claude** with a structured prompt containing the damage state definitions
3. **Parses a structured JSON response** — damage state, water depth estimate, confidence, rationale
4. **Attempts to match** the assessed building to a row in a building inventory spreadsheet (fuzzy address matching)
5. **Writes results** to a `DamageAssessments` tab in the spreadsheet, and backfills `damage_status` and `flood_height_building` columns in the main inventory when a match is found

---

## Damage State Scale

| State | Label | Description |
|-------|-------|-------------|
| 0 | None | Insignificant damage below first-floor elevation. Water touches foundation/crawlspace only. No sewer backup into living area. |
| 1 | Minor | Water at floor joist level up to minor entry. Damage to carpets, pads, baseboards, flooring. No drywall damage. Minor sewer backup possible. |
| 2 | Moderate | Partial drywall damage. Base electrical outlets, water heater, furnace damaged. Complete first-floor appliance/furniture loss. Lower cabinets damaged. Major sewer backup and mold. |
| 3 | Extensive | Damage throughout whole building including upper stories. Mid-wall electrical destroyed. Upper cabinets destroyed. Studs reusable. Major mold. Upper-floor contents also damaged. |
| 4 | Complete | Significant structural damage to studs, trusses, joists. All interiors destroyed. Roof components damaged. Foundation may have shifted. Demolition required. |

This scale is adapted from Nofal & van de Lindt (2020) and is consistent with HAZUS flood damage categories.

---

## File Structure

```
llmDamagev2/
├── assess_damage.py              # Main assessment pipeline
├── Montpelier_Flood_DataInput.xlsx  # Building inventory (318-column schema)
├── Image gallery/                # Input images
│   ├── Capitol Building.png
│   ├── Fire and Ambulance Department.jpg
│   ├── Main St.png
│   └── ...
└── README.md
```

---

## Installation

```bash
pip install anthropic openpyxl
```

AVIF images are automatically converted to PNG on macOS using the built-in `sips` utility — no additional install needed. On Linux, install `libavif` or pre-convert AVIF files to PNG manually.

---

## Usage

Set your Anthropic API key as an environment variable, then run:

```bash
# Process all images in Image gallery/
ANTHROPIC_API_KEY=sk-ant-... python assess_damage.py

# Process a single image (good for testing)
ANTHROPIC_API_KEY=sk-ant-... python assess_damage.py --image "Fire and Ambulance Department.jpg"

# Use a more capable model for higher accuracy
ANTHROPIC_API_KEY=sk-ant-... python assess_damage.py --model claude-opus-4-7
```

Available models (Anthropic, as of 2025):
- `claude-sonnet-4-6` — default, good balance of cost and accuracy
- `claude-opus-4-7` — highest accuracy, recommended for final research runs
- `claude-haiku-4-5-20251001` — fastest and cheapest, lower accuracy

---

## Output

### DamageAssessments sheet (always written)

Every processed image gets a row with these columns:

| Column | Description |
|--------|-------------|
| `image_file` | Source filename |
| `identified_building` | Claude's best-guess building name |
| `identified_address` | Claude's best-guess street address |
| `damage_state` | 0–4 integer (null if image is not assessable) |
| `confidence` | `high` / `medium` / `low` |
| `water_depth_ft_exterior` | Estimated water depth at building exterior in feet |
| `image_type` | `during_flood` / `post_flood` / `aerial_overview` / `unclear` |
| `is_assessable` | `False` for pure aerials or unidentifiable scenes |
| `rationale` | 1–2 sentence explanation citing specific visual evidence |
| `caveats` | What the model could not see (interior, rear facade, etc.) |
| `matched_excel_row` | Row number matched in BuidlingAttributes, or blank |
| `matched_address` | Address it matched to in the spreadsheet |
| `model` | Claude model used |

Rows highlighted in **yellow** require human review (low confidence, not assessable, or null damage state).

### BuidlingAttributes sheet (written when a match is found)

When an assessed address matches an existing row in the inventory (≥75% string similarity):
- `damage_status` (col IJ) ← damage state integer
- `flood_height_building` (col C) ← water depth estimate in feet

---

## Building Inventory Schema

The spreadsheet (`Montpelier_Flood_DataInput.xlsx`) uses a 318-column schema covering:

- **Location**: address, lat/lon, FEMA flood zone, distance from river
- **Structure**: archetype (F1–F15), occupancy type, number of stories, year built, floor area, building height, first floor elevation
- **Construction details**: wall system, foundation type, roof system, cladding, fenestration by facade
- **Damage fields**: damage_status, flood_height_building, and detailed per-component damage percentages
- **Heritage/ownership**: NRHP listing, property values, owner type
- **Temporal**: building use before/during/after flood, demolition status, restoration status

The archetype codes (F1–F15) follow Nofal & van de Lindt (2020) and are used as inputs to the pyIncore `BuildingDamage` analysis.

---

## Connecting to the NSI / IN-CORE Pipeline

This repository is the **image-based damage assessment** component of a larger workflow:

```
NSI API → Building Inventory (GeoDataFrame)
               ↓
     NOAA HAND-FIM + NWM → Flood Depth Raster
               ↓
     pyIncore BuildingDamage → Model-predicted damage states
               ↓
     assess_damage.py (this repo) → Observed damage states from images
               ↓
     Compare modeled vs. observed for calibration / validation
```

The companion notebook (`montpelier_flood_incore.ipynb`) handles steps 1–3 using the `fimserve`, `dataretrieval`, and `pyincore` libraries.

---

## Known Limitations

- **Exterior-only assessment**: All damage states are inferred from exterior photos and water depth at the building face. Interior damage (drywall, electrical, mold) is inferred from water depth relative to building thresholds, not directly observed. Post-flood interior photos would significantly improve DS 2/3 differentiation.
- **During-flood vs. post-flood**: Most available imagery shows active flooding, which supports water depth estimation but not structural damage confirmation. DS 3–4 distinctions require post-flood or interior imagery.
- **Aerial images**: Wide aerials capture flood extent well but cannot support building-level damage assessment. The pipeline flags these as `is_assessable: False`.
- **Address matching**: The fuzzy matcher uses 75% string similarity. Buildings not in the spreadsheet inventory will not be matched — their assessments still appear in `DamageAssessments` and can be used to add new rows.
- **AVIF support**: Requires macOS `sips` for automatic conversion. On other platforms, convert AVIF to PNG before running.

---

## Citation

If you use this pipeline in research, please cite:

> Napolitano, R. (2025). llmDamagev2: LLM-assisted flood damage assessment pipeline. GitHub. https://github.com/rkn2/llmDamagev2

And the damage scale reference:

> Nofal, O.M. & van de Lindt, J.W. (2020). Understanding flood risk in the context of community resilience modeling for the built environment. *Sustainable and Resilient Infrastructure*, 5(3), 145–157.

---

## License

MIT
