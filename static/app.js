const el = (id) => document.getElementById(id);

const topicSelect = el("topic-select");
const newQuestionBtn = el("new-question-btn");
const scoreText = el("score-text");

const errorPanel = el("error-panel");
const errorMessage = el("error-message");
const errorDetails = el("error-details");

const questionPanel = el("question-panel");
const questionText = el("question-text");
const choiceButtons = document.querySelectorAll(".choice-btn");
const confidenceBadge = el("confidence-badge");
const pendingHint = el("pending-hint");

const feedbackPanel = el("feedback-panel");
const verdict = el("verdict");
const feedbackText = el("feedback-text");
const citation = el("citation");
const feedbackConfidenceBadge = el("feedback-confidence-badge");

function hide(node) {
  node.hidden = true;
}
function show(node) {
  node.hidden = false;
}

function confidenceLabel(score) {
  if (score === null || score === undefined) return "";
  let level = "high-risk";
  if (score >= 80) level = "low-risk";
  else if (score >= 50) level = "medium-risk";
  return { text: `Grounding confidence: ${score}/100`, level };
}

function setBadge(node, score) {
  const { text, level } = confidenceLabel(score);
  node.textContent = text;
  node.className = "badge " + level;
}

function showError(data, { hideQuestion = false } = {}) {
  errorMessage.textContent = data.error;
  errorDetails.innerHTML = "";
  if (Array.isArray(data.last_errors)) {
    for (const reason of data.last_errors) {
      const li = document.createElement("li");
      li.textContent = reason;
      errorDetails.appendChild(li);
    }
  }
  show(errorPanel);
  if (hideQuestion) hide(questionPanel);
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return data;
}

async function refreshScore() {
  const res = await fetch("/api/score");
  const data = await res.json();
  scoreText.textContent = data.score;
  if (data.has_active_question) {
    show(pendingHint);
  }
  return data;
}

function setChoicesEnabled(enabled) {
  choiceButtons.forEach((btn) => {
    btn.disabled = !enabled;
  });
}

async function requestNewQuestion() {
  hide(errorPanel);
  hide(feedbackPanel);
  hide(pendingHint);
  newQuestionBtn.disabled = true;

  const topic = topicSelect.value;
  const data = await apiPost("/api/new_question", { topic });

  if (data.error) {
    showError(data, { hideQuestion: true });
    newQuestionBtn.disabled = false;
    return;
  }

  questionText.textContent = data.question;
  choiceButtons.forEach((btn) => {
    const key = btn.dataset.choice;
    btn.textContent = `${key}. ${data.choices[key]}`;
  });
  setBadge(confidenceBadge, data.confidence_score);
  setChoicesEnabled(true);
  show(questionPanel);
  newQuestionBtn.disabled = false;
}

async function submitAnswer(choice) {
  setChoicesEnabled(false);
  hide(errorPanel);

  const data = await apiPost("/api/submit_answer", { choice });

  if (data.error) {
    showError(data);
    setChoicesEnabled(true);
    return;
  }

  verdict.textContent = data.correct
    ? "Correct!"
    : `Incorrect. The correct answer is ${data.correct_answer}.`;
  feedbackText.textContent = data.feedback;
  citation.textContent = `Source: ${data.citation}`;
  setBadge(feedbackConfidenceBadge, data.feedback_confidence_score);
  show(feedbackPanel);
  hide(questionPanel);
  scoreText.textContent = data.score;
}

newQuestionBtn.addEventListener("click", requestNewQuestion);
choiceButtons.forEach((btn) => {
  btn.addEventListener("click", () => submitAnswer(btn.dataset.choice));
});

refreshScore();
