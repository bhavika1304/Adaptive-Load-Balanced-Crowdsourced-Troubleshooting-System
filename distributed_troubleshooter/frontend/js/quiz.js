const BASE_URL = "http://localhost:8000";
const token = localStorage.getItem("token");

// ----------------------
// ✅ SUBMIT QUIZ
// ----------------------
function submitQuiz() {
  const answers = {
    q1: document.querySelector('input[name="q1"]:checked')?.value,
    q2: document.querySelector('input[name="q2"]:checked')?.value,
    q3: document.querySelector('input[name="q3"]:checked')?.value
  };

  if (!answers.q1 || !answers.q2 || !answers.q3) {
    alert("Please answer all questions before submitting.");
    return;
  }

  const correctAnswers = {
    q1: "b",  // Example: Python
    q2: "a",  // Example: SQL
    q3: "c"   // Example: Cloud
  };

  let score = 0;
  Object.keys(correctAnswers).forEach(q => {
    if (answers[q] === correctAnswers[q]) score += 1;
  });

  fetch(`${BASE_URL}/submit_quiz_score`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ score })
  })
    .then(res => res.json())
    .then(data => {
      alert(data.message || "Score submitted.");
      window.location.href = "expert_dashboard.html";
    })
    .catch(() => {
      alert("Error submitting score.");
    });
}
