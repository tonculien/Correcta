#!/usr/bin/env python3
"""Build a Correcta gradebook for one course directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def score_to_letter(score: float) -> tuple[str, float]:
    scale = [
        ("A", 93, 4.0),
        ("A-", 90, 3.7),
        ("B+", 87, 3.3),
        ("B", 83, 3.0),
        ("B-", 80, 2.7),
        ("C+", 77, 2.3),
        ("C", 73, 2.0),
        ("C-", 70, 1.7),
        ("D", 60, 1.0),
        ("F", 0, 0.0),
    ]
    for letter, minimum, gpa in scale:
        if score >= minimum:
            return letter, gpa
    return "F", 0.0


def rebuild_gradebook(course_dir: Path) -> dict[str, Any]:
    course = read_json(course_dir / "course.json", {})
    grading = read_json(course_dir / "package" / "grading.json", {})
    weights = grading.get("weights", {})

    assignments = []
    total_weight = 0.0
    weighted_score = 0.0

    for aid in course.get("assignments", []):
        if isinstance(aid, dict):
            aid = aid.get("assignmentId") or aid.get("id")
        if not aid:
            continue

        data = read_json(course_dir / "assignments" / aid / "data.json", {})
        g = data.get("grading", {}) if isinstance(data, dict) else {}
        score = g.get("score")
        weight = float(weights.get(aid, 1))

        record = {
            "assignmentId": aid,
            "status": data.get("status"),
            "score": score,
            "letterGrade": g.get("letterGrade"),
            "gpaValue": g.get("gpaValue"),
            "weight": weight,
        }
        assignments.append(record)

        if score is not None:
            weighted_score += float(score) * weight
            total_weight += weight

    current_average = round(weighted_score / total_weight, 2) if total_weight else None
    current_letter, current_gpa = score_to_letter(current_average) if current_average is not None else (None, None)

    gradebook = {
        "courseId": course.get("courseId"),
        "title": course.get("title"),
        "assignments": assignments,
        "currentAverage": current_average,
        "currentLetterGrade": current_letter,
        "currentGpa": current_gpa,
    }

    runtime_dir = course_dir / "runtime"
    write_json(runtime_dir / "gradebook.json", gradebook)
    return gradebook


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("course_dir")
    args = parser.parse_args()
    print(json.dumps(rebuild_gradebook(Path(args.course_dir)), indent=2, ensure_ascii=False))
