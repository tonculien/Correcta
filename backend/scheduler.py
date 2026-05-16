from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from grader_runner import grade_assignment
from gradebook_builder import rebuild_gradebook

ROOT = Path(__file__).resolve().parents[1]
COURSE_DIR = ROOT / "courses" / "webdev-30"
DATA_DIR = ROOT / "data"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str, day: int | None = None, event_type: str = "system") -> None:
    path = DATA_DIR / "system_log.json"
    logs = read_json(path) if path.exists() else []
    logs.append({"day": day, "type": event_type, "message": message, "at": utc_now()})
    write_json(path, logs[-300:])


def state() -> Dict[str, Any]:
    return read_json(DATA_DIR / "course_state.json")


def save_state(data: Dict[str, Any]) -> None:
    data["updatedAt"] = utc_now()
    write_json(DATA_DIR / "course_state.json", data)


def course() -> Dict[str, Any]:
    return read_json(COURSE_DIR / "course.json")


def assignment_folder(aid: str) -> Path:
    return COURSE_DIR / "assignments" / aid


def load_assignment(aid: str) -> Dict[str, Any]:
    return read_json(assignment_folder(aid) / "assignment.json")


def load_assignment_data(aid: str) -> Dict[str, Any]:
    return read_json(assignment_folder(aid) / "data.json")


def save_assignment_data(aid: str, data: Dict[str, Any]) -> None:
    data["lastUpdatedDay"] = state()["currentDay"]
    write_json(assignment_folder(aid) / "data.json", data)


def add_event(data: Dict[str, Any], day: int, event_type: str, message: str) -> None:
    data.setdefault("events", []).append({"day": day, "type": event_type, "message": message, "at": utc_now()})




def submission_items(submissions_dir: Path) -> List[Path]:
    """Return user-uploaded items directly inside submissions/.

    GitHub upload sends files straight into the selected folder. For Correcta,
    that means a user may upload index.html directly to submissions/ instead
    of creating submissions/attempt-001/index.html. This helper finds those
    direct uploads and ignores attempt folders / hidden placeholder files.
    """
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
    if not attempts:
        return "attempt-001"
    nums: List[int] = []
    for attempt in attempts:
        try:
            nums.append(int(attempt.name.split("-")[-1]))
        except ValueError:
            pass
    return f"attempt-{(max(nums) + 1 if nums else 1):03d}"


def queue_existing_attempt(aid: str, attempt: str, current_day: int, message: str) -> None:
    folder = assignment_folder(aid)
    ass = load_assignment(aid)
    data = load_assignment_data(aid)
    target = folder / "submissions" / attempt
    output_dir = folder / "ai_output" / attempt

    data["submission"].update({
        "hasSubmission": True,
        "currentAttemptId": attempt,
        "submittedAtDay": current_day,
        "submittedAtDate": utc_now(),
        "submissionDir": target.as_posix(),
    })
    data["flags"]["isLate"] = current_day > ass["dueAtDay"]
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
    save_assignment_data(aid, data)
    log(f"{aid}: {message}", current_day, "submission")


def scan_uploaded_submissions(aid: str, current_day: int) -> None:
    """Detect GitHub-uploaded submissions and queue them for grading.

    Supports two user-friendly patterns:
    1. Upload files directly into submissions/.
       The scheduler normalizes them into submissions/attempt-XXX/.
    2. Upload an attempt folder manually, e.g. submissions/attempt-001/.
       The scheduler queues the latest attempt if data.json has not recorded it.
    """
    folder = assignment_folder(aid)
    submissions_dir = folder / "submissions"
    submissions_dir.mkdir(parents=True, exist_ok=True)
    data = load_assignment_data(aid)

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
        queue_existing_attempt(aid, attempt, current_day, f"Detected GitHub upload and normalized it as {attempt}.")
        return

    attempts = [p for p in attempt_dirs(submissions_dir) if attempt_has_files(p)]
    if not attempts:
        return
    latest = attempts[-1].name
    grading_status = data.get("grading", {}).get("status")
    current_attempt = data.get("submission", {}).get("currentAttemptId")
    if current_attempt != latest or grading_status in {None, "not_graded"}:
        queue_existing_attempt(aid, latest, current_day, f"Detected existing submitted folder {latest}.")

def compute_status(assignment: Dict[str, Any], data: Dict[str, Any], current_day: int) -> str:
    if data.get("grading", {}).get("status") == "graded":
        return "graded"
    if data.get("submission", {}).get("hasSubmission"):
        return "submitted"
    if current_day < assignment["appearsAtDay"]:
        return "locked"
    if current_day > assignment["dueAtDay"]:
        return "overdue"
    if assignment["dueAtDay"] - current_day <= 2:
        return "due_soon"
    return "available"


def update_assignment_day(aid: str, current_day: int) -> None:
    ass = load_assignment(aid)
    data = load_assignment_data(aid)
    old_status = data.get("status")
    data["isVisible"] = current_day >= ass["appearsAtDay"]
    data["flags"]["isDueSoon"] = data["isVisible"] and 0 <= ass["dueAtDay"] - current_day <= 2 and not data["submission"]["hasSubmission"]
    data["flags"]["isOverdue"] = current_day > ass["dueAtDay"] and not data["submission"]["hasSubmission"]
    data["flags"]["isClosed"] = current_day > ass["dueAtDay"] + ass.get("latePolicy", {}).get("maxLateDays", 0)
    data["status"] = compute_status(ass, data, current_day)
    if old_status != data["status"]:
        add_event(data, current_day, "status_changed", f"Status changed from {old_status} to {data['status']}.")
        log(f"{aid}: status changed from {old_status} to {data['status']}", current_day, "assignment")
    save_assignment_data(aid, data)


