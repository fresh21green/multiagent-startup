// ======================================================
// 🔐 Автоматическая проверка авторизации при загрузке
// ======================================================
document.addEventListener("DOMContentLoaded", async () => {
  const token = localStorage.getItem("token");

  // Если токена нет — перенаправляем на страницу входа
  if (!token) {
    window.location.href = "/login";
    return;
  }

  try {
    const res = await fetch("/me", {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (res.status === 401) {
      // Токен просрочен или невалиден
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
  } catch (err) {
    console.error("Ошибка проверки авторизации:", err);
    localStorage.removeItem("token");
    window.location.href = "/login";
  }
});


// === Проверка токена перед работой страницы ===
async function requireAuth() {
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.href = "/login";
    return false;
  }

  const res = await fetch("/me", {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    localStorage.removeItem("token");
    window.location.href = "/login";
    return false;
  }

  const data = await res.json();
  window.currentUser = data.user;
  console.log("✅ Авторизован:", data.user);

  // инициализация окружения
  await fetch("/init_user_workspace", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });

  return true;
}



function authHeaders() {
  const token = localStorage.getItem("token");
  return token ? { "Authorization": `Bearer ${token}` } : {};
}

window.addEventListener("DOMContentLoaded", async () => {
  const ok = await requireAuth();
  if (ok && window.currentUser) {
    const el = document.getElementById("user-info");
    if (el) el.textContent = `👋 ${window.currentUser}`;
  }
});

document.addEventListener("click", (e) => {
  if (e.target.id === "logoutBtn") {
    localStorage.removeItem("token");
    window.location.href = "/login";
  }
});
