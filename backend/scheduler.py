from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from grader_runner import grade_assignment
from gradebook_builder import rebuild_gradebook

ROOT = Path(__file__).resolve().parents[1]
COURSES_ROOT = ROOT / "courses"
DATA_DIR = ROOT / "data"
CATALOG_PATH = COURSES_ROOT / "catalog.json"


def read_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        if fallback is not None:
            return fallback
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_catalog() -> Dict[str, Any]:
    fallback = {
        "activeCourseId": "webdev-30",
        "installedCourses": [{"courseId": "webdev-30", "title": "30-Day Web Development", "path": "courses/webdev-30", "status": "active"}],
        "removedCourses": [],
    }
    return read_json(CATALOG_PATH, fallback)


def course_dir(course_id: str) -> Path:
    return COURSES_ROOT / course_id


def course_runtime_dir(cdir: Path) -> Path:
    return cdir / "runtime"


def legacy_data_path(filename: str) -> Path:
    return DATA_DIR / filename


def runtime_path(cdir: Path, filename: str) -> Path:
    return course_runtime_dir(cdir) / filename


def course(cdir: Path) -> Dict[str, Any]:
    return read_json(cdir / "course.json")


def ensure_runtime(cdir: Path) -> None:
    crs = course(cdir)
    runtime = course_runtime_dir(cdir)
    runtime.mkdir(parents=True, exist_ok=True)
    cid = crs.get("courseId", cdir.name)

    state_file = runtime / "course_state.json"
    if not state_file.exists():
        legacy = read_json(legacy_data_path("course_state.json"), None) if cid == "webdev-30" else None
        state = legacy or {
            "courseId": cid,
            "mode": "github",
            "currentDay": 1,
            "durationDays": crs.get("durationDays", 30),
            "lastDailyUpdateDay": 0,
            "graderMode": crs.get("defaultGrader", "mock"),
            "updatedAt": utc_now(),
        }
        state["courseId"] = cid
        state.setdefault("durationDays", crs.get("durationDays", 30))
        write_json(state_file, state)

    gradebook_file = runtime / "gradebook.json"
    if not gradebook_file.exists():
        legacy = read_json(legacy_data_path("gradebook.json"), None) if cid == "webdev-30" else None
        write_json(gradebook_file, legacy or {"courseId": cid, "assignments": [], "currentAverage": None, "currentLetterGrade": None, "currentGpa": None, "finalEvaluation": None, "updatedAt": utc_now()})

    log_file = runtime / "system_log.json"
    if not log_file.exists():
        legacy = read_json(legacy_data_path("system_log.json"), None) if cid == "webdev-30" else None
        write_json(log_file, legacy or [])


def log(cdir: Path, message: str, day: int | None = None, event_type: str = "system") -> None:
    ensure_runtime(cdir)
    path = runtime_path(cdir, "system_log.json")
    logs = read_json(path, [])
    logs.append({"day": day, "type": event_type, "message": message, "at": utc_now()})
    write_json(path, logs[-300:])

    # Backward compatibility for webdev-30.
    if cdir.name == "webdev-30":
        write_json(legacy_data_path("system_log.json"), logs[-300:])


def state(cdir: Path) -> Dict[str, Any]:
    ensure_runtime(cdir)
    return read_json(runtime_path(cdir, "course_state.json"))


def save_state(cdir: Path, data: Dict[str, Any]) -> None:
    data["updatedAt"] = utc_now()
    write_json(runtime_path(cdir, "course_state.json"), data)
    if cdir.name == "webdev-30":
        write_json(legacy_data_path("course_state.json"), data)


def assignment_folder(cdir: Path, aid: str) -> Path:
    return cdir / "assignments" / aid


def load_assignment(cdir: Path, aid: str) -> Dict[str, Any]:
    return read_json(assignment_folder(cdir, aid) / "assignment.json")


def load_assignment_data(cdir: Path, aid: str) -> Dict[str, Any]:
    return read_json(assignment_folder(cdir, aid) / "data.json")


def save_assignment_data(cdir: Path, aid: str, data: Dict[str, Any]) -> None:
    data["lastUpdatedDay"] = state(cdir).get("currentDay", 1)
    write_json(assignment_folder(cdir, aid) / "data.json", data)


