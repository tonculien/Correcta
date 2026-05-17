const DATA_ROOT = "../data";
const CATALOG_PATH = "../courses/catalog.json";

let activeCourseId = "webdev-30";
let catalog = null;

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

function courseRoot(courseId = activeCourseId) {
  return `../courses/${courseId}`;
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

function getRepoInfo() {
  const host = window.location.hostname;
  const parts = window.location.pathname.split('/').filter(Boolean);
  let owner = 'tonculien';
  let repo = 'Correcta';
  if (host.endsWith('.github.io')) {
    owner = host.replace('.github.io', '');
    if (parts.length > 0) repo = parts[0];
  }
  return { owner, repo };
}

function getGitHubSubmitUrl(assignmentId) {
  const { owner, repo } = getRepoInfo();
  return `https://github.com/${owner}/${repo}/upload/main/courses/${activeCourseId}/assignments/${assignmentId}/submissions`;
}

function getGitHubPackageUploadUrl() {
  const { owner, repo } = getRepoInfo();
  return `https://github.com/${owner}/${repo}/upload/main/package_inbox`;
}

function getGitHubCourseManagerUrl() {
  const { owner, repo } = getRepoInfo();
  return `https://github.com/${owner}/${repo}/actions/workflows/correcta-course-manager.yml`;
}

function canSubmitAssignment(status) {
  return ['available', 'due_soon', 'overdue', 'submitted', 'graded'].includes(String(status || '').toLowerCase());
}

function submitLabel(status) {
  const s = String(status || '').toLowerCase();
  if (s === 'submitted' || s === 'graded') return 'Resubmit on GitHub';
  return 'Submit on GitHub';
}

function markdownLite(md) {
  return escapeHTML(md)
    .replace(/^# (.*)$/gm, "<h2>$1</h2>")
    .replace(/^## (.*)$/gm, "<h3>$1</h3>")
    .replace(/^- (.*)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
    .replace(/\n\n/g, "<br><br>");
}

function getCourseFromUrl() {
  return new URLSearchParams(window.location.search).get("course");
}

function setCourseInUrl(courseId) {
  const url = new URL(window.location.href);
  url.searchParams.set("course", courseId);
  window.history.replaceState({}, "", url.toString());
}

async function loadCatalog() {
  const fallback = {
    activeCourseId: "webdev-30",
    installedCourses: [
      {
        courseId: "webdev-30",
        title: "30-Day Web Development",
        path: "courses/webdev-30",
        status: "active"
      }
    ],
    removedCourses: []
  };
  catalog = await getJSON(CATALOG_PATH, fallback);
  activeCourseId = getCourseFromUrl() || catalog.activeCourseId || fallback.activeCourseId;
  renderCourseSelector();
}

function renderCourseSelector() {
  const select = $("courseSelect");
  if (!select || !catalog) return;
  const courses = catalog.installedCourses || [];
  select.innerHTML = courses.map(course => {
    const selected = course.courseId === activeCourseId ? "selected" : "";
    return `<option value="${escapeHTML(course.courseId)}" ${selected}>${escapeHTML(course.title || course.courseId)}</option>`;
  }).join("");
  select.onchange = () => {
    activeCourseId = select.value;
    setCourseInUrl(activeCourseId);
    loadApp();
  };
}

async function loadApp() {
  if (!catalog) await loadCatalog();

  const root = courseRoot(activeCourseId);
  const course = await getJSON(`${root}/course.json`, null);
  const state = await getJSON(`${root}/runtime/course_state.json`, null)
    || await getJSON(`${DATA_ROOT}/course_state.json`, { currentDay: 1, durationDays: 30, mode: "github" });
  const gradebook = await getJSON(`${root}/runtime/gradebook.json`, null)
    || await getJSON(`${DATA_ROOT}/gradebook.json`, { assignments: [] });
  const logs = await getJSON(`${root}/runtime/system_log.json`, null)
    || await getJSON(`${DATA_ROOT}/system_log.json`, []);

  if (!course) {
    $("courseDescription").textContent = `Could not load course.json for ${activeCourseId}.`;
    $("assignmentGrid").innerHTML = `<article class="assignment-card"><h3>Course not found</h3><p class="muted">Check courses/catalog.json and the course folder.</p></article>`;
    return;
  }

  $("courseDescription").textContent = course.description || course.title;
  $("dayLabel").textContent = `Day ${state.currentDay} / ${state.durationDays || course.durationDays}`;
  $("modeLabel").textContent = `Mode: ${state.mode || "github"} · Grader: ${state.graderMode || course.defaultGrader || "mock"}`;
  $("averageValue").textContent = gradebook.currentAverage == null ? "--" : `${gradebook.currentAverage}%`;
  $("gpaValue").textContent = gradebook.currentGpa == null ? "GPA --" : `${gradebook.currentLetterGrade} · GPA ${gradebook.currentGpa}`;

  renderFinal(gradebook.finalEvaluation);

  const assignments = [];
  for (const aid of course.assignments || []) {
    const assignment = await getJSON(`${root}/assignments/${aid}/assignment.json`, null);
    const data = await getJSON(`${root}/assignments/${aid}/data.json`, null);
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
  if (!items.length) {
    grid.innerHTML = `<article class="assignment-card"><h3>No assignments</h3><p class="muted">This course has no assignment folders yet.</p></article>`;
    return;
  }

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
  const recent = [...(logs || [])].reverse().slice(0, 80);
  if (!recent.length) {
    el.innerHTML = `<div class="log-item">No logs yet. Run GitHub Actions. Tiny silence goblin.</div>`;
    return;
  }
  el.innerHTML = recent.map(log => `
    <div class="log-item"><b>Day ${escapeHTML(log.day ?? "--")}</b> · ${escapeHTML(log.type)} · ${escapeHTML(log.message)}</div>
  `).join("");
}

function showDetail(assignment, data) {
  const rubricRows = (assignment.rubric || []).map(r => `
    <tr><td>${escapeHTML(r.criterion)}</td><td>${escapeHTML(r.points)}</td><td>${escapeHTML(r.description)}</td></tr>
  `).join("");
  const submitUrl = getGitHubSubmitUrl(assignment.assignmentId);
  const submitBlock = canSubmitAssignment(data.status) ? `
    <div class="submit-panel">
      <div>
        <p class="eyebrow">Submission</p>
        <h3>${escapeHTML(submitLabel(data.status))}</h3>
        <p class="muted">This opens the exact GitHub upload folder for this assignment. After uploading, wait for Actions to finish, then press Refresh here.</p>
      </div>
      <a class="button submit-button" target="_blank" rel="noopener" href="${escapeHTML(submitUrl)}" id="submitLink">${escapeHTML(submitLabel(data.status))}</a>
    </div>
    <div class="notice soft">If you already uploaded your submission on GitHub, come back here and press Refresh after Actions finishes grading.</div>
  ` : "";
  $("dialogBody").innerHTML = `
    <p class="eyebrow">${escapeHTML(assignment.assignmentId)}</p>
    <h2>${escapeHTML(assignment.title)}</h2>
    <p class="muted">${escapeHTML(assignment.summary)}</p>
    ${submitBlock}
    <h3>Instructions</h3>
    <ul>${(assignment.studentInstructions || []).map(x => `<li>${escapeHTML(x)}</li>`).join("")}</ul>
    <h3>Required Files</h3>
    <ul>${(assignment.submissionRequirements?.requiredFiles || []).map(x => `<li>${escapeHTML(x)}</li>`).join("")}</ul>
    <h3>Rubric</h3>
    <table class="rubric-table"><thead><tr><th>Criterion</th><th>Points</th><th>Description</th></tr></thead><tbody>${rubricRows}</tbody></table>
    <h3>Runtime Data</h3>
    <pre>${escapeHTML(JSON.stringify(data, null, 2))}</pre>
  `;
  $("detailDialog").showModal();
}

async function showFeedback(assignment, data) {
  let out = data.grading.aiOutputDir || "";
  out = out.replace(/^.*courses\//, "../courses/");
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

function showNotice(html) {
  const el = $("courseManagerNotice");
  el.classList.remove("hidden");
  el.innerHTML = html;
}

function setupCourseManagerButtons() {
  $("importCourseBtn")?.addEventListener("click", () => {
    const uploadUrl = getGitHubPackageUploadUrl();
    const actionsUrl = getGitHubCourseManagerUrl();
    showNotice(`
      <b>Import flow:</b>
      <ol>
        <li>Upload your <code>.corr</code> file into <code>package_inbox/</code>.</li>
        <li>Open <b>Correcta Course Manager</b> in GitHub Actions.</li>
        <li>Run workflow with <code>operation=import</code> and <code>package_path=package_inbox/YOUR_FILE.corr</code>.</li>
      </ol>
      <div class="notice-actions">
        <a class="button" target="_blank" rel="noopener" href="${escapeHTML(uploadUrl)}">Upload .corr</a>
        <a class="button ghost" target="_blank" rel="noopener" href="${escapeHTML(actionsUrl)}">Open Course Manager</a>
      </div>
    `);
  });

  $("uninstallCourseBtn")?.addEventListener("click", () => {
    const actionsUrl = getGitHubCourseManagerUrl();
    showNotice(`
      <b>Uninstall flow:</b>
      <ol>
        <li>Open <b>Correcta Course Manager</b> in GitHub Actions.</li>
        <li>Run workflow with <code>operation=uninstall</code>.</li>
        <li>Use <code>course_id=${escapeHTML(activeCourseId)}</code>.</li>
      </ol>
      <p class="muted">Uninstall archives the full course folder into <code>removed_courses/</code>, including submissions, feedback, grades, and unfinished progress.</p>
      <div class="notice-actions">
        <a class="button danger" target="_blank" rel="noopener" href="${escapeHTML(actionsUrl)}">Open Course Manager</a>
      </div>
    `);
  });
}

$("refreshBtn")?.addEventListener("click", loadApp);
$("closeDialog")?.addEventListener("click", () => $("detailDialog").close());
setupCourseManagerButtons();
loadApp();
