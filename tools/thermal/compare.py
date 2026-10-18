"""Compare two thermal runs (e.g. before/after a layout change). Stdlib only."""

import json
from pathlib import Path

from tools.core.common import KitError


def _load(path):
    path = Path(path)
    if path.is_dir():
        path = path / "thermal.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise KitError("Cannot read thermal result %s: %s" % (path, exc))


def compare(a, b):
    ra, rb = _load(a), _load(b)
    keys = ("ambient_c", "power_in_w", "grid_mm")
    mismatched = [k for k in keys if abs(ra["summary"][k] - rb["summary"][k]) > 1e-9]
    comps = {}
    for side, run in (("before", ra), ("after", rb)):
        for c in run["components"]:
            if "board_max_c" in c:
                comps.setdefault(c["reference"], {})[side] = c["board_max_c"]
    rows = [{"reference": ref, "before_c": v.get("before"), "after_c": v.get("after"),
             "delta_k": round(v["after"] - v["before"], 2) if len(v) == 2 else None}
            for ref, v in sorted(comps.items())]
    return {
        "before": ra["output_directory"], "after": rb["output_directory"],
        "comparable": not mismatched, "differing_inputs": mismatched,
        "delta_max_top_k": round(rb["summary"]["max_top_c"] - ra["summary"]["max_top_c"], 2),
        "delta_max_bottom_k": round(rb["summary"]["max_bottom_c"] - ra["summary"]["max_bottom_c"], 2),
        "components": rows, "estimate": True,
    }


def compare_lines(r):
    lines = ["Thermal comparison (ESTIMATES): max top %+.2f K, max bottom %+.2f K"
             % (r["delta_max_top_k"], r["delta_max_bottom_k"])]
    if not r["comparable"]:
        lines.append("  ! inputs differ (%s); deltas mix layout and input changes" % ", ".join(r["differing_inputs"]))
    lines += ["  %-8s %8s -> %8s  %s" % (c["reference"], c["before_c"], c["after_c"],
                                         "%+.2f K" % c["delta_k"] if c["delta_k"] is not None else "n/a")
              for c in r["components"]]
    return lines