def add_event(data: Dict[str, Any], day: int, event_type: str, message: str) -> None:
    data.setdefault("events", []).append({"day": day, "type": event_type, "message": message, "at": utc_now()})


def submission_items(submissions_dir: Path) -> List[Path]:
    if not submissions_dir.exists():
        return []
    ignored = {".gitkeep", ".DS_Store"}
    items: List[Path] = []
    for item in submissions_dir.iterdir():
        if item.name in ignored or item.name.startswith("."):
            continue
        if item.is_dir() and item.name.startswith("attempt-"):
            continue
        items.append(item)
    return items


def attempt_dirs(submissions_dir: Path) -> List[Path]:
    if not submissions_dir.exists():
        return []
    return sorted([p for p in submissions_dir.glob("attempt-*") if p.is_dir()])


def attempt_has_files(attempt_dir: Path) -> bool:
    return attempt_dir.exists() and any(p.is_file() for p in attempt_dir.rglob("*"))


def next_attempt_name(submissions_dir: Path) -> str:
    attempts = attempt_dirs(submissions_dir)
    nums: List[int] = []
    for attempt in attempts:
        try:
            nums.append(int(attempt.name.split("-")[-1]))
        except ValueError:
            pass
    return f"attempt-{(max(nums) + 1 if nums else 1):03d}"


def queue_existing_attempt(cdir: Path, aid: str, attempt: str, current_day: int, message: str) -> None:
    folder = assignment_folder(cdir, aid)
    ass = load_assignment(cdir, aid)
    data = load_assignment_data(cdir, aid)
    target = folder / "submissions" / attempt
    output_dir = folder / "ai_output" / attempt

    data.setdefault("submission", {})
    data.setdefault("grading", {})
    data.setdefault("flags", {})
    data["submission"].update({
        "hasSubmission": True,
        "currentAttemptId": attempt,
        "submittedAtDay": current_day,
        "submittedAtDate": utc_now(),
        "submissionDir": target.as_posix(),
    })
    data["flags"]["isLate"] = current_day > ass.get("dueAtDay", current_day)
    data["grading"].update({
        "status": "queued",
        "queuedAtDay": current_day,
        "gradedAtDay": None,
        "aiOutputDir": output_dir.as_posix(),
        "score": None,
        "letterGrade": None,
        "gpaValue": None,
    })
    data["status"] = "submitted"
    add_event(data, current_day, "submitted", message)
    add_event(data, current_day, "grading_queued", f"Queued {attempt} for grading.")
    save_assignment_data(cdir, aid, data)
    log(cdir, f"{aid}: {message}", current_day, "submission")


def scan_uploaded_submissions(cdir: Path, aid: str, current_day: int) -> None:
    folder = assignment_folder(cdir, aid)
    submissions_dir = folder / "submissions"
    submissions_dir.mkdir(parents=True, exist_ok=True)
    data = load_assignment_data(cdir, aid)

    direct_items = submission_items(submissions_dir)
    if direct_items:
        attempt = next_attempt_name(submissions_dir)
        target = submissions_dir / attempt
        target.mkdir(parents=True, exist_ok=True)
        for item in direct_items:
            dest = target / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))
        queue_existing_attempt(cdir, aid, attempt, current_day, f"Detected GitHub upload and normalized it as {attempt}.")
        return

    attempts = [p for p in attempt_dirs(submissions_dir) if attempt_has_files(p)]
    if not attempts:
        return
    latest = attempts[-1].name
    grading_status = data.get("grading", {}).get("status")
    current_attempt = data.get("submission", {}).get("currentAttemptId")
    if current_attempt != latest or grading_status in {None, "not_graded"}:
        queue_existing_attempt(cdir, aid, latest, current_day, f"Detected existing submitted folder {latest}.")


def compute_status(assignment: Dict[str, Any], data: Dict[str, Any], current_day: int) -> str:
    if data.get("grading", {}).get("status") == "graded":
        return "graded"
    if data.get("submission", {}).get("hasSubmission"):
        return "submitted"
    if current_day < assignment.get("appearsAtDay", 1):
        return "locked"
    if current_day > assignment.get("dueAtDay", current_day):
        return "overdue"
    if assignment.get("dueAtDay", current_day) - current_day <= 2:
        return "due_soon"
    return "available"


