from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
COURSE_DIR = ROOT / "courses" / "webdev-30"
SCALE = [
    (93, "A", 4.0), (90, "A-", 3.7), (87, "B+", 3.3), (83, "B", 3.0),
    (80, "B-", 2.7), (77, "C+", 2.3), (73, "C", 2.0), (70, "C-", 1.7),
    (60, "D", 1.0), (0, "F", 0.0),
]


def letter_for(score: float):
    for minimum, letter, gpa in SCALE:
        if score >= minimum:
            return letter, gpa
    return "F", 0.0


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def list_submission_files(submission_dir: Path) -> List[Path]:
    if not submission_dir.exists():
        return []
    return [p for p in submission_dir.rglob("*") if p.is_file()]


def required_missing(assignment: Dict[str, Any], submission_dir: Path) -> List[str]:
    missing = []
    for required in assignment["submissionRequirements"].get("requiredFiles", []):
        if not (submission_dir / required).exists():
            missing.append(required)
    return missing


def mock_grade(assignment: Dict[str, Any], assignment_data: Dict[str, Any], submission_dir: Path, output_dir: Path, current_day: int) -> Dict[str, Any]:
    missing = required_missing(assignment, submission_dir)
    base = 92 - (len(missing) * 18)
    # deterministic variation by assignment id, because chaos should be documented, not random
    variation = (sum(ord(c) for c in assignment["assignmentId"]) % 7) - 3
    score_before = max(0, min(100, base + variation))

    late_days = max(0, (assignment_data.get("submission", {}).get("submittedAtDay") or current_day) - assignment["dueAtDay"])
    late_policy = assignment.get("latePolicy", {})
    late_penalty = 0
    if late_days and late_policy.get("allowLate", False):
        late_penalty = min(late_days, late_policy.get("maxLateDays", late_days)) * late_policy.get("penaltyPerDay", 0)
    elif late_days:
        late_penalty = 100
    final_score = max(0, score_before - late_penalty)
    letter, gpa = letter_for(final_score)

    rubric_breakdown = []
    total_points = sum(item["points"] for item in assignment["rubric"])
    for item in assignment["rubric"]:
        proportional = item["points"] * (score_before / total_points)
        earned = round(max(0, min(item["points"], proportional)), 1)
        reason = "Mock grading: requirement appears acceptable for prototype testing."
        if missing and item is assignment["rubric"][0]:
            reason = f"Missing required files detected: {', '.join(missing)}."
        rubric_breakdown.append({
            "criterion": item["criterion"],
            "maxPoints": item["points"],
            "earnedPoints": earned,
            "reason": reason,
        })

    grade = {
        "assignmentId": assignment["assignmentId"],
        "attemptId": assignment_data["submission"].get("currentAttemptId"),
        "scoreBeforeLatePenalty": score_before,
        "latePenalty": late_penalty,
        "finalScore": final_score,
        "letterGrade": letter,
        "gpaValue": gpa,
        "gradedAtDay": current_day,
        "gradedAt": datetime.now(timezone.utc).isoformat(),
        "rubricBreakdown": rubric_breakdown,
        "missingRequiredFiles": missing,
        "summaryFeedback": f"Mock feedback for {assignment['title']}. The grading pipeline is working.",
        "deepNotes": "This is prototype output. Replace mock mode with opencode/api mode when the file workflow is stable.",
        "recommendedFixes": ["Review the rubric.", "Check required files.", "Improve clarity and consistency."],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "grade.json", grade)
    (output_dir / "feedback.md").write_text(
        f"# Feedback — {assignment['title']}\n\n"
        f"Score: {final_score}/100  \nLetter Grade: {letter}\n\n"
        f"## Summary\n\n{grade['summaryFeedback']}\n\n"
        f"## Recommended Fixes\n\n" + "\n".join(f"- {x}" for x in grade["recommendedFixes"]) + "\n",
        encoding="utf-8",
    )
    (output_dir / "notes.md").write_text(f"# Deep Notes\n\n{grade['deepNotes']}\n", encoding="utf-8")
    return grade


def build_opencode_prompt(assignment_path: Path, data_path: Path, submission_dir: Path, output_dir: Path) -> str:
    template = (ROOT / "prompts" / "grading_prompt_template.md").read_text(encoding="utf-8")
    return template.format(
        assignment_path=assignment_path.as_posix(),
        data_path=data_path.as_posix(),
        submission_dir=submission_dir.as_posix(),
        output_dir=output_dir.as_posix(),
    )


def run_opencode(assignment_path: Path, data_path: Path, submission_dir: Path, output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_opencode_prompt(assignment_path, data_path, submission_dir, output_dir)
    prompt_file = output_dir / "_prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")

    cmd = os.environ.get("CORRECTA_OPENCODE_CMD", "opencode")
    result = subprocess.run(
        [cmd, "run", prompt],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=600,
    )
    (output_dir / "_opencode_stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output_dir / "_opencode_stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"OpenCode failed: {result.stderr}")
    grade_path = output_dir / "grade.json"
    if not grade_path.exists():
        raise RuntimeError("OpenCode completed but did not create grade.json")
    return read_json(grade_path)


def grade_assignment(assignment_id: str, current_day: int, mode: str = "mock") -> Dict[str, Any]:
    folder = COURSE_DIR / "assignments" / assignment_id
    assignment_path = folder / "assignment.json"
    data_path = folder / "data.json"
    assignment = read_json(assignment_path)
    assignment_data = read_json(data_path)
    attempt = assignment_data["submission"].get("currentAttemptId")
    if not attempt:
        raise ValueError(f"{assignment_id} has no current attempt")
    submission_dir = folder / "submissions" / attempt
    output_dir = folder / "ai_output" / attempt

    if mode == "opencode":
        return run_opencode(assignment_path, data_path, submission_dir, output_dir)
    return mock_grade(assignment, assignment_data, submission_dir, output_dir, current_day)
