// ============================================================
// CBT Mock AI — Summary Page
// ============================================================

async function init() {
  initTheme();
  $('#theme-toggle').addEventListener('click', toggleTheme);

  const courseId = sessionStorage.getItem('cbt_course_id');
  const courseName = sessionStorage.getItem('cbt_course_name');

  if (!courseId) {
    window.location.href = 'index.html';
    return;
  }

  $('#course-title').textContent = courseName || 'Loading...';
  $('#back-link').href = 'index.html';

  await loadSummary(courseId);
}

async function loadSummary(courseId) {
  const contentEl = $('#summary-content-area');
  contentEl.innerHTML = `
    <div class="loading-state">
      <div class="spinner spinner-lg"></div>
      <p>Loading summary...</p>
    </div>
  `;

  try {
    const data = await API.get(`/get-summary/${courseId}`);
    const { course, summary } = data;

    $('#course-title').textContent = course.name;
    $('#summary-updated').textContent = new Date(summary.updated_at).toLocaleDateString('en-GB', {
      day: 'numeric', month: 'long', year: 'numeric'
    });

    // Sanitise and render HTML summary
    contentEl.innerHTML = sanitiseSummaryHtml(summary.content);

    // Show start exam button if course has questions
    if (course.question_count >= 40) {
      $('#btn-start-exam').classList.remove('hidden');
      $('#btn-start-exam').addEventListener('click', () => {
        sessionStorage.setItem('cbt_course_id', course.id);
        sessionStorage.setItem('cbt_course_name', course.name);
        window.location.href = 'exam.html';
      });
    }

    // Print button
    $('#btn-print').addEventListener('click', () => window.print());

  } catch (err) {
    contentEl.innerHTML = `
      <div class="alert alert-danger">
        ${escapeHtml(err.message || 'Failed to load summary. Please try again.')}
      </div>
    `;
  }
}

/**
 * Basic HTML sanitiser — allows only safe structural tags for summary content.
 */
function sanitiseSummaryHtml(html) {
  const allowedTags = ['h2', 'h3', 'h4', 'p', 'ul', 'ol', 'li', 'strong', 'em', 'b', 'i', 'div', 'span', 'br'];
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');

  function sanitiseNode(node) {
    if (node.nodeType === Node.TEXT_NODE) return node.cloneNode();
    if (node.nodeType !== Node.ELEMENT_NODE) return null;

    const tag = node.tagName.toLowerCase();
    if (!allowedTags.includes(tag)) {
      // Replace disallowed tags with a div or span
      const wrapper = document.createElement(tag === 'div' ? 'div' : 'span');
      [...node.childNodes].forEach(child => {
        const sanitised = sanitiseNode(child);
        if (sanitised) wrapper.appendChild(sanitised);
      });
      return wrapper;
    }

    const clean = document.createElement(tag);
    // Allow class attribute for summary-content div
    if (node.getAttribute('class')) {
      clean.setAttribute('class', node.getAttribute('class'));
    }

    [...node.childNodes].forEach(child => {
      const sanitised = sanitiseNode(child);
      if (sanitised) clean.appendChild(sanitised);
    });

    return clean;
  }

  const result = document.createElement('div');
  result.className = 'summary-content';
  const body = doc.body;
  [...body.childNodes].forEach(node => {
    const sanitised = sanitiseNode(node);
    if (sanitised) result.appendChild(sanitised);
  });

  return result.outerHTML;
}

document.addEventListener('DOMContentLoaded', init);
