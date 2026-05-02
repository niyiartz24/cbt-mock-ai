// ============================================================
// CBT Mock AI — Admin Dashboard
// ============================================================

// ── State ─────────────────────────────────────────────────────
let courses = [];
let selectedCourseId = null;
let currentQuestions = [];
let currentSummary = null;
let activeView = 'overview';
let editingQuestionId = null;

// ── Init ──────────────────────────────────────────────────────
async function init() {
  initTheme();
  $('#theme-toggle').addEventListener('click', toggleTheme);

  // Auth check
  const token = Storage.getToken();
  if (!token) { window.location.href = 'login.html'; return; }

  try {
    await API.get('/auth/verify');
  } catch {
    Storage.removeToken();
    window.location.href = 'login.html';
    return;
  }

  // Event bindings
  $$('.sidebar-item').forEach(item => {
    item.addEventListener('click', () => {
      const view = item.dataset.view;
      if (view) switchView(view);
    });
  });

  $('#btn-logout').addEventListener('click', logout);
  $('#upload-form').addEventListener('submit', handleUpload);
  $('#upload-zone').addEventListener('click', () => $('#pdf-file-input').click());
  $('#pdf-file-input').addEventListener('change', handleFileSelect);
  setupDragDrop();

  await loadStats();
  await loadCourses();
}

// ── View switching ─────────────────────────────────────────────
function switchView(view) {
  activeView = view;
  $$('.sidebar-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === view);
  });
  $$('.admin-view').forEach(el => el.classList.add('hidden'));
  $(`#view-${view}`)?.classList.remove('hidden');

  if (view === 'questions' || view === 'summary') {
    renderCourseSelector();
  }
}

// ── Stats ─────────────────────────────────────────────────────
async function loadStats() {
  try {
    const stats = await API.get('/admin/stats');
    $('#stat-courses').textContent = stats.total_courses;
    $('#stat-published').textContent = stats.published_courses;
    $('#stat-questions').textContent = stats.total_questions;
    $('#stat-sessions').textContent = stats.total_test_sessions;
    $('#stat-avg-score').textContent = stats.average_score_percent + '%';
  } catch (e) { /* silent */ }

  try {
    const ai = await API.get('/admin/ai-provider');
    const providerEl = $('#stat-ai-provider');
    const modelEl    = $('#stat-ai-model');
    const freeEl     = $('#stat-ai-free');
    if (providerEl) providerEl.textContent = ai.provider;
    if (modelEl)    modelEl.textContent    = ai.model;
    if (freeEl && ai.free) freeEl.style.display = 'inline-flex';
  } catch (e) { /* silent */ }
}

// ── Courses ────────────────────────────────────────────────────
async function loadCourses() {
  try {
    courses = await API.get('/admin/courses');
    renderCoursesTable();
    renderCourseSelector();
  } catch (err) {
    showToast('Failed to load courses: ' + err.message, 'danger');
  }
}

