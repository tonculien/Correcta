#!/usr/bin/env python3
"""Correcta course package manager.

.corr files are zip archives that contain a Correcta course package.
This script validates, imports, archives/uninstalls, restores, and lists courses.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COURSES_DIR = ROOT / "courses"
CATALOG_PATH = COURSES_DIR / "catalog.json"
REMOVED_DIR = ROOT / "removed_courses"

ALLOWED_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def archive_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_catalog() -> dict[str, Any]:
    COURSES_DIR.mkdir(parents=True, exist_ok=True)
    catalog = read_json(CATALOG_PATH, None)
    if not isinstance(catalog, dict):
        catalog = {"activeCourseId": None, "installedCourses": [], "removedCourses": []}
        # Preserve the original webdev course if it exists.
        if (COURSES_DIR / "webdev-30").exists():
            catalog["activeCourseId"] = "webdev-30"
            catalog["installedCourses"].append({
                "courseId": "webdev-30",
                "title": "30-Day Web Development",
                "path": "courses/webdev-30",
                "status": "active",
                "installedAt": "initial"
            })
        write_json(CATALOG_PATH, catalog)
    catalog.setdefault("installedCourses", [])
    catalog.setdefault("removedCourses", [])
    return catalog


def save_catalog(catalog: dict[str, Any]) -> None:
    write_json(CATALOG_PATH, catalog)


def find_manifest(extracted_root: Path) -> Path:
    direct = extracted_root / "correcta.course.json"
    if direct.exists():
        return direct
    matches = list(extracted_root.rglob("correcta.course.json"))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("Package does not contain correcta.course.json")
    raise ValueError("Package contains multiple correcta.course.json files")


def safe_rel(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe path in package: {path_str}")
    return path


def validate_assignment(assignment_path: Path) -> dict[str, Any]:
    if not assignment_path.exists():
        raise ValueError(f"Missing assignment file: {assignment_path}")
    assignment = read_json(assignment_path)
    if not isinstance(assignment, dict):
        raise ValueError(f"Invalid assignment JSON: {assignment_path}")
    required = ["assignmentId", "title", "appearsAtDay", "dueAtDay", "studentInstructions", "submissionRequirements", "rubric"]
    for key in required:
        if key not in assignment:
            raise ValueError(f"Assignment {assignment_path} missing {key}")
    if assignment["appearsAtDay"] > assignment["dueAtDay"]:
        raise ValueError(f"Assignment {assignment_path} has appearsAtDay > dueAtDay")
    rubric = assignment.get("rubric", [])
    if not isinstance(rubric, list) or not rubric:
        raise ValueError(f"Assignment {assignment_path} has invalid rubric")
    total = sum(int(item.get("points", 0)) for item in rubric)
    if total != 100:
        raise ValueError(f"Rubric for {assignment_path} totals {total}, expected 100")
    return assignment


def validate_corr(package_path: Path) -> dict[str, Any]:
    if not package_path.exists():
        raise FileNotFoundError(f"Package not found: {package_path}")
    if not zipfile.is_zipfile(package_path):
        raise ValueError(f"Not a valid .corr/.zip package: {package_path}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(package_path, "r") as zf:
            zf.extractall(tmp_path)
        manifest_path = find_manifest(tmp_path)
        package_root = manifest_path.parent
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise ValueError("correcta.course.json is not a JSON object")
        course_id = manifest.get("courseId")
        if not course_id or not ALLOWED_ID_RE.match(course_id):
            raise ValueError(f"Invalid courseId: {course_id!r}")
        if manifest.get("packageType") not in (None, "correcta-course"):
            raise ValueError("packageType must be correcta-course")
        assignments = manifest.get("assignments", [])
        if not isinstance(assignments, list) or not assignments:
            raise ValueError("Manifest must include assignments list")
        seen = set()
        for item in assignments:
            if not isinstance(item, dict):
                raise ValueError("Assignment manifest entries must be objects")
            aid = item.get("assignmentId")
            rel = item.get("path")
            if not aid or not rel:
                raise ValueError("Assignment entry missing assignmentId or path")
            if aid in seen:
                raise ValueError(f"Duplicate assignmentId: {aid}")
            seen.add(aid)
            assignment = validate_assignment(package_root / safe_rel(rel))
            if assignment.get("assignmentId") != aid:
                raise ValueError(f"Assignment id mismatch for {rel}")
        return manifest


def runtime_data_for(assignment: dict[str, Any]) -> dict[str, Any]:
    return {
        "assignmentId": assignment["assignmentId"],
        "status": "locked",
        "isVisible": False,
        "openedAtDay": None,
        "dueAtDay": assignment.get("dueAtDay"),
        "lastUpdatedDay": None,
        "submission": {
            "hasSubmission": False,
            "currentAttemptId": None,
            "submittedAtDay": None,
            "submittedAtDate": None,
            "submissionDir": None
        },
        "grading": {
            "status": "not_graded",
            "queuedAtDay": None,
            "gradedAtDay": None,
            "aiOutputDir": None,
            "score": None,
            "letterGrade": None,
            "gpaValue": None
        },
        "flags": {
            "isDueSoon": False,
            "isOverdue": False,
            "isLate": False,
            "isClosed": False
        },
        "events": []
    }


def import_corr(package_path: Path) -> None:
    manifest = validate_corr(package_path)
    course_id = manifest["courseId"]
    target = COURSES_DIR / course_id
    catalog = ensure_catalog()
    if target.exists() or any(c.get("courseId") == course_id for c in catalog["installedCourses"]):
        raise ValueError(f"Course already installed: {course_id}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(package_path, "r") as zf:
            zf.extractall(tmp_path)
        manifest_path = find_manifest(tmp_path)
        package_root = manifest_path.parent

        target.mkdir(parents=True, exist_ok=False)
        package_target = target / "package"
        shutil.copytree(package_root, package_target)

        runtime_dir = target / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        write_json(runtime_dir / "course_state.json", {
            "courseId": course_id,
            "mode": "github",
            "currentDay": 1,
            "durationDays": manifest.get("durationDays", 30),
            "status": "active",
            "lastDailyUpdateDay": None,
            "graderMode": "mock"
        })
        write_json(runtime_dir / "gradebook.json", {
            "courseId": course_id,
            "assignments": [],
            "currentAverage": None,
            "currentLetterGrade": None,
            "currentGpa": None,
            "finalEvaluation": None
        })
        write_json(runtime_dir / "system_log.json", [])

        course_json = {
            "courseId": course_id,
            "title": manifest.get("title", course_id),
            "description": manifest.get("description", ""),
            "durationDays": manifest.get("durationDays", 30),
            "assignments": [item["assignmentId"] for item in manifest["assignments"]],
            "gradingScale": read_json(package_root / safe_rel(manifest.get("entry", {}).get("grading", "grading.json")), {})
        }
        write_json(target / "course.json", course_json)

        assignments_dir = target / "assignments"
        for item in manifest["assignments"]:
            aid = item["assignmentId"]
            src = package_root / safe_rel(item["path"])
            assignment = read_json(src)
            assignment["courseId"] = course_id
            dest = assignments_dir / aid
            dest.mkdir(parents=True, exist_ok=True)
            write_json(dest / "assignment.json", assignment)
            write_json(dest / "data.json", runtime_data_for(assignment))
            (dest / "submissions").mkdir(exist_ok=True)
            (dest / "ai_output").mkdir(exist_ok=True)
            (dest / "submissions" / ".gitkeep").write_text("", encoding="utf-8")
            (dest / "ai_output" / ".gitkeep").write_text("", encoding="utf-8")

    catalog["installedCourses"].append({
        "courseId": course_id,
        "title": manifest.get("title", course_id),
        "description": manifest.get("description", ""),
        "path": f"courses/{course_id}",
        "status": "active",
        "installedAt": now_stamp(),
        "sourcePackage": str(package_path)
    })
    if not catalog.get("activeCourseId"):
        catalog["activeCourseId"] = course_id
    save_catalog(catalog)
    print(f"Imported course: {course_id}")


def uninstall_course(course_id: str) -> None:
    if not course_id:
        raise ValueError("course_id is required")
    target = COURSES_DIR / course_id
    if not target.exists():
        raise FileNotFoundError(f"Course not found: {course_id}")
    REMOVED_DIR.mkdir(parents=True, exist_ok=True)
    archive = REMOVED_DIR / f"{course_id}_{archive_stamp()}"
    shutil.move(str(target), str(archive))

    catalog = ensure_catalog()
    info = None
    remaining = []
    for item in catalog["installedCourses"]:
        if item.get("courseId") == course_id:
            info = item
        else:
            remaining.append(item)
    catalog["installedCourses"] = remaining
    if catalog.get("activeCourseId") == course_id:
        catalog["activeCourseId"] = remaining[0]["courseId"] if remaining else None
    catalog["removedCourses"].append({
        "courseId": course_id,
        "title": (info or {}).get("title", course_id),
        "archivePath": str(archive.relative_to(ROOT)),
        "removedAt": now_stamp()
    })
    write_json(archive / "uninstall_report.json", {
        "courseId": course_id,
        "removedAt": now_stamp(),
        "archivePath": str(archive.relative_to(ROOT)),
        "includedData": ["package", "runtime", "assignments", "submissions", "ai_output"]
    })
    save_catalog(catalog)
    print(f"Archived course: {course_id} -> {archive.relative_to(ROOT)}")


def restore_course(archive_path: Path) -> None:
    archive = ROOT / archive_path if not archive_path.is_absolute() else archive_path
    if not archive.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    report = read_json(archive / "uninstall_report.json", {})
    course_id = report.get("courseId") or archive.name.split("_")[0]
    target = COURSES_DIR / course_id
    if target.exists():
        raise ValueError(f"Course already exists: {course_id}")
    shutil.move(str(archive), str(target))
    course = read_json(target / "course.json", {})
    catalog = ensure_catalog()
    catalog["installedCourses"].append({
        "courseId": course_id,
        "title": course.get("title", course_id),
        "description": course.get("description", ""),
        "path": f"courses/{course_id}",
        "status": "active",
        "installedAt": now_stamp(),
        "sourcePackage": "restored"
    })
    catalog["removedCourses"] = [x for x in catalog.get("removedCourses", []) if x.get("archivePath") != str(archive_path)]
    if not catalog.get("activeCourseId"):
        catalog["activeCourseId"] = course_id
    save_catalog(catalog)
    print(f"Restored course: {course_id}")


def list_courses() -> None:
    catalog = ensure_catalog()
    print(json.dumps(catalog, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Correcta course manager")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate")
    p.add_argument("package_path")
    p = sub.add_parser("import")
    p.add_argument("package_path")
    p = sub.add_parser("uninstall")
    p.add_argument("course_id")
    p = sub.add_parser("restore")
    p.add_argument("archive_path")
    sub.add_parser("list")
    args = parser.parse_args()

    try:
        if args.cmd == "validate":
            manifest = validate_corr(ROOT / args.package_path)
            print(f"Valid .corr package: {manifest.get('courseId')}")
        elif args.cmd == "import":
            import_corr(ROOT / args.package_path)
        elif args.cmd == "uninstall":
            uninstall_course(args.course_id)
        elif args.cmd == "restore":
            restore_course(Path(args.archive_path))
        elif args.cmd == "list":
            list_courses()
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
