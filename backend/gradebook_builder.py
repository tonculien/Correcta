from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple

SCALE = [(93,"A",4.0),(90,"A-",3.7),(87,"B+",3.3),(83,"B",3.0),(80,"B-",2.7),(77,"C+",2.3),(73,"C",2.0),(70,"C-",1.7),(60,"D",1.0),(0,"F",0.0)]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def letter_for(score: float) -> Tuple[str, float]:
    for minimum, letter, gpa in SCALE:
        if score >= minimum:
            return letter, gpa
    return "F", 0.0


def weight_for(assignment_id: str, course: dict) -> float:
    weights = course.get("weights") or course.get("grading", {}).get("weights") or {}
    if assignment_id in weights:
        return weights[assignment_id]
    return 2 if assignment_id.startswith("FINAL") else 1


def rebuild_gradebook(course_dir: Path) -> dict:
    course = read_json(course_dir / "course.json")
    rows = []
    for aid in course.get("assignments", []):
        dpath = course_dir / "assignments" / aid / "data.json"
        if not dpath.exists():
            continue
        data = read_json(dpath)
        grading = data.get("grading", {})
        if grading.get("status") == "graded" and grading.get("score") is not None:
            rows.append({
                "assignmentId": aid,
                "score": grading["score"],
                "letterGrade": grading["letterGrade"],
                "gpaValue": grading["gpaValue"],
                "weight": weight_for(aid, course),
                "aiOutputDir": grading.get("aiOutputDir"),
            })
    if rows:
        total_weight = sum(float(r["weight"]) for r in rows)
        avg = round(sum(float(r["score"]) * float(r["weight"]) for r in rows) / total_weight, 2)
        letter, gpa = letter_for(avg)
    else:
        avg = letter = gpa = None

    final = None
    if course.get("assignments") and len(rows) == len(course.get("assignments", [])):
        final = {
            "finalPercentage": avg,
            "letterGrade": letter,
            "gpa": gpa,
            "summary": "Final evaluation generated from graded assignments.",
            "strengths": ["Completed the course sequence.", "Produced reviewable submissions."],
            "weaknesses": ["Review detailed assignment notes for improvement targets."],
        }

    gradebook = {
        "courseId": course.get("courseId"),
        "assignments": rows,
        "currentAverage": avg,
        "currentLetterGrade": letter,
        "currentGpa": gpa,
        "finalEvaluation": final,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    runtime_path = course_dir / "runtime" / "gradebook.json"
    write_json(runtime_path, gradebook)

    # Compatibility for older single-course frontend/folders.
    root = course_dir.parents[1]
    data_dir = root / "data"
    if course.get("courseId") == "webdev-30":
        write_json(data_dir / "gradebook.json", gradebook)
    return gradebook