def update_assignment_day(cdir: Path, aid: str, current_day: int) -> None:
    ass = load_assignment(cdir, aid)
    data = load_assignment_data(cdir, aid)
    data.setdefault("submission", {"hasSubmission": False})
    data.setdefault("flags", {})
    old_status = data.get("status")
    data["isVisible"] = current_day >= ass.get("appearsAtDay", 1)
    data["flags"]["isDueSoon"] = data["isVisible"] and 0 <= ass.get("dueAtDay", current_day) - current_day <= 2 and not data["submission"].get("hasSubmission")
    data["flags"]["isOverdue"] = current_day > ass.get("dueAtDay", current_day) and not data["submission"].get("hasSubmission")
    data["flags"]["isClosed"] = current_day > ass.get("dueAtDay", current_day) + ass.get("latePolicy", {}).get("maxLateDays", 0)
    data["status"] = compute_status(ass, data, current_day)
    if old_status != data["status"]:
        add_event(data, current_day, "status_changed", f"Status changed from {old_status} to {data['status']}.")
        log(cdir, f"{aid}: status changed from {old_status} to {data['status']}", current_day, "assignment")
    save_assignment_data(cdir, aid, data)


def daily_course(course_id: str, grader_mode: str | None = None, advance: bool = False) -> None:
    cdir = course_dir(course_id)
    ensure_runtime(cdir)
    st = state(cdir)
    current_day = int(st.get("currentDay", 1))
    mode = grader_mode or st.get("graderMode", "mock")
    crs = course(cdir)

    for aid in crs.get("assignments", []):
        scan_uploaded_submissions(cdir, aid, current_day)
        update_assignment_day(cdir, aid, current_day)

    for aid in crs.get("assignments", []):
        data = load_assignment_data(cdir, aid)
        if data.get("grading", {}).get("status") == "queued":
            try:
                grade = grade_assignment(cdir, aid, current_day, mode=mode)
                data = load_assignment_data(cdir, aid)
                data.setdefault("grading", {}).update({
                    "status": "graded",
                    "gradedAtDay": current_day,
                    "score": grade["finalScore"],
                    "letterGrade": grade["letterGrade"],
                    "gpaValue": grade["gpaValue"],
                })
                data["status"] = "graded"
                add_event(data, current_day, "graded", f"Graded: {grade['finalScore']}/100 ({grade['letterGrade']}).")
                save_assignment_data(cdir, aid, data)
                log(cdir, f"{aid}: graded {grade['finalScore']}/100", current_day, "grading")
            except Exception as exc:
                log(cdir, f"{aid}: grading failed: {exc}", current_day, "error")

    rebuild_gradebook(cdir)
    st["lastDailyUpdateDay"] = current_day
    if advance:
        st["currentDay"] = min(int(st.get("durationDays", crs.get("durationDays", 30))), current_day + 1)
    save_state(cdir, st)


def active_course_ids() -> List[str]:
    catalog = load_catalog()
    ids: List[str] = []
    for item in catalog.get("installedCourses", []):
        if item.get("status", "active") in {"active", "installed"}:
            cid = item.get("courseId")
            if cid and (COURSES_ROOT / cid / "course.json").exists():
                ids.append(cid)
    if not ids and (COURSES_ROOT / "webdev-30" / "course.json").exists():
        ids.append("webdev-30")
    return ids


def daily_all(grader_mode: str | None = None) -> None:
    for cid in active_course_ids():
        daily_course(cid, grader_mode=grader_mode)


def next_day(course_id: str, days: int = 1) -> None:
    cdir = course_dir(course_id)
    st = state(cdir)
    duration = int(st.get("durationDays", course(cdir).get("durationDays", 30)))
    st["currentDay"] = max(1, min(duration, int(st.get("currentDay", 1)) + days))
    save_state(cdir, st)
    log(cdir, f"Moved to day {st['currentDay']}", st["currentDay"], "time")