def daily(grader_mode: str | None = None) -> None:
    st = state()
    current_day = st["currentDay"]
    mode = grader_mode or st.get("graderMode", "mock")
    for aid in course()["assignments"]:
        scan_uploaded_submissions(aid, current_day)
        update_assignment_day(aid, current_day)
    for aid in course()["assignments"]:
        data = load_assignment_data(aid)
        if data.get("grading", {}).get("status") == "queued":
            try:
                grade = grade_assignment(aid, current_day, mode=mode)
                data = load_assignment_data(aid)
                data["grading"].update({
                    "status": "graded",
                    "gradedAtDay": current_day,
                    "score": grade["finalScore"],
                    "letterGrade": grade["letterGrade"],
                    "gpaValue": grade["gpaValue"],
                })
                data["status"] = "graded"
                add_event(data, current_day, "graded", f"Graded: {grade['finalScore']}/100 ({grade['letterGrade']}).")
                save_assignment_data(aid, data)
                log(f"{aid}: graded {grade['finalScore']}/100", current_day, "grading")
            except Exception as exc:
                log(f"{aid}: grading failed: {exc}", current_day, "error")
    rebuild_gradebook()
    st["lastDailyUpdateDay"] = current_day
    save_state(st)


def next_day(days: int = 1) -> None:
    st = state()
    st["currentDay"] = max(1, min(st["durationDays"], st["currentDay"] + days))
    save_state(st)
    log(f"Moved to day {st['currentDay']}", st["currentDay"], "time")


def submit(aid: str, source_dir: str | None = None) -> None:
    st = state()
    current_day = st["currentDay"]
    folder = assignment_folder(aid)
    ass = load_assignment(aid)
    data = load_assignment_data(aid)
    attempt_no = 1
    submissions_dir = folder / "submissions"
    existing = sorted([p.name for p in submissions_dir.glob("attempt-*") if p.is_dir()])
    if existing:
        attempt_no = int(existing[-1].split("-")[-1]) + 1
    attempt = f"attempt-{attempt_no:03d}"
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
        # create placeholder files so prototype grading can run
        for req in ass["submissionRequirements"].get("requiredFiles", []):
            (target / req).parent.mkdir(parents=True, exist_ok=True)
            if not (target / req).exists():
                (target / req).write_text(f"<!-- Mock submission for {aid}: {req} -->\n", encoding="utf-8")
    output_dir = folder / "ai_output" / attempt
    data["submission"].update({
        "hasSubmission": True,
        "currentAttemptId": attempt,
        "submittedAtDay": current_day,
        "submittedAtDate": utc_now(),
        "submissionDir": target.as_posix(),
    })
    late = current_day > ass["dueAtDay"]
    data["flags"]["isLate"] = late
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
    add_event(data, current_day, "submitted", f"Submitted {attempt}.")
    add_event(data, current_day, "grading_queued", f"Queued {attempt} for grading.")
    save_assignment_data(aid, data)
    log(f"{aid}: submitted {attempt}", current_day, "submission")


def reset() -> None:
    write_json(DATA_DIR / "course_state.json", {"courseId":"webdev-30","mode":"github","currentDay":1,"durationDays":30,"lastDailyUpdateDay":0,"graderMode":"mock","updatedAt":utc_now()})
    write_json(DATA_DIR / "system_log.json", [])
    write_json(DATA_DIR / "gradebook.json", {"courseId":"webdev-30","assignments":[],"currentAverage":None,"currentLetterGrade":None,"currentGpa":None,"finalEvaluation":None,"updatedAt":utc_now()})
    for aid in course()["assignments"]:
        ass = load_assignment(aid)
        data = {"assignmentId":aid,"status":"locked","isVisible":False,"openedAtDay":ass["appearsAtDay"],"dueAtDay":ass["dueAtDay"],"lastUpdatedDay":0,"submission":{"hasSubmission":False,"currentAttemptId":None,"submittedAtDay":None,"submittedAtDate":None,"submissionDir":None},"grading":{"status":"not_graded","queuedAtDay":None,"gradedAtDay":None,"aiOutputDir":None,"score":None,"letterGrade":None,"gpaValue":None},"flags":{"isDueSoon":False,"isOverdue":False,"isLate":False,"isClosed":False},"events":[]}
        write_json(assignment_folder(aid)/"data.json", data)
        for d in [assignment_folder(aid)/"submissions", assignment_folder(aid)/"ai_output"]:
            shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    log("Simulation reset", 1, "system")


def status() -> None:
    print(json.dumps({"state": state(), "gradebook": read_json(DATA_DIR / "gradebook.json")}, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Correcta scheduler")
    parser.add_argument("--daily", action="store_true")
    parser.add_argument("--next-day", action="store_true")
    parser.add_argument("--jump", type=int)
    parser.add_argument("--submit")
    parser.add_argument("--source-dir")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--grader", choices=["mock", "opencode"])
    args = parser.parse_args()
    if args.reset:
        reset()
    if args.submit:
        submit(args.submit, args.source_dir)
    if args.next_day:
        next_day(1)
    if args.jump:
        next_day(args.jump)
    if args.daily:
        daily(args.grader)
    if args.status:
        status()

if __name__ == "__main__":
    main()
