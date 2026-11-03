"""Small, reusable Windows COM helpers for the Auto SolidWorks skill."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence


def _upstream_path() -> Path:
    value = os.environ.get("AUTO_SOLIDWORKS_UPSTREAM")
    if value:
        return Path(value)
    return Path.home() / ".codex" / "skills" / "solidworks-automation"


UPSTREAM = _upstream_path()
if str(UPSTREAM.parent) not in sys.path:
    sys.path.insert(0, str(UPSTREAM.parent))

if str(UPSTREAM) not in sys.path:
    sys.path.insert(0, str(UPSTREAM))

from scripts.sw_connect import get_com_member, mm
from scripts.sw_document_data import update_dimension_mm
from scripts.sw_export import export_to_step, export_to_stl
from scripts.sw_part import sketch
from scripts.sw_review import run_review
from scripts.sw_session import SolidWorksSession
from scripts.sw_sketch_quality import fully_define_sketch, inspect_model_sketches


class DirectSession(SolidWorksSession):
    """Use registered version-specific COM Dispatch and own only a new empty instance."""

    def __init__(self, prog_id: str | None = None, *, visible: bool = False):
        import win32com.client

        if prog_id is None:
            prog_id = os.environ.get("AUTO_SOLIDWORKS_PROGID")
        process_rows = csv.reader(subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV", "/NH"],
            text=True, errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
        ).splitlines())
        before_pids = {int(row[1]) for row in process_rows if len(row) > 1 and row[1].isdigit()}
        self.sw = win32com.client.Dispatch(prog_id) if prog_id else win32com.client.Dispatch("SldWorks.Application")
        pid = int(get_com_member(self.sw, "GetProcessID"))
        docs = list(get_com_member(self.sw, "GetDocuments") or [])
        self.model = None
        self.max_documents = 8
        self._owned_documents = []
        self.connection_info = {
            "process_id": pid,
            "started_by_cad_studio": pid not in before_pids,
            "prog_id": prog_id or "SldWorks.Application",
            "revision": str(get_com_member(self.sw, "RevisionNumber")),
            "documents_open_at_connect": len(docs),
        }
        if self.connection_info["started_by_cad_studio"]:
            self.sw.Visible = bool(visible)


def create_revolved_profile(
    model,
    name: str,
    points_mm: Sequence[tuple[float, float]],
    *,
    axis_y_mm: tuple[float, float],
):
    """Create a fully constrained closed straight-line profile revolved about sketch Y."""
    if len(points_mm) < 4 or points_mm[0] != points_mm[-1]:
        raise ValueError("Profile must contain at least three edges and repeat the first point at the end")
    with sketch(model, "Front Plane") as sketch_name:
        model.SketchManager.AddToDB = True
        try:
            axis = model.SketchManager.CreateCenterLine(0, mm(axis_y_mm[0]), 0, 0, mm(axis_y_mm[1]), 0)
            if axis is None:
                raise RuntimeError("Could not create the revolve centerline")
            for start, end in zip(points_mm, points_mm[1:]):
                segment = model.SketchManager.CreateLine(mm(start[0]), mm(start[1]), 0, mm(end[0]), mm(end[1]), 0)
                if segment is None:
                    raise RuntimeError(f"Sketch segment failed: {start} -> {end}")
        finally:
            model.SketchManager.AddToDB = False
        quality = fully_define_sketch(model)
        if quality.get("status") != "pass" or quality.get("fix_count"):
            raise RuntimeError(f"Profile did not become fully defined without Fix: {quality}")

    model.ClearSelection2(True)
    profile_feature = model.FeatureByName(str(sketch_name))
    if profile_feature is None or not profile_feature.Select2(False, 0):
        raise RuntimeError(f"Unable to select profile sketch: {sketch_name}")
    feature = model.FeatureManager.FeatureRevolve2(
        True, True, False, False, False, False,
        0, 0, 6.283185307179586, 0,
        False, False, 0.0, 0.0, 0, 0.0, 0.0,
        False, False, True,
    )
    if feature is None:
        raise RuntimeError(f"Native revolve failed for {name}")
    feature.Name = name
    model.ClearSelection2(True)
    if not model.ForceRebuild3(False):
        raise RuntimeError(f"Rebuild failed for {name}")
    return feature, {"profile": str(sketch_name), "feature": name, "quality": quality}


def body_summary(model) -> list[dict]:
    bodies = list(get_com_member(model, "GetBodies2", 0, False) or [])
    return [{
        "name": str(get_com_member(body, "Name")),
        "box_mm": [float(value) * 1000 for value in get_com_member(body, "GetBodyBox")],
        "face_count": len(get_com_member(body, "GetFaces") or []),
    } for body in bodies]


def _edit_probe(model, names: Sequence[str], explicit: tuple[str, float] | None) -> dict:
    candidates = [explicit[0]] if explicit else list(names)
    for name in candidates:
        dimension = model.Parameter(name)
        if dimension is None:
            continue
        nominal = float(get_com_member(dimension, "SystemValue")) * 1000
        delta = explicit[1] if explicit else 0.01
        if not explicit and not 5 < nominal < 100:
            continue
        trial = update_dimension_mm(model, name, nominal + delta, rebuild=True)
        restored = update_dimension_mm(model, name, nominal, rebuild=True)
        if not trial.get("success") or not restored.get("success"):
            raise RuntimeError(f"Dimension edit/restore failed for {name}: {trial}; {restored}")
        return {"dimension": name, "nominal_mm": nominal, "delta_mm": delta, "trial": trial, "restored": restored}
    if explicit:
        raise LookupError(f"Could not edit requested driving dimension: {explicit[0]}")
    return {"status": "not_run", "reason": "No candidate linear driving dimension was supplied or found"}


def verify_part_delivery(
    session: DirectSession,
    model,
    output_dir: str | Path,
    *,
    basename: str,
    expected_bodies: int | None = None,
    expected_envelope_mm: tuple[float, float, float] | None = None,
    envelope_tolerance_mm: float = 0.05,
    edit_dimension: tuple[str, float] | None = None,
    appearance_check: Callable | None = None,
) -> dict:
    """Save/reopen/rebuild, check editable sketches, export and review a simple native part."""
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    part, step, stl = (out / f"{basename}{ext}" for ext in (".SLDPRT", ".STEP", ".STL"))
    if not session.save(model, str(part)):
        raise RuntimeError(f"Could not save native model: {part}")
    session.close(model=model)
    model = session.open(str(part), silent=True, raise_on_error=True)
    if not model.ForceRebuild3(False):
        raise RuntimeError("Reopened part failed rebuild")
    if appearance_check:
        appearance_check(model)
    initial_sketch_evidence = inspect_model_sketches(model)
    if initial_sketch_evidence.get("status") != "pass":
        raise RuntimeError(f"Sketch check failed after reopen: {initial_sketch_evidence}")
    names = [name for item in initial_sketch_evidence.get("sketches", []) for name in item.get("dimension_names", [])]
    edit_evidence = _edit_probe(model, names, edit_dimension)
    sketch_evidence = inspect_model_sketches(model)
    if sketch_evidence.get("status") != "pass":
        raise RuntimeError(f"Sketch check failed after dimension restore: {sketch_evidence}")
    if appearance_check:
        appearance_check(model)
    if not session.save(model, str(part)):
        raise RuntimeError("Could not save model after restoring driving dimension")

    bodies = body_summary(model)
    if expected_bodies is not None and len(bodies) != expected_bodies:
        raise RuntimeError(f"Expected {expected_bodies} solid bodies; got {len(bodies)}")
    summary = get_com_member(model, "GetPartBox", True)
    envelope = tuple(sorted(float(summary[i + 3] - summary[i]) * 1000 for i in range(3)))
    if expected_envelope_mm is not None:
        expected = tuple(sorted(float(value) for value in expected_envelope_mm))
        if any(abs(a - b) > envelope_tolerance_mm for a, b in zip(envelope, expected)):
            raise RuntimeError(f"Unexpected envelope: got {envelope} mm, expected {expected} mm")

    for destination, exporter in ((step, export_to_step), (stl, export_to_stl)):
        if not exporter(model, str(destination)) or not destination.is_file() or destination.stat().st_size < 1024:
            raise RuntimeError(f"Export failed: {destination}")
    report, report_path = run_review(model, out, basename=basename, expected_outputs=[part, step, stl])
    if report["evaluation"]["status"] == "fail":
        raise RuntimeError(f"Review failed: {report['evaluation']}")
    session.close(model=model)
    neutral = session.open(str(step), silent=True, raise_on_error=True)
    neutral_bodies = body_summary(neutral)
    if expected_bodies is not None and len(neutral_bodies) != expected_bodies:
        raise RuntimeError(f"STEP round-trip solid count mismatch: {len(neutral_bodies)}")
    session.close(model=neutral)

    files = []
    for path in sorted(out.iterdir()):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append({"name": path.name, "size_bytes": path.stat().st_size, "sha256": digest})
    return {
        "status": "review_required",
        "reason": "Native SolidWorks delivery on the installed version requires human review unless this exact capability has been independently verified.",
        "output_dir": str(out),
        "solidworks": session.connection_info,
        "native_reopened_and_rebuilt": True,
        "body_count": len(bodies),
        "bodies": bodies,
        "envelope_sorted_mm": envelope,
        "sketches": sketch_evidence,
        "editability": edit_evidence,
        "appearance_check_performed": appearance_check is not None,
        "automated_review": report["evaluation"],
        "step_round_trip_body_count": len(neutral_bodies),
        "review_report": str(report_path),
        "files": files,
        "created_on": datetime.now().isoformat(),
    }


def probe() -> dict:
    with DirectSession() as session:
        return {
            "status": "ready",
            "connection": session.connection_info,
            "open_document_count": len(session._documents()),
            "note": "Connection probe only; existing documents were not edited, closed, or hidden.",
        }


def self_test(output_dir: str | Path) -> dict:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    with DirectSession() as session:
        model = session.new_part()
        create_revolved_profile(
            model, "SelfTestRing",
            [(10, 0), (14, 0), (14, 25), (10, 25), (10, 0)],
            axis_y_mm=(-5, 30),
        )
        report = verify_part_delivery(
            session, model, target, basename="SelfTestRing", expected_bodies=1,
            expected_envelope_mm=(28, 25, 28),
        )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="connect and report version/PID/documents only")
    parser.add_argument("--self-test", action="store_true", help="create a native ring in a new output directory and run delivery checks")
    parser.add_argument("--output", type=Path, help="new output directory for --self-test")
    args = parser.parse_args()
    if args.probe == args.self_test:
        parser.error("choose exactly one of --probe or --self-test")
    if args.self_test and args.output is None:
        parser.error("--self-test requires --output")
    result = probe() if args.probe else self_test(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
