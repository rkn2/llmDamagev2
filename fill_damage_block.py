"""One-off script to fill the damage-assessment block (cols 100-153, 243, 251)
for 5 State St rows in Montpelier_Flood_DataInput.xlsx, using address_assessments.json
results plus manual review of before/after photos.
"""
import openpyxl

XLSX = "Montpelier_Flood_DataInput.xlsx"

wb = openpyxl.load_workbook(XLSX)
ws = wb["BuidlingAttributes"]
headers = [c.value for c in ws[1]]
col = {h: i for i, h in enumerate(headers)}


def cardinal_visibility(front_orientation, vis):
    """Map front/back/left/right photo visibility to N/S/E/W given front_elevation_orientation."""
    if front_orientation == "n":
        return {"n": vis["front"], "s": vis["back"], "e": vis["left"], "w": vis["right"]}
    elif front_orientation == "s":
        return {"n": vis["back"], "s": vis["front"], "e": vis["right"], "w": vis["left"]}
    raise ValueError(front_orientation)


# row -> (flood_height_ft, front_orientation, visibility dict, notes)
ROWS = {
    30: (2.5, "s", {"front": False, "back": False, "left": False, "right": False},
         "damage_status/flood_height from address_assessments.json pipeline (DS2, ~2.5ft "
         "exterior water depth, medium confidence). After-photos for this address are "
         "aerial only (no street-level post-flood images) - wall/cladding/fenestration "
         "columns marked 'un' where facade not visible at ground level. Roof intact in "
         "aerial views. First-floor elevation (~5m) is well above the observed flood "
         "depth, consistent with DS2 reflecting basement-level flooding rather than "
         "structural damage. Foundation/basement not visually inspected."),
    56: (2.5, "n", {"front": True, "back": False, "left": False, "right": False},
         "damage_status/flood_height from address_assessments.json pipeline (DS2, ~2.5ft "
         "exterior water depth, medium confidence). After-set includes a 2024 "
         "street-level front (N) photo showing no visible structural/cladding/"
         "fenestration damage; back/left/right not covered by after-photos. Mansard "
         "roof intact in 2023 aerial. First-floor elevation (~3m) exceeds observed "
         "flood depth - DS2 likely reflects basement flooding, not visible exterior "
         "damage. Foundation/basement not visually inspected."),
    52: (1.5, "n", {"front": True, "back": True, "left": True, "right": False},
         "damage_status/flood_height from address_assessments.json pipeline (DS2, ~1.5ft "
         "exterior water depth, medium confidence). After-set includes 2023 "
         "street-level front (N), left (E) and back (S) photos, all showing the "
         "Romanesque sandstone/brick building intact with no visible damage; right (W) "
         "facade not covered. Roof intact in aerial. Raised stone basement "
         "(first-floor elevation ~3m) likely absorbed the ~1.5ft flood depth without "
         "visible exterior damage. Foundation/basement not visually inspected."),
    48: (2.0, "n", {"front": True, "back": False, "left": False, "right": False},
         "damage_status/flood_height from address_assessments.json pipeline (DS2, ~2.0ft "
         "exterior water depth, medium confidence). Only one before-photo and a 2024 "
         "street-level front (N) photo are available in the after-set, showing the "
         "Queen Anne house intact with no visible damage; back/left/right not covered. "
         "The 2023 aerial after-photo is too wide-area to identify this building's "
         "facades individually. First-floor elevation (~3m) exceeds the ~2ft flood "
         "depth - DS2 likely reflects basement-level flooding. Foundation/basement not "
         "visually inspected."),
    28: (3.0, "s", {"front": True, "back": False, "left": False, "right": False},
         "damage_status/flood_height from address_assessments.json pipeline (DS2, ~3.0ft "
         "exterior water depth, medium confidence). After-set is two wide-area aerials; "
         "the granite front (S) facade is visible at a distance with no obvious "
         "structural damage, but individual windows/cladding details aren't "
         "resolvable. Back/left/right not covered. FEMA zone X (0.2% annual chance, "
         "not in mapped SFHA) yet pipeline estimated ~3ft exterior water - flood depth "
         "here is less certain than for the other 4 buildings (all in zone AE). "
         "Foundation/basement not visually inspected."),
}


def v(visible):
    return 0 if visible else "un"


for row, (flood_ft, front_orient, vis, notes) in ROWS.items():
    cv = cardinal_visibility(front_orient, vis)

    values = {
        "flood_height_building": flood_ft,
        "hazards_present_u": "flood, rain",
        "status_u": "moderate",
        "rainwater_ingress_damage_rating_u": "un",
        "wind_damage_rating_u": 0,
        "damage_indicator_u": 2,
        "degree_of_damage_u": 2,
        "rain_damage_details_u": "un",
        "wind_damage_details_u": "not_applicable",
        "roof_structure_damage_u": 0,
        "roof_structure_damage_u_per": 0,
        "roof_substrate_damage_u": 0,
        "roof_substrate_damage_per": 0,
        "foundation_failure_u": 0,
        "foundation_failure_per_u": "un",
        "wall_structure_damage_per_front": v(vis["front"]),
        "wall_structure_damage_per_back": v(vis["back"]),
        "wall_structure_damage_per_left": v(vis["left"]),
        "wall_structure_damage_per_right": v(vis["right"]),
        "wall_structure_damage_u": 0,
        "wall_structure_damage_n": v(cv["n"]),
        "wall_structure_damage_s": v(cv["s"]),
        "wall_structure_damage_e": v(cv["e"]),
        "wall_structure_damage_w": v(cv["w"]),
        "wall_substrate_damage_per_front": "un",
        "wall_substrate_damage_per_back": "un",
        "wall_substrate_damage_per_right": "un",
        "wall_substrate_damage_per_left": "un",
        "wall_substrate_damage_n": "un",
        "wall_substrate_damage_s": "un",
        "wall_substrate_damage_e": "un",
        "wall_substrate_damage_w": "un",
        "wall_substrate_damage_u": "un",
        "wall_cladding_damage_per_front": v(vis["front"]),
        "wall_cladding_damage_per_back": v(vis["back"]),
        "wall_cladding_damage_per_right": v(vis["right"]),
        "wall_cladding_damage_per_left": v(vis["left"]),
        "wall_cladding_damage_n": v(cv["n"]),
        "wall_cladding_damage_s": v(cv["s"]),
        "wall_cladding_damage_e": v(cv["e"]),
        "wall_cladding_damage_w": v(cv["w"]),
        "damaged_fenesteration_per_front": v(vis["front"]),
        "damaged_fenesteration_per_back": v(vis["back"]),
        "damaged_fenesteration_per_right": v(vis["right"]),
        "damaged_fenesteration_per_left": v(vis["left"]),
        "wall_fenestration_damage_per_n": v(cv["n"]),
        "wall_fenestration_damage_per_s": v(cv["s"]),
        "wall_fenestration_damage_per_e": v(cv["e"]),
        "wall_fenestration_damage_per_w": v(cv["w"]),
        "soffit_damage_per_u": "not_applicable",
        "fascia_damage_per_u": 0,
        "piles_damage_u": "not_applicable",
        "foundation_damage_cause_u": "ot",
        "foundation_damage_u": 1,
        "foundation_damage_u_per": "un",
        "damage_status": 2,
        "Notes": notes,
    }

    for name, val in values.items():
        ws.cell(row=row, column=col[name] + 1).value = val

wb.save(XLSX)
print("done")
