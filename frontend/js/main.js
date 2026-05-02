// ============================================================
// CBT Mock AI — Homepage Logic
// ============================================================

let searchTimeout = null;
let allCourses = [];

async function init() {
  initTheme();

  // Theme toggle
  $('#theme-toggle').addEventListener('click', toggleTheme);

  // Search input with debounce
  const searchInput = $('#search-input');
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    const q = searchInput.value.trim();
    if (!q) {
      clearResults();
      return;
    }
    searchTimeout = setTimeout(() => performSearch(q), 280);
  });

  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      clearTimeout(searchTimeout);
      performSearch(searchInput.value.trim());
    }
  });

  // Quick action buttons
  $('#btn-take-exam').addEventListener('click', () => {
    searchInput.focus();
    searchInput.placeholder = 'Search a course to start your exam...';
  });

  $('#btn-summarise').addEventListener('click', () => {
    searchInput.focus();
    searchInput.placeholder = 'Search a course to view lesson summary...';
  });
}

async function performSearch(query) {
  if (!query) { clearResults(); return; }

  const resultsEl = $('#search-results');
  resultsEl.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Searching courses...</p>
    </div>
  `;
  resultsEl.classList.remove('hidden');

  try {
    const courses = await API.get(`/courses?q=${encodeURIComponent(query)}`);
    renderResults(courses, query);
  } catch (err) {
    resultsEl.innerHTML = `
      <div class="alert alert-danger">
        Unable to search courses. Please try again.
      </div>
    `;
  }
}

function renderResults(courses, query) {
  const resultsEl = $('#search-results');

  if (!courses.length) {
    resultsEl.innerHTML = `
      <div class="no-results">
        <p class="no-results-title">No content available yet</p>
        <p>No courses match "<strong>${escapeHtml(query)}</strong>". 
           Check back later or contact your administrator.</p>
      </div>
    `;
    return;
  }

  const items = courses.map(c => `
    <div class="course-result-card" data-id="${c.id}">
      <div class="course-result-info">
        <p class="course-name">${escapeHtml(c.name)}</p>
        <div class="course-meta">
          <span>${c.question_count} questions</span>
          ${c.has_summary ? '<span>Summary available</span>' : ''}
        </div>
      </div>
      <div class="course-result-actions">
        ${c.question_count >= 40 ? `
          <button class="btn btn-primary btn-sm" onclick="startExam(${c.id}, '${escapeHtml(c.name)}')">
            Take Exam
          </button>
        ` : ''}
        ${c.has_summary ? `
          <button class="btn btn-ghost btn-sm" onclick="viewSummary(${c.id}, '${escapeHtml(c.name)}')">
            Summary
          </button>
        ` : ''}
      </div>
    </div>
  `).join('');

  resultsEl.innerHTML = items;
}

function clearResults() {
  const resultsEl = $('#search-results');
  resultsEl.innerHTML = '';
  resultsEl.classList.add('hidden');
}

function startExam(courseId, courseName) {
  sessionStorage.setItem('cbt_course_id', courseId);
  sessionStorage.setItem('cbt_course_name', courseName);
  window.location.href = '../exam.html';
}

function viewSummary(courseId, courseName) {
  sessionStorage.setItem('cbt_course_id', courseId);
  sessionStorage.setItem('cbt_course_name', courseName);
  window.location.href = '../summary.html';
}

// Close results on outside click
document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-container') && !e.target.closest('.course-result-card')) {
    clearResults();
  }
});

document.addEventListener('DOMContentLoaded', init);
