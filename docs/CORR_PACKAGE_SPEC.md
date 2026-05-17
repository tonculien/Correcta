# Correcta `.corr` Course Package Spec

A `.corr` file is a ZIP archive renamed with the `.corr` extension. It contains one installable Correcta course.

## Required structure

```text
my-course.corr
├── correcta.course.json
├── grading.json
├── syllabus.md
├── knowledge/
└── assignments/
    └── A01-example/
        └── assignment.json
```

## `correcta.course.json`

```json
{
  "packageType": "correcta-course",
  "formatVersion": "1.0",
  "courseId": "minimal-30",
  "title": "Minimal 30-Day Course",
  "description": "A starter course package.",
  "durationDays": 30,
  "entry": {
    "syllabus": "syllabus.md",
    "grading": "grading.json",
    "knowledgeRoot": "knowledge",
    "assignmentRoot": "assignments"
  },
  "assignments": [
    {
      "assignmentId": "A01-example",
      "path": "assignments/A01-example/assignment.json",
      "appearsAtDay": 1,
      "dueAtDay": 5
    }
  ]
}
```

## Import behavior

Correcta creates:

```text
courses/<courseId>/
├── package/
├── runtime/
│   ├── course_state.json
│   ├── gradebook.json
│   └── system_log.json
├── course.json
└── assignments/
    └── <assignmentId>/
        ├── assignment.json
        ├── data.json
        ├── submissions/
        └── ai_output/
```

## Uninstall behavior

Uninstall does not delete the course. It archives the complete installed folder:

```text
removed_courses/<courseId>_<timestamp>/
```

The archive includes submissions, feedback, grades, logs, unfinished progress, and an `uninstall_report.json`.
