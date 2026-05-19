#!/usr/bin/env python3
"""Correcta daily scheduler.

This script is intentionally file-based because Correcta is GitHub-first:
- courses/<courseId>/ contains course.json and assignments/
- each assignment folder contains assignment.json, data.json, submissions/, ai_output/
- GitHub Actions runs this script and commits the generated state back to the repo.

Main responsibilities:
1. Wake assignments according to currentDay.
2. Scan submissions/ for uploaded files and convert loose uploads into attempt folders.
3. Queue and grade ungraded attempts.
4. Update per-course gradebook and system log.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grader_runner import grade_attempt
from gradebook_builder import rebuild_gradebook

ROOT = Path(__file__).resolve().parents[1]
COURSES_DIR = ROOT / "courses"
CATALOG_PATH = COURSES_DIR / "catalog.json"
GLOBAL_DATA_DIR = ROOT / "data"
GLOBAL_LOG_PATH = GLOBAL_DATA_DIR / "system_log.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        if fallback is not None:
            return fallback
        raise


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        # Backward-compatible fallback for old single-course repos.
        return {
            "activeCourseId": "webdev-30",
            "installedCourses": [
                {
                    "courseId": "webdev-30",
                    "title": "30-Day Web Development",
                    "path": "courses/webdev-30",
                    "status": "active",
                }
            ],
            "removedCourses": [],
        }
    return read_json(CATALOG_PATH, {"installedCourses": []})


def course_path_from_catalog_entry(entry: dict[str, Any]) -> Path:
    raw = entry.get("path") or f"courses/{entry.get('courseId')}"
    path = ROOT / raw
    return path.resolve()


def get_course_entries(course_arg: str) -> list[dict[str, Any]]:
    catalog = load_catalog()
    installed = catalog.get("installedCourses", [])

    if course_arg and course_arg != "all":
        entries = [c for c in installed if c.get("courseId") == course_arg]
        if not entries:
            raise SystemExit(f"Course not found in catalog: {course_arg}")
        return entries

    # By default, run every installed course except archived/removed items.
    return [
        c for c in installed
        if str(c.get("status", "active")).lower() in {"active", "installed", "paused"}
    ]


def append_global_log(day: int | None, event_type: str, message: str, course_id: str | None = None) -> None:
    logs = read_json(GLOBAL_LOG_PATH, [])
    logs.append(
        {
            "timestamp": now_iso(),
            "courseId": course_id,
            "day": day,
            "type": event_type,
            "message": message,
        }
    )
    write_json(GLOBAL_LOG_PATH, logs[-500:])


def append_assignment_event(data: dict[str, Any], day: int, event_type: str, message: str) -> None:
    events = data.setdefault("events", [])
    # Prevent duplicate day/type spam when workflow runs multiple times.
    if not any(e.get("day") == day and e.get("type") == event_type and e.get("message") == message for e in events):
        events.append({"day": day, "type": event_type, "message": message})


def ensure_assignment_data(assignment: dict[str, Any], data_path: Path) -> dict[str, Any]:
    data = read_json(data_path, None)
    aid = assignment["assignmentId"]

    if not isinstance(data, dict):
        data = {}

    data.setdefault("assignmentId", aid)
    data.setdefault("status", "locked")
    data.setdefault("isVisible", False)
    data.setdefault("openedAtDay", None)
    data.setdefault("dueAtDay", assignment.get("dueAtDay"))
    data.setdefault("lastUpdatedDay", None)
    data.setdefault(
        "submission",
        {
            "hasSubmission": False,
            "currentAttemptId": None,
            "submittedAtDay": None,
            "submittedAtDate": None,
            "submissionDir": None,
        },
    )
    data.setdefault(
        "grading",
        {
            "status": "not_graded",
            "queuedAtDay": None,
            "gradedAtDay": None,
            "aiOutputDir": None,
            "score": None,
            "letterGrade": None,
            "gpaValue": None,
        },
    )
    data.setdefault(
        "flags",
        {
            "isDueSoon": False,
            "isOverdue": False,
            "isLate": False,
            "isClosed": False,
        },
    )
    data.setdefault("events", [])
    return data


def assignment_folders(course_dir: Path, course: dict[str, Any]) -> list[Path]:
    root = course_dir / "assignments"
    result: list[Path] = []
    for aid in course.get("assignments", []):
        if isinstance(aid, str):
            result.append(root / aid)
        elif isinstance(aid, dict):
            # Allow future manifest-like entries.
            assignment_id = aid.get("assignmentId") or aid.get("id")
            if assignment_id:
                result.append(root / assignment_id)
    return result


def update_assignment_status(
    assignment: dict[str, Any],
    data: dict[str, Any],
    current_day: int,
) -> None:
    appears = int(assignment.get("appearsAtDay", 1))
    due = int(assignment.get("dueAtDay", appears))
    grading_status = str(data.get("grading", {}).get("status", "")).lower()
    has_submission = bool(data.get("submission", {}).get("hasSubmission"))

    data["isVisible"] = current_day >= appears
    data["lastUpdatedDay"] = current_day
    data["dueAtDay"] = due

    flags = data.setdefault("flags", {})
    flags["isDueSoon"] = False
    flags["isOverdue"] = False

    if grading_status == "graded":
        data["status"] = "graded"
        return

    if has_submission:
        data["status"] = "submitted"
        return

    if current_day < appears:
        data["status"] = "locked"
        data["isVisible"] = False
        return

    if data.get("openedAtDay") is None:
        data["openedAtDay"] = appears
        append_assignment_event(
            data,
            current_day,
            "assignment_available",
            f"{assignment.get('title', assignment.get('assignmentId'))} became available.",
        )

    if current_day > due:
        data["status"] = "overdue"
        flags["isOverdue"] = True
        append_assignment_event(
            data,
            current_day,
            "assignment_overdue",
            f"{assignment.get('title', assignment.get('assignmentId'))} is overdue.",
        )
        return

    days_until_due = due - current_day
    if days_until_due <= 2:
        data["status"] = "due_soon"
        flags["isDueSoon"] = True
        if days_until_due == 0:
            append_assignment_event(
                data,
                current_day,
                "assignment_due_today",
                f"{assignment.get('title', assignment.get('assignmentId'))} is due today.",
            )
    else:
        data["status"] = "available"


def existing_attempt_numbers(submissions_dir: Path) -> list[int]:
    nums: list[int] = []
    if not submissions_dir.exists():
        return nums
    for child in submissions_dir.iterdir():
        if child.is_dir() and child.name.startswith("attempt-"):
            try:
                nums.append(int(child.name.split("-", 1)[1]))
            except ValueError:
                pass
    return sorted(nums)


def next_attempt_id(submissions_dir: Path) -> str:
    nums = existing_attempt_numbers(submissions_dir)
    return f"attempt-{(nums[-1] + 1) if nums else 1:03d}"


def loose_submission_files(submissions_dir: Path) -> list[Path]:
    if not submissions_dir.exists():
        return []
    files = []
    for child in submissions_dir.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir() and child.name.startswith("attempt-"):
            continue
        files.append(child)
    return files


def normalize_loose_submission(
    course_id: str,
    assignment: dict[str, Any],
    assignment_dir: Path,
    data: dict[str, Any],
    current_day: int,
) -> bool:
    submissions_dir = assignment_dir / "submissions"
    submissions_dir.mkdir(parents=True, exist_ok=True)

    loose = loose_submission_files(submissions_dir)
    if not loose:
        return False

    attempt_id = next_attempt_id(submissions_dir)
    attempt_dir = submissions_dir / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)

    for item in loose:
        dest = attempt_dir / item.name
        if dest.exists():
            # If a duplicate somehow exists, keep the new one with timestamp suffix.
            dest = attempt_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{item.name}"
        shutil.move(str(item), str(dest))

    rel_attempt = attempt_dir.relative_to(ROOT).as_posix()
    rel_output = (assignment_dir / "ai_output" / attempt_id).relative_to(ROOT).as_posix()

    data["submission"] = {
        "hasSubmission": True,
        "currentAttemptId": attempt_id,
        "submittedAtDay": current_day,
        "submittedAtDate": now_iso(),
        "submissionDir": rel_attempt,
    }
    data["grading"] = {
        "status": "queued",
        "queuedAtDay": current_day,
        "gradedAtDay": None,
        "aiOutputDir": rel_output,
        "score": None,
        "letterGrade": None,
        "gpaValue": None,
    }
    data["status"] = "submitted"
    append_assignment_event(
        data,
        current_day,
        "submitted",
        f"Student submitted {attempt_id}.",
    )
    append_assignment_event(
        data,
        current_day,
        "grading_queued",
        f"{attempt_id} queued for grading.",
    )
    append_global_log(
        current_day,
        "submission_detected",
        f"{course_id}/{assignment['assignmentId']} detected {attempt_id}.",
        course_id,
    )
    return True


def grade_if_needed(
    course_dir: Path,
    course_id: str,
    assignment: dict[str, Any],
    assignment_dir: Path,
    data: dict[str, Any],
    current_day: int,
    grader: str,
) -> bool:
    grading = data.get("grading", {})
    if grading.get("status") != "queued":
        return False

    attempt_id = data.get("submission", {}).get("currentAttemptId")
    if not attempt_id:
        return False

    grade = grade_attempt(course_dir, assignment_dir, assignment, data, attempt_id, grader)

    grading["status"] = "graded"
    grading["gradedAtDay"] = current_day
    grading["score"] = grade.get("finalScore")
    grading["letterGrade"] = grade.get("letterGrade")
    grading["gpaValue"] = grade.get("gpaValue")
    data["status"] = "graded"

    append_assignment_event(
        data,
        current_day,
        "graded",
        f"{attempt_id} graded. Score: {grade.get('finalScore')}.",
    )
    append_global_log(
        current_day,
        "graded",
        f"{course_id}/{assignment['assignmentId']} {attempt_id} graded.",
        course_id,
    )
    return True


def run_course_daily(course_entry: dict[str, Any], grader: str) -> None:
    course_id = course_entry.get("courseId")
    course_dir = course_path_from_catalog_entry(course_entry)
    course_json_path = course_dir / "course.json"

    if not course_json_path.exists():
        append_global_log(None, "course_missing", f"Missing course.json for {course_id}", course_id)
        return

    course = read_json(course_json_path, {})
    current_day = int(course.get("currentDay") or course.get("startDay") or 1)
    duration = int(course.get("durationDays", 30))
    current_day = max(1, min(current_day, duration))

    changed_any = False

    for assignment_dir in assignment_folders(course_dir, course):
        assignment_path = assignment_dir / "assignment.json"
        if not assignment_path.exists():
            append_global_log(current_day, "assignment_missing", f"Missing {assignment_path}", course_id)
            continue

        assignment = read_json(assignment_path, {})
        data_path = assignment_dir / "data.json"
        data = ensure_assignment_data(assignment, data_path)

        before = json.dumps(data, sort_keys=True, ensure_ascii=False)

        update_assignment_status(assignment, data, current_day)
        normalize_loose_submission(course_id, assignment, assignment_dir, data, current_day)
        grade_if_needed(course_dir, course_id, assignment, assignment_dir, data, current_day, grader)

        after = json.dumps(data, sort_keys=True, ensure_ascii=False)
        if before != after:
            changed_any = True
            write_json(data_path, data)

    gradebook = rebuild_gradebook(course_dir)
    append_global_log(current_day, "daily_update", f"Daily update completed for {course_id}.", course_id)

    # Keep legacy/global gradebook for currently viewed course if this course is active.
    # Frontend can also read per-course gradebooks if present.
    if course_entry.get("courseId") == load_catalog().get("activeCourseId"):
        legacy_gradebook = GLOBAL_DATA_DIR / "gradebook.json"
        write_json(legacy_gradebook, gradebook)

    if changed_any:
        print(f"Updated course: {course_id}")
    else:
        print(f"No assignment state changes for course: {course_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Correcta daily scheduler")
    parser.add_argument("--daily", action="store_true", help="Run daily update")
    parser.add_argument("--course", default="all", help="Course ID to update, or all")
    parser.add_argument("--grader", default="mock", choices=["mock", "opencode"], help="Grader mode")
    parser.add_argument("--status", action="store_true", help="Print catalog status")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(load_catalog(), indent=2, ensure_ascii=False))
        return

    if not args.daily:
        parser.error("Nothing to do. Use --daily or --status.")

    entries = get_course_entries(args.course)
    if not entries:
        print("No courses to update.")
        return

    for entry in entries:
        run_course_daily(entry, args.grader)


if __name__ == "__main__":
    main()