function renderCoursesTable() {
  const tbody = $('#courses-tbody');
  if (!courses.length) {
    tbody.innerHTML = `
      <tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:2rem;">
        No courses yet. Upload a PDF to get started.
      </td></tr>
    `;
    return;
  }

  tbody.innerHTML = courses.map(c => `
    <tr>
      <td style="font-weight:600">${escapeHtml(c.name)}</td>
      <td>
        <span class="badge ${c.published ? 'badge-published' : 'badge-draft'}">
          ${c.published ? 'Published' : 'Draft'}
        </span>
      </td>
      <td>
        <span style="font-family:var(--font-mono)">${c.question_count}</span>
        <span style="color:var(--text-dim)">/${c.total_questions}</span>
        <span style="color:var(--text-muted); font-size:0.78rem;"> approved</span>
      </td>
      <td>${c.has_summary ? '<span style="color:var(--success)">Yes</span>' : '<span style="color:var(--text-dim)">No</span>'}</td>
      <td>
        ${!c.published && c.question_count >= 40 && c.has_summary
          ? `<button class="btn btn-success btn-sm" onclick="publishCourse(${c.id})">Publish</button>`
          : c.published
          ? `<button class="btn btn-ghost btn-sm" onclick="unpublishCourse(${c.id})">Unpublish</button>`
          : `<span class="text-muted" style="font-size:0.8rem">Not ready</span>`
        }
      </td>
      <td>
        <button class="btn btn-danger btn-sm" onclick="deleteCourse(${c.id}, '${escapeHtml(c.name)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

function renderCourseSelector() {
  const containers = $$('.course-selector-container');
  if (!courses.length) {
    containers.forEach(c => { c.innerHTML = `<p class="text-muted" style="font-size:0.875rem;">No courses available. Upload a PDF first.</p>`; });
    return;
  }

  const html = courses.map(c => `
    <button class="course-select-btn ${c.id === selectedCourseId ? 'active' : ''}"
            data-id="${c.id}" onclick="selectCourse(${c.id})">
      ${escapeHtml(c.name)}
      <span class="badge ${c.published ? 'badge-published' : 'badge-draft'}">${c.published ? 'Live' : 'Draft'}</span>
    </button>
  `).join('');

  containers.forEach(c => { c.innerHTML = html; });

  if (!selectedCourseId && courses.length > 0) {
    selectCourse(courses[0].id);
  }
}

async function selectCourse(courseId) {
  selectedCourseId = courseId;
  renderCourseSelector();

  if (activeView === 'questions') await loadQuestions(courseId);
  if (activeView === 'summary') await loadSummaryAdmin(courseId);
}

// ── Publish/Unpublish/Delete ────────────────────────────────────
async function publishCourse(courseId) {
  try {
    const result = await API.post(`/admin/courses/${courseId}/publish`);
    showToast(result.message, 'success');
    await loadCourses();
    await loadStats();
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

async function unpublishCourse(courseId) {
  if (!confirm('Unpublish this course? Students will no longer see it.')) return;
  try {
    const result = await API.post(`/admin/courses/${courseId}/unpublish`);
    showToast(result.message, 'warning');
    await loadCourses();
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

async function deleteCourse(courseId, name) {
  if (!confirm(`Delete "${name}" and all its questions/summary? This cannot be undone.`)) return;
  try {
    await API.delete(`/admin/courses/${courseId}`);
    showToast(`Course "${name}" deleted.`, 'success');
    if (selectedCourseId === courseId) selectedCourseId = null;
    await loadCourses();
    await loadStats();
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

// ── Upload ─────────────────────────────────────────────────────
function handleFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;
  updateUploadZone(file.name);
}

function updateUploadZone(filename) {
  const zone = $('#upload-zone');
  zone.querySelector('.upload-title').textContent = filename;
  zone.querySelector('.upload-hint').textContent = 'PDF selected — fill in the course name below and upload.';
}

function setupDragDrop() {
  const zone = $('#upload-zone');
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file && file.type === 'application/pdf') {
      const dt = new DataTransfer();
      dt.items.add(file);
      $('#pdf-file-input').files = dt.files;
      updateUploadZone(file.name);
    } else {
      showToast('Please drop a PDF file.', 'warning');
    }
  });
}

async function handleUpload(e) {
  e.preventDefault();
  const fileInput = $('#pdf-file-input');
  const courseName = $('#course-name-input').value.trim();

  if (!fileInput.files[0]) { showToast('Please select a PDF file.', 'warning'); return; }
  if (!courseName) { showToast('Please enter a course name.', 'warning'); return; }

  showProcessingOverlay();

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('course_name', courseName);

  try {
    const result = await API.upload('/upload-pdf', formData);
    hideProcessingOverlay();

    let msg = `Success: ${result.questions_generated} questions generated for "${result.course.name}".`;
    if (result.warning) msg += ` Warning: ${result.warning}`;
    showToast(msg, result.warning ? 'warning' : 'success', 6000);

    // Reset form
    e.target.reset();
    $('#upload-zone').querySelector('.upload-title').textContent = 'Drop your PDF here or click to browse';
    $('#upload-zone').querySelector('.upload-hint').textContent = 'Maximum file size: 20MB';

    await loadCourses();
    await loadStats();
    switchView('questions');
    await selectCourse(result.course.id);

  } catch (err) {
    hideProcessingOverlay();
    showToast(err.message || 'Upload failed. Please try again.', 'danger', 6000);
  }
}

function showProcessingOverlay() {
  let overlay = $('#processing-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'processing-overlay';
    overlay.className = 'processing-overlay';
    overlay.innerHTML = `
      <div class="spinner spinner-lg"></div>
      <p class="processing-title">Processing your PDF</p>
      <div class="processing-steps">
        <div class="processing-step active" id="step-extract">
          <div class="spinner"></div> Extracting text from PDF...
        </div>
        <div class="processing-step" id="step-questions">
          <div class="spinner" style="opacity:0.3"></div> Generating MCQ questions with AI...
        </div>
        <div class="processing-step" id="step-summary">
          <div class="spinner" style="opacity:0.3"></div> Creating lesson summary...
        </div>
        <div class="processing-step" id="step-save">
          <div class="spinner" style="opacity:0.3"></div> Saving to database...
        </div>
      </div>
      <p style="margin-top:1.5rem; color:var(--text-muted); font-size:0.8rem">
        This may take 30–60 seconds depending on PDF length.
      </p>
    `;
    document.body.appendChild(overlay);

    // Animate steps
    const delays = [2000, 8000, 18000];
    const steps = ['step-questions', 'step-summary', 'step-save'];
    steps.forEach((id, i) => {
      setTimeout(() => {
        const el = document.getElementById(id);
        if (el) el.classList.add('active');
      }, delays[i]);
    });
  }
}

function hideProcessingOverlay() {
  $('#processing-overlay')?.remove();
}

// ── Questions management ───────────────────────────────────────
async function loadQuestions(courseId) {
  const container = $('#questions-list');
  container.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Loading questions...</p></div>`;

  try {
    currentQuestions = await API.get(`/admin/courses/${courseId}/questions`);
    renderQuestions();
    updateCourseStatus(courseId);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-danger">${escapeHtml(err.message)}</div>`;
  }
}

function renderQuestions(filter = 'all') {
  const container = $('#questions-list');
  const course = courses.find(c => c.id === selectedCourseId);

  if (!currentQuestions.length) {
    container.innerHTML = `<p class="text-muted" style="text-align:center; padding:2rem;">No questions found for this course.</p>`;
    return;
  }

  let filtered = currentQuestions;
  if (filter === 'approved') filtered = currentQuestions.filter(q => q.approved);
  if (filter === 'pending')  filtered = currentQuestions.filter(q => !q.approved);

  const approvedCount = currentQuestions.filter(q => q.approved).length;

  $('#approved-count-display').textContent = `${approvedCount} / 40 approved`;

  const html = filtered.map((q, i) => {
    const options = ['A','B','C','D'].map(letter => {
      const key = `option_${letter.toLowerCase()}`;
      const isCorrect = q.correct_answer === letter;
      return `<div class="question-option-preview ${isCorrect ? 'correct' : ''}">${letter}. ${escapeHtml(q[key])}</div>`;
    }).join('');

    return `
      <div class="question-item ${q.approved ? 'approved' : ''}" data-id="${q.id}">
        <div class="question-item-header">
          <span class="question-item-num">Q${i + 1}</span>
          <p class="question-item-text">${escapeHtml(q.question)}</p>
          <div class="question-item-actions">
            <button class="btn btn-ghost btn-sm btn-icon" title="Edit" onclick="openEditModal(${q.id})">&#9998;</button>
            <button class="btn ${q.approved ? 'btn-success' : 'btn-ghost'} btn-sm" 
                    onclick="toggleApprove(${q.id})"
                    title="${q.approved ? 'Remove approval' : 'Approve this question'}">
              ${q.approved ? '&#10003; Approved' : 'Approve'}
            </button>
            <button class="btn btn-danger btn-sm btn-icon" title="Delete" onclick="deleteQuestion(${q.id})">&#10005;</button>
          </div>
        </div>
        <div class="question-options-preview">
          ${options}
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = html;
}

function updateCourseStatus(courseId) {
  const course = courses.find(c => c.id === courseId);
  if (!course) return;
  const approvedCount = currentQuestions.filter(q => q.approved).length;
  const statusEl = $('#course-status-bar');
  if (statusEl) {
    const ready = approvedCount >= 40 && course.has_summary;
    statusEl.className = `alert alert-${ready ? 'success' : approvedCount >= 40 ? 'warning' : 'warning'}`;
    statusEl.textContent = ready
      ? `This course is ready to publish (${approvedCount} approved questions, summary available).`
      : `${approvedCount}/40 questions approved. ${!course.has_summary ? 'No summary yet.' : ''}`;
  }
}

async function toggleApprove(questionId) {
  try {
    const result = await API.post(`/admin/questions/${questionId}/approve`);
    const q = currentQuestions.find(q => q.id === questionId);
    if (q) q.approved = result.approved;
    renderQuestions($('#filter-select')?.value || 'all');
    updateCourseStatus(selectedCourseId);
    await loadCourses();
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

async function approveFirst40() {
  if (!selectedCourseId) return;
  try {
    const result = await API.post(`/admin/courses/${selectedCourseId}/approve-all`);
    showToast(result.message, 'success');
    await loadQuestions(selectedCourseId);
    await loadCourses();
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

async function deleteQuestion(questionId) {
  if (!confirm('Delete this question permanently?')) return;
  try {
    await API.delete(`/admin/questions/${questionId}`);
    currentQuestions = currentQuestions.filter(q => q.id !== questionId);
    renderQuestions($('#filter-select')?.value || 'all');
    showToast('Question deleted.', 'success');
  } catch (err) {
    showToast(err.message, 'danger');
  }
}

// ── Edit modal ─────────────────────────────────────────────────
function openEditModal(questionId) {
  const q = currentQuestions.find(q => q.id === questionId);
  if (!q) return;
  editingQuestionId = questionId;

  $('#edit-question-text').value  = q.question;
  $('#edit-option-a').value       = q.option_a;
  $('#edit-option-b').value       = q.option_b;
  $('#edit-option-c').value       = q.option_c;
  $('#edit-option-d').value       = q.option_d;
  $('#edit-correct-answer').value = q.correct_answer;
  $('#edit-explanation').value    = q.explanation || '';

  $('#edit-modal').classList.remove('hidden');
}

function closeEditModal() {
  $('#edit-modal').classList.add('hidden');
  editingQuestionId = null;
}

async function saveQuestion() {
  if (!editingQuestionId) return;
  const btn = $('#btn-save-question');
  setLoading(btn, true, 'Saving...');

  const payload = {
    question:       $('#edit-question-text').value.trim(),
    option_a:       $('#edit-option-a').value.trim(),
    option_b:       $('#edit-option-b').value.trim(),
    option_c:       $('#edit-option-c').value.trim(),
    option_d:       $('#edit-option-d').value.trim(),
    correct_answer: $('#edit-correct-answer').value,
    explanation:    $('#edit-explanation').value.trim(),
  };

  try {
    const updated = await API.put(`/admin/questions/${editingQuestionId}`, payload);
    const idx = currentQuestions.findIndex(q => q.id === editingQuestionId);
    if (idx >= 0) currentQuestions[idx] = updated;
    renderQuestions($('#filter-select')?.value || 'all');
    closeEditModal();
    showToast('Question updated.', 'success');
  } catch (err) {
    showToast(err.message, 'danger');
  } finally {
    setLoading(btn, false, 'Save Changes');
  }
}

// ── Summary management ─────────────────────────────────────────
async function loadSummaryAdmin(courseId) {
  const container = $('#summary-editor-content');
  container.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Loading summary...</p></div>`;

  try {
    currentSummary = await API.get(`/admin/courses/${courseId}/summary`);
    $('#summary-textarea').value = currentSummary.content;
    $('#summary-preview').innerHTML = currentSummary.content;
    container.innerHTML = '';
    $('#summary-editor-area').classList.remove('hidden');
  } catch (err) {
    if (err.status === 404) {
      container.innerHTML = `<p class="text-muted" style="padding:2rem; text-align:center;">
        No summary generated yet. Upload a PDF to generate one.
      </p>`;
      $('#summary-editor-area').classList.add('hidden');
    } else {
      container.innerHTML = `<div class="alert alert-danger">${escapeHtml(err.message)}</div>`;
    }
  }
}

function updateSummaryPreview() {
  $('#summary-preview').innerHTML = $('#summary-textarea').value;
}

async function saveSummary() {
  if (!selectedCourseId) return;
  const btn = $('#btn-save-summary');
  setLoading(btn, true, 'Saving...');

  try {
    const updated = await API.put(`/admin/courses/${selectedCourseId}/summary`, {
      content: $('#summary-textarea').value.trim(),
    });
    currentSummary = updated;
    showToast('Summary saved.', 'success');
  } catch (err) {
    showToast(err.message, 'danger');
  } finally {
    setLoading(btn, false, 'Save Summary');
  }
}

// ── Auth ──────────────────────────────────────────────────────
function logout() {
  Storage.removeToken();
  window.location.href = 'login.html';
}

document.addEventListener('DOMContentLoaded', init);
