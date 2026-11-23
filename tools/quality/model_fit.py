"""3D model fit check of one footprint (review images; the project board is never written).

KiCad's own Python copies footprint REF from the board onto an empty scratch board in the evidence run
(pads, silkscreen, fab and courtyard as on the board, top side, orientation 0) and replaces its 3D models
by MODEL with the given offset (mm) and rotation (degrees). `kicad-cli pcb render` then draws top, front,
left and iso views. Use it to align a vendor or drawing-derived model before entering offset/rotation in
the footprint. Rendered images are review evidence, not proof of mechanical fit: compare them with the
model's drawing and check pin 1, seating plane and body outline against the courtyard and fab layer.
"""
import json
from pathlib import Path

from tools.core import kicad_env
from tools.core.common import KitError, now, project_files, run, sha256, write_json

SCRATCH = r'''
import json, os, sys
import pcbnew
cfg = json.loads(sys.argv[1])
M = pcbnew.FromMM
src = pcbnew.LoadBoard(cfg["board"])
fp = src.FindFootprintByReference(cfg["reference"])
if fp is None:
    print(json.dumps({"error": "footprint %s not on the board" % cfg["reference"]}))
    sys.stdout.flush()
    os._exit(3)
nb = pcbnew.CreateEmptyBoard()
nfp = pcbnew.FOOTPRINT(fp)
nfp.SetParent(nb)
if nfp.IsFlipped():
    nfp.Flip(nfp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
nfp.SetOrientationDegrees(0)
nfp.SetPosition(pcbnew.VECTOR2I(M(50), M(50)))
old = [m.m_Filename for m in nfp.Models()]
nfp.Models().clear()
m = pcbnew.FP_3DMODEL()
m.m_Filename = cfg["model"]
m.m_Offset = pcbnew.VECTOR3D(*cfg["offset"])
m.m_Rotation = pcbnew.VECTOR3D(*cfg["rotation"])
m.m_Scale = pcbnew.VECTOR3D(1, 1, 1)
nfp.Add3DModel(m)
nb.Add(nfp)
bb = nfp.GetBoundingBox(False)
pad = M(4)
x1, y1, x2, y2 = bb.GetLeft() - pad, bb.GetTop() - pad, bb.GetRight() + pad, bb.GetBottom() + pad
for a, c in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))):
    s = pcbnew.PCB_SHAPE(nb)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(pcbnew.VECTOR2I(*a))
    s.SetEnd(pcbnew.VECTOR2I(*c))
    s.SetWidth(M(0.1))
    nb.Add(s)
nb.Save(cfg["output"])
print(json.dumps({"footprint": str(fp.GetFPID().GetUniStringLibItemName()), "replaced_models": old}))
sys.stdout.flush()
os._exit(0)  # SWIG teardown of copied footprints may crash after a successful save
'''

VIEWS = {"top": ["--side", "top"], "front": ["--side", "front"], "left": ["--side", "left"],
         "iso": ["--perspective", "--rotate", "-55,0,35"]}


def _fit(project, reference, model, offset, rotation, folder):
    board = project_files(project)[2]
    model = Path(model).expanduser().resolve()
    if not model.is_file():
        raise KitError("3D model not found: %s" % model, 13)
    python, cli = kicad_env.bundled_python(), kicad_env.kicad_cli_path()
    if not python or not cli:
        raise KitError("Model fit needs KiCad %s (bundled Python with pcbnew and kicad-cli)." % kicad_env.KICAD_VERSION, 3)
    folder.mkdir(parents=True, exist_ok=True)
    scratch = folder / ("fit_%s.kicad_pcb" % reference)
    before = sha256(board)
    cfg = {"board": str(board), "reference": reference, "model": str(model), "offset": list(offset),
           "rotation": list(rotation), "output": str(scratch)}
    rec = run([python, "-c", SCRATCH, json.dumps(cfg)], timeout=180)
    lines = [l for l in rec["stdout"].splitlines() if l.startswith("{")]
    info = json.loads(lines[-1]) if lines else {}
    if rec["exit_code"] or not scratch.is_file() or "error" in info:
        raise KitError("Scratch board not created: %s" % (info.get("error") or rec["stderr"][-400:]), 13)
    images, renders = {}, []
    for name, args in VIEWS.items():
        png = folder / ("fit_%s_%s.png" % (reference, name))
        r = run([cli, "pcb", "render", "-o", png, "--width", "1000", "--height", "700", "--quality", "high",
                 "--background", "opaque"] + args + [scratch], timeout=300)
        renders.append({k: r[k] for k in ("argv", "exit_code")})
        if r["exit_code"] or not png.is_file():
            raise KitError("kicad-cli render failed for view %s: %s" % (name, r["stderr"][-400:]), 13)
        images[name] = {"file": str(png), "sha256": sha256(png)}
    if sha256(board) != before:
        raise KitError("Board changed during the model fit run; repeat on a stable board.", 13)
    return {"status": "IMAGES_READY", "created": now(), "board": str(board), "board_sha256": before,
            "reference": reference, "footprint": info.get("footprint"), "replaced_models": info.get("replaced_models"),
            "model": str(model), "model_sha256": sha256(model), "offset_mm": list(offset),
            "rotation_deg": list(rotation), "scratch_board": str(scratch), "images": images, "renders": renders,
            "visual_review": "PENDING",
            "limitations": ["Images only; a person compares them with the model drawing and the footprint "
                            "(pin 1, seating plane, body vs courtyard).",
                            "The scratch board carries only this footprint; neighbours and enclosure are not shown."]}


def run_fit(project, reference, model, offset=(0, 0, 0), rotation=(0, 0, 0)):
    """Images, scratch board and result.json share one run folder; a failed run is marked FAILED."""
    import tempfile

    parent = Path(project).resolve() / "qa/generated/model-fit"
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    try:
        result = _fit(project, reference, model, offset, rotation, folder)
    except Exception as exc:
        write_json(folder / "result.json", {"status": "FAILED", "created": now(), "directory": str(folder),
                                            "error": str(exc)})
        if isinstance(exc, KitError):
            raise KitError("%s (failed run: %s)" % (exc, folder), exc.exit_code) from exc
        raise
    result["directory"] = str(folder)
    write_json(folder / "result.json", result)
    return result
