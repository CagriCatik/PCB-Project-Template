"""Thermal model inputs: <project>/hardware/simulations/thermal/{thermal.json,power_sources.csv}.

Default material and convection values are typical literature values, not data
for any specific laminate or enclosure; every report lists which values were
defaults so they can be replaced with datasheet or measured values.
"""

import csv
import json
from pathlib import Path

from tools.core.common import KitError

FOLDER = "hardware/simulations/thermal"
BASES = ("calculation", "datasheet", "measurement", "estimate")
DEFAULTS = {
    "schema": 1,
    "ambient_c": 25.0,
    "grid_mm": 0.25,
    "h_top_w_m2k": 10.0,
    "h_bottom_w_m2k": 10.0,
    "copper_k_w_mk": 390.0,
    "dielectric_k_inplane_w_mk": 0.8,
    "dielectric_k_through_w_mk": 0.3,
    "copper_thickness_mm": {"F.Cu": None, "B.Cu": None},
    "via_plating_mm": 0.025,
    "board_max_c": 105.0,
    "hotspot_count": 10,
    "hotspot_separation_mm": 2.0,
}
NOTES = {
    "h_top_w_m2k": "natural convection incl. radiation, still air (typ. 5-15)",
    "h_bottom_w_m2k": "natural convection incl. radiation, still air (typ. 5-15)",
    "copper_k_w_mk": "electrodeposited copper (typ. 385-400)",
    "dielectric_k_inplane_w_mk": "FR-4 in-plane (typ. 0.6-1.0)",
    "dielectric_k_through_w_mk": "FR-4 through-plane (typ. 0.25-0.35)",
    "board_max_c": "laminate/solder-mask limit to check against; set from your laminate datasheet",
}


def load_config(project, overrides=None):
    path = Path(project) / FOLDER / "thermal.json"
    config = json.loads(json.dumps(DEFAULTS))
    from_file = {}
    if path.is_file():
        try:
            from_file = json.loads(path.read_text())
        except ValueError as exc:
            raise KitError("%s is not valid JSON: %s" % (path, exc))
        unknown = set(from_file) - set(DEFAULTS) - {"description", "notes"}
        if unknown:
            raise KitError("Unknown keys in %s: %s" % (path, ", ".join(sorted(unknown))))
        for key, value in from_file.items():
            if key in DEFAULTS:
                config[key] = value
    for key, value in (overrides or {}).items():
        if value is not None:
            config[key] = value
    sources = {k: ("override" if overrides and overrides.get(k) is not None else
                   "thermal.json" if k in from_file else "default") for k in DEFAULTS if k != "schema"}
    for key in ("grid_mm", "h_top_w_m2k", "h_bottom_w_m2k", "copper_k_w_mk", "dielectric_k_inplane_w_mk",
                "dielectric_k_through_w_mk", "via_plating_mm"):
        if not isinstance(config[key], (int, float)) or config[key] <= 0:
            raise KitError("Thermal parameter %s must be a positive number." % key)
    if not 0.05 <= config["grid_mm"] <= 5:
        raise KitError("grid_mm must be between 0.05 and 5 mm.")
    return config, sources, str(path) if path.is_file() else None


def load_power(project, extra=None):
    """Rows from power_sources.csv plus CLI overrides REF=W (basis 'estimate')."""
    path = Path(project) / FOLDER / "power_sources.csv"
    rows = {}
    if path.is_file():
        with path.open(newline="") as fp:
            for n, row in enumerate(csv.DictReader(fp), start=2):
                ref = (row.get("reference") or "").strip()
                if not ref or ref.startswith("#"):
                    continue
                try:
                    power = float(row.get("power_w") or "")
                except ValueError:
                    raise KitError("%s line %d: power_w must be a number." % (path, n))
                if power < 0:
                    raise KitError("%s line %d: power_w must not be negative." % (path, n))
                basis = (row.get("basis") or "estimate").strip()
                if basis not in BASES:
                    raise KitError("%s line %d: basis must be one of %s." % (path, n, "/".join(BASES)))
                rows[ref] = {"reference": ref, "power_w": power, "basis": basis,
                             "theta_jb_c_per_w": _optional(row.get("theta_jb_c_per_w"), path, n),
                             "limit_c": _optional(row.get("limit_c"), path, n),
                             "notes": (row.get("notes") or "").strip(), "origin": "power_sources.csv"}
    for item in extra or []:
        ref, _, value = item.partition("=")
        try:
            power = float(value)
        except ValueError:
            raise KitError("--power expects REF=WATTS, got %r" % item)
        rows[ref.strip()] = {"reference": ref.strip(), "power_w": power, "basis": "estimate",
                             "theta_jb_c_per_w": None, "limit_c": None, "notes": "command line",
                             "origin": "--power"}
    return list(rows.values()), str(path) if path.is_file() else None


def _optional(text, path, line):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise KitError("%s line %d: expected a number, got %r" % (path, line, text))
