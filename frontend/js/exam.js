// ============================================================
// CBT Mock AI — CBT Exam Engine
// ============================================================

let questions = [];
let answers = {};       // { question_id: 'A'|'B'|'C'|'D' }
let currentIndex = 0;
let timerInterval = null;
let timeRemaining = 600; // 10 minutes in seconds
let courseData = null;
let examSubmitted = false;

async function init() {
  initTheme();
  $('#theme-toggle').addEventListener('click', toggleTheme);

  const courseId = sessionStorage.getItem('cbt_course_id');
  const courseName = sessionStorage.getItem('cbt_course_name');

  if (!courseId) {
    window.location.href = 'index.html';
    return;
  }

  $('#course-name-display').textContent = courseName || 'Loading...';
  $('#back-link').href = 'index.html';

  await loadExam(courseId);
}

async function loadExam(courseId) {
  showLoadingState();
  try {
    const data = await API.get(`/get-questions/${courseId}`);
    courseData = data.course;
    questions = data.questions;

    $('#course-name-display').textContent = courseData.name;
    buildQuestionNav();
    renderQuestion(0);
    startTimer();
    showExamState();
  } catch (err) {
    showError(err.message || 'Failed to load exam questions. Please try again.');
  }
}

function showLoadingState() {
  $('#exam-loading').classList.remove('hidden');
  $('#exam-body').classList.add('hidden');
  $('#exam-results').classList.add('hidden');
}

function showExamState() {
  $('#exam-loading').classList.add('hidden');
  $('#exam-body').classList.remove('hidden');
  $('#exam-results').classList.add('hidden');
}

function showError(message) {
  $('#exam-loading').innerHTML = `
    <div class="card" style="text-align:center; padding: 3rem;">
      <p style="color:var(--danger); margin-bottom:1rem;">${escapeHtml(message)}</p>
      <a href="index.html" class="btn btn-ghost">Return to Home</a>
    </div>
  `;
}

// ── Timer ─────────────────────────────────────────────────────
function startTimer() {
  updateTimerDisplay();
  timerInterval = setInterval(() => {
    timeRemaining--;
    updateTimerDisplay();
    if (timeRemaining <= 0) {
      clearInterval(timerInterval);
      autoSubmit();
    }
  }, 1000);
}

function updateTimerDisplay() {
  const mins = Math.floor(timeRemaining / 60).toString().padStart(2, '0');
  const secs = (timeRemaining % 60).toString().padStart(2, '0');
  const display = `${mins}:${secs}`;
  const el = $('#timer-display');
  el.textContent = display;

  el.className = 'timer-display';
  if (timeRemaining <= 60)       el.classList.add('critical');
  else if (timeRemaining <= 180) el.classList.add('warning');
}

function autoSubmit() {
  if (!examSubmitted) {
    showToast('Time is up! Submitting your exam...', 'warning', 4000);
    submitExam();
  }
}

// ── Question navigation ────────────────────────────────────────
function buildQuestionNav() {
  const nav = $('#question-grid-nav');
  nav.innerHTML = questions.map((_, i) => `
    <button class="q-nav-btn${i === 0 ? ' current' : ''}" 
            data-index="${i}" 
            onclick="goToQuestion(${i})"
            title="Question ${i + 1}">
      ${i + 1}
    </button>
  `).join('');
}

function updateQuestionNav() {
  $$('.q-nav-btn').forEach((btn, i) => {
    btn.classList.remove('current', 'answered');
    if (i === currentIndex) btn.classList.add('current');
    else if (answers[questions[i]?.id] !== undefined) btn.classList.add('answered');
  });
}

function goToQuestion(index) {
  if (index < 0 || index >= questions.length) return;
  currentIndex = index;
  renderQuestion(index);
  updateQuestionNav();
  updateProgress();
}

function renderQuestion(index) {
  const q = questions[index];
  if (!q) return;

  $('#question-number').textContent = `Question ${index + 1}`;
  $('#question-counter').textContent = `${index + 1} / ${questions.length}`;
  $('#question-text').textContent = q.question;

  const selected = answers[q.id];
  const optionLetters = ['A', 'B', 'C', 'D'];
  const optionKeys = ['option_a', 'option_b', 'option_c', 'option_d'];

  const optionsHtml = optionKeys.map((key, i) => {
    const letter = optionLetters[i];
    const isSelected = selected === letter;
    return `
      <button class="option-btn ${isSelected ? 'selected' : ''}"
              data-letter="${letter}"
              onclick="selectAnswer('${q.id}', '${letter}')"
              ${examSubmitted ? 'disabled' : ''}>
        <span class="option-letter">${letter}</span>
        <span class="option-text">${escapeHtml(q[key])}</span>
      </button>
    `;
  }).join('');

  $('#options-grid').innerHTML = optionsHtml;

  // Update nav buttons
  const prevBtn = $('#btn-prev');
  const nextBtn = $('#btn-next');
  prevBtn.disabled = index === 0;
  nextBtn.textContent = index === questions.length - 1 ? 'Finish' : 'Next';
}