def submit(course_id: str, aid: str, source_dir: str | None = None) -> None:
    cdir = course_dir(course_id)
    st = state(cdir)
    current_day = int(st.get("currentDay", 1))
    folder = assignment_folder(cdir, aid)
    ass = load_assignment(cdir, aid)
    submissions_dir = folder / "submissions"
    attempt = next_attempt_name(submissions_dir)
    target = submissions_dir / attempt
    target.mkdir(parents=True, exist_ok=True)
    if source_dir:
        src = Path(source_dir)
        if not src.exists() or not src.is_dir():
            raise FileNotFoundError(source_dir)
        for item in src.iterdir():
            dest = target / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    else:
        for req in ass.get("submissionRequirements", {}).get("requiredFiles", []):
            (target / req).parent.mkdir(parents=True, exist_ok=True)
            if not (target / req).exists():
                (target / req).write_text(f"<!-- Mock submission for {aid}: {req} -->\n", encoding="utf-8")
    queue_existing_attempt(cdir, aid, attempt, current_day, f"Submitted {attempt}.")


def reset(course_id: str) -> None:
    cdir = course_dir(course_id)
    crs = course(cdir)
    runtime = course_runtime_dir(cdir)
    write_json(runtime / "course_state.json", {"courseId": course_id, "mode": "github", "currentDay": 1, "durationDays": crs.get("durationDays", 30), "lastDailyUpdateDay": 0, "graderMode": "mock", "updatedAt": utc_now()})
    write_json(runtime / "system_log.json", [])
    write_json(runtime / "gradebook.json", {"courseId": course_id, "assignments": [], "currentAverage": None, "currentLetterGrade": None, "currentGpa": None, "finalEvaluation": None, "updatedAt": utc_now()})
    if course_id == "webdev-30":
        write_json(DATA_DIR / "course_state.json", read_json(runtime / "course_state.json"))
        write_json(DATA_DIR / "system_log.json", [])
        write_json(DATA_DIR / "gradebook.json", read_json(runtime / "gradebook.json"))
    for aid in crs.get("assignments", []):
        ass = load_assignment(cdir, aid)
        data = {"assignmentId": aid, "status": "locked", "isVisible": False, "openedAtDay": ass.get("appearsAtDay", 1), "dueAtDay": ass.get("dueAtDay"), "lastUpdatedDay": 0, "submission": {"hasSubmission": False, "currentAttemptId": None, "submittedAtDay": None, "submittedAtDate": None, "submissionDir": None}, "grading": {"status": "not_graded", "queuedAtDay": None, "gradedAtDay": None, "aiOutputDir": None, "score": None, "letterGrade": None, "gpaValue": None}, "flags": {"isDueSoon": False, "isOverdue": False, "isLate": False, "isClosed": False}, "events": []}
        write_json(assignment_folder(cdir, aid) / "data.json", data)
        for d in [assignment_folder(cdir, aid) / "submissions", assignment_folder(cdir, aid) / "ai_output"]:
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
    log(cdir, "Simulation reset", 1, "system")


def status(course_id: str) -> None:
    cdir = course_dir(course_id)
    print(json.dumps({"state": state(cdir), "gradebook": read_json(runtime_path(cdir, "gradebook.json"), {})}, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Correcta scheduler")
    parser.add_argument("--course", default="webdev-30", help="Course id to process")
    parser.add_argument("--all-courses", action="store_true", help="Run daily update for every active/installed course in catalog")
    parser.add_argument("--daily", action="store_true")
    parser.add_argument("--next-day", action="store_true")
    parser.add_argument("--jump", type=int)
    parser.add_argument("--submit")
    parser.add_argument("--source-dir")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--grader", choices=["mock", "opencode"])
    args = parser.parse_args()

    if args.all_courses and args.daily:
        daily_all(args.grader)
        return

    cid = args.course
    if args.reset:
        reset(cid)
    if args.submit:
        submit(cid, args.submit, args.source_dir)
    if args.next_day:
        next_day(cid, 1)
    if args.jump:
        next_day(cid, args.jump)
    if args.daily:
        daily_course(cid, args.grader)
    if args.status:
        status(cid)


if __name__ == "__main__":
    main()
