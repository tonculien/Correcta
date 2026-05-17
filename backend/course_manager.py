#!/usr/bin/env python3
"""Correcta course package manager.

.corr files are zip archives with this required structure:
- correcta.course.json
- grading.json
- assignments/<assignmentId>/assignment.json
- optional syllabus.md, knowledge/, README.md
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COURSES_DIR = ROOT / "courses"
CATALOG_PATH = COURSES_DIR / "catalog.json"
REMOVED_DIR = ROOT / "removed_courses"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_catalog() -> dict[str, Any]:
    COURSES_DIR.mkdir(parents=True, exist_ok=True)
    if not CATALOG_PATH.exists():
        catalog = {"activeCourseId": None, "installedCourses": [], "removedCourses": []}
        write_json(CATALOG_PATH, catalog)
        return catalog
    return read_json(CATALOG_PATH)


def save_catalog(catalog: dict[str, Any]) -> None:
    write_json(CATALOG_PATH, catalog)


def normalize_manifest_root(extracted_root: Path) -> Path:
    direct = extracted_root / "correcta.course.json"
    if direct.exists():
        return extracted_root
    matches = list(extracted_root.rglob("correcta.course.json"))
    if len(matches) == 1:
        return matches[0].parent
    if not matches:
        raise ValueError("Package is missing correcta.course.json")
    raise ValueError("Package has multiple correcta.course.json files; cannot choose safely")


def validate_assignment(path: Path, expected_course_id: str) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Missing assignment file: {path}")
    assignment = read_json(path)
    required = [
        "assignmentId",
        "courseId",
        "title",
        "appearsAtDay",
        "dueAtDay",
        "summary",
        "studentInstructions",
        "submissionRequirements",
        "rubric",
    ]
    missing = [key for key in required if key not in assignment]
    if missing:
        raise ValueError(f"{path} missing keys: {', '.join(missing)}")
    if assignment["courseId"] != expected_course_id:
        raise ValueError(f"{path} courseId does not match manifest courseId")
    if int(assignment["appearsAtDay"]) > int(assignment["dueAtDay"]):
        raise ValueError(f"{path} appearsAtDay cannot be after dueAtDay")
    points = sum(int(item.get("points", 0)) for item in assignment.get("rubric", []))
    if points != 100:
        raise ValueError(f"{path} rubric must add up to 100, got {points}")
    return assignment


def validate_package(package_path: Path) -> dict[str, Any]:
    package_path = package_path.resolve()
    if not package_path.exists():
        raise FileNotFoundError(package_path)
    if not zipfile.is_zipfile(package_path):
        raise ValueError(".corr package must be a valid zip archive")

    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        with zipfile.ZipFile(package_path, "r") as zf:
            zf.extractall(temp)
        root = normalize_manifest_root(temp)
        manifest = read_json(root / "correcta.course.json")

        required = ["packageType", "formatVersion", "courseId", "title", "durationDays", "entry", "assignments"]
        missing = [key for key in required if key not in manifest]
        if missing:
            raise ValueError(f"correcta.course.json missing keys: {', '.join(missing)}")
        if manifest["packageType"] != "correcta-course":
            raise ValueError("packageType must be correcta-course")

        course_id = manifest["courseId"]
        entry = manifest.get("entry", {})
        grading_path = root / entry.get("grading", "grading.json")
        if not grading_path.exists():
            raise ValueError("Missing grading.json")

        seen = set()
        for item in manifest.get("assignments", []):
            aid = item.get("assignmentId")
            rel = item.get("path")
            if not aid or not rel:
                raise ValueError("Each assignment entry must include assignmentId and path")
            if aid in seen:
                raise ValueError(f"Duplicate assignmentId in manifest: {aid}")
            seen.add(aid)
            assignment = validate_assignment(root / rel, course_id)
            if assignment["assignmentId"] != aid:
                raise ValueError(f"Assignment id mismatch: manifest {aid}, file {assignment['assignmentId']}")

        return manifest


def create_data_json(assignment: dict[str, Any]) -> dict[str, Any]:
    return {
        "assignmentId": assignment["assignmentId"],
        "status": "locked",
        "isVisible": False,
        "openedAtDay": assignment["appearsAtDay"],
        "dueAtDay": assignment["dueAtDay"],
        "lastUpdatedDay": 0,
        "submission": {
            "hasSubmission": False,
            "currentAttemptId": None,
            "submittedAtDay": None,
            "submittedAtDate": None,
            "submissionDir": None,
        },
        "grading": {
            "status": "not_graded",
            "queuedAtDay": None,
            "gradedAtDay": None,
            "aiOutputDir": None,
            "score": None,
            "letterGrade": None,
            "gpaValue": None,
        },
        "flags": {
            "isDueSoon": False,
            "isOverdue": False,
            "isLate": False,
            "isClosed": False,
        },
        "events": [],
    }


def import_package(package_path: Path, allow_overwrite: bool = False) -> None:
    manifest = validate_package(package_path)
    course_id = manifest["courseId"]
    target = COURSES_DIR / course_id
    if target.exists() and not allow_overwrite:
        raise FileExistsError(f"Course already installed: {course_id}")
    if target.exists() and allow_overwrite:
        shutil.rmtree(target)

    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        with zipfile.ZipFile(package_path, "r") as zf:
            zf.extractall(temp)
        package_root = normalize_manifest_root(temp)

        package_target = target / "package"
        shutil.copytree(package_root, package_target)

        runtime = target / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        write_json(runtime / "course_state.json", {
            "courseId": course_id,
            "mode": "github",
            "currentDay": 1,
            "durationDays": manifest["durationDays"],
            "lastDailyUpdateDay": 0,
            "graderMode": "mock",
            "installedAt": datetime.now().isoformat(timespec="seconds"),
        })
        write_json(runtime / "gradebook.json", {
            "courseId": course_id,
            "assignments": [],
            "currentAverage": None,
            "currentLetterGrade": None,
            "currentGpa": None,
            "finalEvaluation": None,
        })
        write_json(runtime / "system_log.json", [])

        course_json = {
            "courseId": course_id,
            "title": manifest["title"],
            "description": manifest.get("description", ""),
            "durationDays": manifest["durationDays"],
            "defaultGrader": "mock",
            "assignments": [item["assignmentId"] for item in manifest["assignments"]],
            "gradingScale": read_json(package_root / manifest.get("entry", {}).get("grading", "grading.json")).get("gradingScale", {}),
            "packageManifest": "package/correcta.course.json",
        }
        write_json(target / "course.json", course_json)

        for item in manifest["assignments"]:
            aid = item["assignmentId"]
            src_assignment = package_root / item["path"]
            assignment = read_json(src_assignment)
            adir = target / "assignments" / aid
            adir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_assignment, adir / "assignment.json")
            write_json(adir / "data.json", create_data_json(assignment))
            (adir / "submissions").mkdir(exist_ok=True)
            (adir / "ai_output").mkdir(exist_ok=True)
            (adir / "submissions" / ".gitkeep").write_text("", encoding="utf-8")
            (adir / "ai_output" / ".gitkeep").write_text("", encoding="utf-8")

    catalog = ensure_catalog()
    catalog["installedCourses"] = [c for c in catalog.get("installedCourses", []) if c.get("courseId") != course_id]
    catalog["installedCourses"].append({
        "courseId": course_id,
        "title": manifest["title"],
        "path": f"courses/{course_id}",
        "installedAt": datetime.now().isoformat(timespec="seconds"),
        "sourcePackage": str(package_path),
        "status": "active",
    })
    if not catalog.get("activeCourseId"):
        catalog["activeCourseId"] = course_id
    save_catalog(catalog)
    print(f"Imported course: {course_id}")


def uninstall_course(course_id: str) -> None:
    src = COURSES_DIR / course_id
    if not src.exists():
        raise FileNotFoundError(f"Course not installed: {course_id}")
    REMOVED_DIR.mkdir(parents=True, exist_ok=True)
    dest = REMOVED_DIR / f"{course_id}_{now_stamp()}"
    shutil.move(str(src), str(dest))

    report = {
        "courseId": course_id,
        "removedAt": datetime.now().isoformat(timespec="seconds"),
        "originalPath": f"courses/{course_id}",
        "archivePath": str(dest.relative_to(ROOT)),
        "includedData": ["package", "runtime", "assignments", "submissions", "ai_output"],
    }
    write_json(dest / "uninstall_report.json", report)

    catalog = ensure_catalog()
    installed = catalog.get("installedCourses", [])
    removed_meta = None
    new_installed = []
    for c in installed:
        if c.get("courseId") == course_id:
            removed_meta = dict(c)
        else:
            new_installed.append(c)
    catalog["installedCourses"] = new_installed
    if removed_meta:
        removed_meta.update({"archivePath": str(dest.relative_to(ROOT)), "removedAt": report["removedAt"]})
        catalog.setdefault("removedCourses", []).append(removed_meta)
    if catalog.get("activeCourseId") == course_id:
        catalog["activeCourseId"] = new_installed[0]["courseId"] if new_installed else None
    save_catalog(catalog)
    print(f"Archived course: {course_id} -> {dest.relative_to(ROOT)}")


def restore_course(archive_path: Path) -> None:
    src = (ROOT / archive_path).resolve() if not archive_path.is_absolute() else archive_path
    if not src.exists():
        raise FileNotFoundError(src)
    report_path = src / "uninstall_report.json"
    if not report_path.exists():
        raise ValueError("Archive is missing uninstall_report.json")
    report = read_json(report_path)
    course_id = report["courseId"]
    dest = COURSES_DIR / course_id
    if dest.exists():
        raise FileExistsError(f"Course already installed: {course_id}")
    shutil.move(str(src), str(dest))

    title = course_id
    course_json = dest / "course.json"
    if course_json.exists():
        title = read_json(course_json).get("title", course_id)

    catalog = ensure_catalog()
    catalog["installedCourses"] = [c for c in catalog.get("installedCourses", []) if c.get("courseId") != course_id]
    catalog["installedCourses"].append({
        "courseId": course_id,
        "title": title,
        "path": f"courses/{course_id}",
        "restoredAt": datetime.now().isoformat(timespec="seconds"),
        "status": "active",
    })
    catalog["removedCourses"] = [c for c in catalog.get("removedCourses", []) if c.get("archivePath") != str(archive_path)]
    if not catalog.get("activeCourseId"):
        catalog["activeCourseId"] = course_id
    save_catalog(catalog)
    print(f"Restored course: {course_id}")


def list_courses() -> None:
    catalog = ensure_catalog()
    print(json.dumps(catalog, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Correcta course package manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("package_path")

    p_import = sub.add_parser("import")
    p_import.add_argument("package_path")
    p_import.add_argument("--allow-overwrite", action="store_true")

    p_uninstall = sub.add_parser("uninstall")
    p_uninstall.add_argument("course_id")

    p_restore = sub.add_parser("restore")
    p_restore.add_argument("archive_path")

    sub.add_parser("list")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            manifest = validate_package(Path(args.package_path))
            print(f"Valid .corr package: {manifest['courseId']} — {manifest['title']}")
        elif args.command == "import":
            import_package(Path(args.package_path), allow_overwrite=args.allow_overwrite)
        elif args.command == "uninstall":
            uninstall_course(args.course_id)
        elif args.command == "restore":
            restore_course(Path(args.archive_path))
        elif args.command == "list":
            list_courses()
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
