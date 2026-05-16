from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COURSE_DIR = ROOT / "courses" / "webdev-30"
DATA_DIR = ROOT / "data"
SCALE = [(93,"A",4.0),(90,"A-",3.7),(87,"B+",3.3),(83,"B",3.0),(80,"B-",2.7),(77,"C+",2.3),(73,"C",2.0),(70,"C-",1.7),(60,"D",1.0),(0,"F",0.0)]

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def letter_for(score: float):
    for minimum, letter, gpa in SCALE:
        if score >= minimum:
            return letter, gpa
    return "F", 0.0

def rebuild_gradebook():
    course = read_json(COURSE_DIR / "course.json")
    rows = []
    for aid in course["assignments"]:
        dpath = COURSE_DIR / "assignments" / aid / "data.json"
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
                "weight": 2 if aid.startswith("FINAL") else 1,
                "aiOutputDir": grading.get("aiOutputDir"),
            })
    if rows:
        total_weight = sum(r["weight"] for r in rows)
        avg = round(sum(r["score"] * r["weight"] for r in rows) / total_weight, 2)
        letter, gpa = letter_for(avg)
    else:
        avg = letter = gpa = None
    final = None
    if len(rows) == len(course["assignments"]):
        final = {
            "finalPercentage": avg,
            "letterGrade": letter,
            "gpa": gpa,
            "summary": "Final evaluation generated from graded assignments.",
            "strengths": ["Completed the course sequence.", "Produced reviewable submissions."],
            "weaknesses": ["Review detailed assignment notes for improvement targets."],
        }
    gradebook = {
        "courseId": course["courseId"],
        "assignments": rows,
        "currentAverage": avg,
        "currentLetterGrade": letter,
        "currentGpa": gpa,
        "finalEvaluation": final,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    write_json(DATA_DIR / "gradebook.json", gradebook)
    return gradebook