function selectAnswer(questionId, letter) {
  if (examSubmitted) return;
  answers[questionId] = letter;
  renderQuestion(currentIndex);
  updateQuestionNav();
  updateProgress();
}

function updateProgress() {
  const answered = Object.keys(answers).length;
  const pct = (answered / questions.length) * 100;
  $('#progress-fill').style.width = `${pct}%`;
  $('#answered-count').textContent = `${answered}/${questions.length} answered`;
}

// ── Navigation buttons ─────────────────────────────────────────
function prevQuestion() {
  if (currentIndex > 0) goToQuestion(currentIndex - 1);
}

function nextQuestion() {
  if (currentIndex < questions.length - 1) {
    goToQuestion(currentIndex + 1);
  } else {
    confirmSubmit();
  }
}

// ── Submit ────────────────────────────────────────────────────
function confirmSubmit() {
  const answered = Object.keys(answers).length;
  const unanswered = questions.length - answered;

  if (unanswered > 0) {
    const proceed = confirm(
      `You have ${unanswered} unanswered question${unanswered > 1 ? 's' : ''}. Submit anyway?`
    );
    if (!proceed) return;
  } else {
    const proceed = confirm('Are you sure you want to submit your exam?');
    if (!proceed) return;
  }

  submitExam();
}

async function submitExam() {
  if (examSubmitted) return;
  examSubmitted = true;

  clearInterval(timerInterval);

  const submitBtn = $('#btn-submit');
  if (submitBtn) setLoading(submitBtn, true, 'Submitting...');

  // Build answers payload
  const answersPayload = {};
  questions.forEach(q => {
    if (answers[q.id] !== undefined) {
      answersPayload[q.id] = answers[q.id];
    }
  });

  try {
    const result = await API.post('/submit-test', {
      course_id: courseData.id,
      answers: answersPayload,
    });

    showResults(result);
  } catch (err) {
    examSubmitted = false;
    if (submitBtn) setLoading(submitBtn, false, 'Submit Exam');
    showToast(err.message || 'Submission failed. Please try again.', 'danger');
  }
}

// ── Results ────────────────────────────────────────────────────
function showResults(result) {
  $('#exam-body').classList.add('hidden');
  $('#exam-loading').classList.add('hidden');
  $('#exam-results').classList.remove('hidden');

  const pct = result.percentage;
  const gradeColor = pct >= 70 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)';
  const gradeText  = pct >= 70 ? 'Pass' : pct >= 50 ? 'Average' : 'Fail';
  const gradeBg    = pct >= 70 ? 'var(--success-bg)' : pct >= 50 ? 'var(--warning-bg)' : 'var(--danger-bg)';

  $('#results-header').innerHTML = `
    <div class="results-card">
      <p class="score-label">${escapeHtml(result.course_name)}</p>
      <div class="score-display" style="color:${gradeColor}">
        ${result.score}<span class="total">/${result.total}</span>
      </div>
      <span class="score-grade" style="background:${gradeBg}; color:${gradeColor}">
        ${pct}% — ${gradeText}
      </span>
      <p style="color:var(--text-muted); font-size:0.875rem; margin-top:1rem;">
        You answered ${result.score} out of ${result.total} questions correctly.
      </p>
    </div>
  `;

  // Render detailed results
  const detailsHtml = result.results.map((r, i) => {
    const isCorrect = r.is_correct;
    const choseName = r.chosen ? `Your answer: ${r.chosen} — ${escapeHtml(r[`option_${r.chosen.toLowerCase()}`] || '')}` : 'Not answered';
    const correctName = `Correct: ${r.correct_answer} — ${escapeHtml(r[`option_${r.correct_answer.toLowerCase()}`] || '')}`;

    return `
      <div class="result-item ${isCorrect ? 'correct' : 'wrong'}">
        <p style="font-size:0.72rem; color:var(--text-muted); margin-bottom:0.4rem; font-family:var(--font-mono);">
          Q${i + 1}
        </p>
        <p class="result-question">${escapeHtml(r.question)}</p>
        <div class="result-answers">
          ${r.chosen && !isCorrect ? `<span class="result-answer-tag chosen">${escapeHtml(choseName)}</span>` : ''}
          <span class="result-answer-tag correct">${escapeHtml(correctName)}</span>
        </div>
        ${r.explanation ? `<p class="result-explanation">${escapeHtml(r.explanation)}</p>` : ''}
      </div>
    `;
  }).join('');

  $('#results-detail').innerHTML = detailsHtml;
}

document.addEventListener('DOMContentLoaded', () => {
  init();

  // Button handlers
  document.addEventListener('click', (e) => {
    if (e.target.id === 'btn-prev' || e.target.closest('#btn-prev')) prevQuestion();
    if (e.target.id === 'btn-next' || e.target.closest('#btn-next')) nextQuestion();
    if (e.target.id === 'btn-submit') confirmSubmit();
    if (e.target.id === 'btn-retry') {
      sessionStorage.removeItem('cbt_course_id');
      sessionStorage.removeItem('cbt_course_name');
      window.location.href = 'index.html';
    }
  });
});
