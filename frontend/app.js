const COURSE_ROOT = "../courses/webdev-30";
const DATA_ROOT = "../data";

const $ = (id) => document.getElementById(id);

async function getJSON(path, fallback = null) {
  try {
    const res = await fetch(`${path}?v=${Date.now()}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn("Failed to load", path, err);
    return fallback;
  }
}

async function getText(path, fallback = "") {
  try {
    const res = await fetch(`${path}?v=${Date.now()}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.text();
  } catch (err) {
    console.warn("Failed to load", path, err);
    return fallback;
  }
}

function statusClass(status) {
  return String(status || "locked").toLowerCase();
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function markdownLite(md) {
  return escapeHTML(md)
    .replace(/^# (.*)$/gm, "<h2>$1</h2>")
    .replace(/^## (.*)$/gm, "<h3>$1</h3>")
    .replace(/^- (.*)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
    .replace(/\n\n/g, "<br><br>");
}

async function loadApp() {
  const course = await getJSON(`${COURSE_ROOT}/course.json`, null);
  const state = await getJSON(`${DATA_ROOT}/course_state.json`, { currentDay: 1, durationDays: 30, mode: "github" });
  const gradebook = await getJSON(`${DATA_ROOT}/gradebook.json`, { assignments: [] });
  const logs = await getJSON(`${DATA_ROOT}/system_log.json`, []);
  if (!course) {
    $("courseDescription").textContent = "Could not load course.json. If opened as file://, use GitHub Pages or a local static preview.";
    return;
  }

  $("courseDescription").textContent = course.description || course.title;
  $("dayLabel").textContent = `Day ${state.currentDay} / ${state.durationDays || course.durationDays}`;
  $("modeLabel").textContent = `Mode: ${state.mode || "github"} · Grader: ${state.graderMode || "mock"}`;
  $("averageValue").textContent = gradebook.currentAverage == null ? "--" : `${gradebook.currentAverage}%`;
  $("gpaValue").textContent = gradebook.currentGpa == null ? "GPA --" : `${gradebook.currentLetterGrade} · GPA ${gradebook.currentGpa}`;

  renderFinal(gradebook.finalEvaluation);

  const assignments = [];
  for (const aid of course.assignments) {
    const assignment = await getJSON(`${COURSE_ROOT}/assignments/${aid}/assignment.json`, null);
    const data = await getJSON(`${COURSE_ROOT}/assignments/${aid}/data.json`, null);
    if (assignment && data) assignments.push({ assignment, data });
  }
  renderAssignments(assignments);
  renderLogs(logs);
}

function renderFinal(finalEvaluation) {
  const el = $("finalEvaluation");
  if (!finalEvaluation) {
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = `
    <p class="eyebrow">Final Evaluation</p>
    <h2>${escapeHTML(finalEvaluation.letterGrade)} · ${escapeHTML(finalEvaluation.finalPercentage)}% · GPA ${escapeHTML(finalEvaluation.gpa)}</h2>
    <p class="muted">${escapeHTML(finalEvaluation.summary)}</p>
    <h3>Strengths</h3>
    <ul>${(finalEvaluation.strengths || []).map(x => `<li>${escapeHTML(x)}</li>`).join("")}</ul>
    <h3>Weaknesses</h3>
    <ul>${(finalEvaluation.weaknesses || []).map(x => `<li>${escapeHTML(x)}</li>`).join("")}</ul>
  `;
}

function renderAssignments(items) {
  const grid = $("assignmentGrid");
  grid.innerHTML = "";
  for (const item of items) {
    const { assignment, data } = item;
    const score = data.grading?.score;
    const card = document.createElement("article");
    card.className = "assignment-card";
    card.innerHTML = `
      <span class="status ${statusClass(data.status)}">${escapeHTML(data.status)}</span>
      <div>
        <h3>${escapeHTML(assignment.title)}</h3>
        <p class="muted">${escapeHTML(assignment.summary)}</p>
      </div>
      <div class="meta">
        <span>Appears <b>Day ${assignment.appearsAtDay}</b></span>
        <span>Due <b>Day ${assignment.dueAtDay}</b></span>
        <span>Submission <b>${data.submission?.currentAttemptId || "--"}</b></span>
        <span>Score <b>${score == null ? "--" : `${score}% ${data.grading.letterGrade}`}</b></span>
      </div>
      <div class="card-actions">
        <button class="ghost" data-action="detail">View Assignment</button>
        ${data.grading?.aiOutputDir ? `<button data-action="feedback">View Feedback</button>` : ""}
      </div>
    `;
    card.querySelector('[data-action="detail"]').addEventListener("click", () => showDetail(assignment, data));
    const feedbackBtn = card.querySelector('[data-action="feedback"]');
    if (feedbackBtn) feedbackBtn.addEventListener("click", () => showFeedback(assignment, data));
    grid.appendChild(card);
  }
}

function renderLogs(logs) {
  const el = $("systemLog");
  const recent = [...logs].reverse().slice(0, 80);
  if (!recent.length) {
    el.innerHTML = `<div class="log-item">No logs yet. Run the scheduler or GitHub Actions. Tiny silence goblin.</div>`;
    return;
  }
  el.innerHTML = recent.map(log => `
    <div class="log-item"><b>Day ${escapeHTML(log.day ?? "--")}</b> · ${escapeHTML(log.type)} · ${escapeHTML(log.message)}</div>
  `).join("");
}

function showDetail(assignment, data) {
  const rubricRows = assignment.rubric.map(r => `
    <tr><td>${escapeHTML(r.criterion)}</td><td>${escapeHTML(r.points)}</td><td>${escapeHTML(r.description)}</td></tr>
  `).join("");
  $("dialogBody").innerHTML = `
    <p class="eyebrow">${escapeHTML(assignment.assignmentId)}</p>
    <h2>${escapeHTML(assignment.title)}</h2>
    <p class="muted">${escapeHTML(assignment.summary)}</p>
    <h3>Instructions</h3>
    <ul>${assignment.studentInstructions.map(x => `<li>${escapeHTML(x)}</li>`).join("")}</ul>
    <h3>Required Files</h3>
    <ul>${assignment.submissionRequirements.requiredFiles.map(x => `<li>${escapeHTML(x)}</li>`).join("")}</ul>
    <h3>Rubric</h3>
    <table class="rubric-table"><thead><tr><th>Criterion</th><th>Points</th><th>Description</th></tr></thead><tbody>${rubricRows}</tbody></table>
    <h3>Runtime Data</h3>
    <pre>${escapeHTML(JSON.stringify(data, null, 2))}</pre>
  `;
  $("detailDialog").showModal();
}

async function showFeedback(assignment, data) {
  const out = data.grading.aiOutputDir.replace(/^.*courses\/webdev-30\//, `${COURSE_ROOT}/`);
  const grade = await getJSON(`${out}/grade.json`, null);
  const feedback = await getText(`${out}/feedback.md`, "No feedback.md found.");
  const notes = await getText(`${out}/notes.md`, "No notes.md found.");
  $("dialogBody").innerHTML = `
    <p class="eyebrow">AI Output</p>
    <h2>${escapeHTML(assignment.title)}</h2>
    ${grade ? `<pre>${escapeHTML(JSON.stringify(grade, null, 2))}</pre>` : ""}
    <section>${markdownLite(feedback)}</section>
    <hr>
    <section>${markdownLite(notes)}</section>
  `;
  $("detailDialog").showModal();
}

$("refreshBtn").addEventListener("click", loadApp);
$("closeDialog").addEventListener("click", () => $("detailDialog").close());
loadApp();
