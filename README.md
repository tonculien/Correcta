# Correcta

Correcta is a personal, GitHub-first course simulator.

It treats a GitHub repository as a small personal LMS database:

- `courses/` stores course content, assignments, rubrics, submissions, and AI output.
- `data/` stores course state, gradebook, and system logs.
- `frontend/` displays the course as a static UI.
- `backend/` updates assignment state, grades queued submissions, and rebuilds the gradebook.
- `.github/workflows/` can run the daily update on GitHub Actions.

## Core idea

Correcta is not a multi-user LMS. It is a personal course system.

Recommended flow:

1. Keep this repo private.
2. Put your assignment submissions into the correct assignment folder.
3. Run the scheduler locally or through GitHub Actions.
4. The scheduler creates grading output in `ai_output/` and updates `data.json` / `gradebook.json`.
5. The frontend reads the files and displays results.

## Folder structure

```text
Correcta/
├── frontend/
├── backend/
├── data/
├── prompts/
├── courses/
│   └── webdev-30/
│       ├── course.json
│       └── assignments/
│           └── A01-html-profile/
│               ├── assignment.json
│               ├── data.json
│               ├── submissions/
│               └── ai_output/
└── .github/workflows/
```

Each assignment has:

- `assignment.json`: fixed assignment specification, instructions, required files, rubric.
- `data.json`: runtime state for that assignment.
- `submissions/`: submitted attempts.
- `ai_output/`: grading result files.

## Local commands

Check state:

```bash
python backend/scheduler.py --status
```

Run daily update:

```bash
python backend/scheduler.py --daily
```

Move one day forward:

```bash
python backend/scheduler.py --next-day --daily
```

Jump 7 days:

```bash
python backend/scheduler.py --jump 7 --daily
```

Submit a mock attempt:

```bash
python backend/scheduler.py --submit A01-html-profile --daily
```

Submit a real folder:

```bash
python backend/scheduler.py --submit A01-html-profile --source-dir /path/to/your/work --daily
```

Reset everything:

```bash
python backend/scheduler.py --reset
```

## GitHub Actions

The workflow `.github/workflows/correcta-daily.yml` can run the scheduler on GitHub.

By default it uses `mock` grader mode.

Manual run:

1. Go to GitHub → Actions.
2. Select `Correcta Daily Update`.
3. Click `Run workflow`.
4. Choose `mock` or `opencode`.

The workflow commits generated updates back to the repository.

## OpenCode mode

OpenCode mode is prepared but intentionally not enabled by default.

The safe design is:

- OpenCode reads `assignment.json`, `data.json`, and submitted files.
- OpenCode writes only to the assigned `ai_output/attempt-xxx/` directory.
- The scheduler validates `grade.json` and updates system data.

The workflow contains a commented OpenCode install step because the exact install command should be verified in your environment before enabling it.

## GitHub Pages

`frontend/` is static and can be hosted with GitHub Pages.

Important: the frontend does not write to the repo. It only reads JSON/Markdown files and displays them. Updates are done by GitHub Actions or local scheduler scripts.

## Privacy warning

If the repo or GitHub Pages site is public, your submissions, grades, and feedback may be visible. For personal use, a private repo is recommended.
