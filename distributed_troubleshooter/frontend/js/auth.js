const BASE_URL = "http://localhost:8000";  // Update if deployed

// ----------------------
// 🔐 LOGIN FUNCTION
// ----------------------
function login() {
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;

  fetch(`${BASE_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  })
    .then(res => res.json())
    .then(data => {
      if (data.access_token && data.user_id && data.role) {
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("role", data.role);
        localStorage.setItem("user_id", data.user_id);  // ✅ Store user_id for WebSocket
        redirectToDashboard(data.role);
      } else {
        document.getElementById("login-message").innerText = data.detail || "Login failed";
      }
    })
    .catch(() => {
      document.getElementById("login-message").innerText = "Server error. Please try again.";
    });
}

// ----------------------
// 📝 SIGNUP FUNCTION (with auto-login for expert)
// ----------------------
function signup() {
  const email = document.getElementById("signup-email").value;
  const password = document.getElementById("signup-password").value;
  const name = document.getElementById("signup-name").value;
  const role = document.getElementById("signup-role").value;
  const region = document.getElementById("region").value;

  const tagsRaw = document.getElementById("signup-tags")?.value || "";
  const expert_tags = tagsRaw.split(",").map(tag => tag.trim()).filter(tag => tag !== "");

  const bodyData = {
    email,
    password,
    name,
    role,
    region
  };

  if (role === "expert") {
    bodyData.expert_tags = expert_tags;
  }

  fetch(`${BASE_URL}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bodyData)
  })
    .then(res => res.json())
    .then(data => {
      if (data.detail) {
        // ❌ Backend returned error
        document.getElementById("signup-message").innerText = data.detail;
        return;
      }
      if (role === "expert") {
        // ✅ Immediately login expert after successful signup
        fetch(`${BASE_URL}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        })
          .then(res => res.json())
          .then(loginData => {
            if (loginData.access_token) {
              localStorage.setItem("token", loginData.access_token);
              localStorage.setItem("role", loginData.role);
              //alert("Signup complete. Redirecting to quiz...");
              window.location.href = "quiz.html";
            } else {
              document.getElementById("signup-message").innerText = loginData.detail || "Login after signup failed.";
            }
          });
      } else {
        document.getElementById("signup-message").innerText = data.message || "Signup complete. Please login.";
      }
    })
    .catch(() => {
      document.getElementById("signup-message").innerText = "Server error. Please try again.";
    });
}

// ----------------------
// 🚀 DASHBOARD REDIRECT
// ----------------------
function redirectToDashboard(role) {
  if (role === "user") {
    window.location.href = "user_dashboard.html";
  } else if (role === "expert") {
    window.location.href = "expert_dashboard.html";
  } else if (role === "admin") {
    window.location.href = "admin_dashboard.html";
  }
}

// ----------------------
// 🔁 FORM TOGGLE
// ----------------------
function showSignup() {
  document.getElementById("login-form").style.display = "none";
  document.getElementById("signup-form").style.display = "block";
  document.getElementById("form-title").innerText = "Sign Up";
}

function showLogin() {
  document.getElementById("signup-form").style.display = "none";
  document.getElementById("login-form").style.display = "block";
  document.getElementById("form-title").innerText = "Login";
}
