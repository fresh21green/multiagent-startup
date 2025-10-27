// ========================================================================
// 🧩 CORE MODULE — управление каталогами и сотрудниками
// ========================================================================

const AIManager = (() => {
  const qs  = s => document.querySelector(s);
  const qsa = s => document.querySelectorAll(s);

  // --- 🧠 Универсальный вывод сообщений ---
  const showMessage = (text, type = "info") => {
    const msgBox = qs("#folderMessage");
    if (!msgBox) return;
    msgBox.textContent = text;
    msgBox.className = type;
    setTimeout(() => (msgBox.textContent = ""), 1500);
  };

  // === API wrapper ===
  async function api(url, options = {}) {
    try {
      const res = await fetch(url, options);
      const text = await res.text();
      if (!res.ok) throw new Error(`${res.status}: ${text.slice(0,100)}`);
      try {
        return JSON.parse(text);
      } catch {
        return text;
      }
    } catch (err) {
      console.error("API error:", err);
      setSystemStatus("error", err.message);
      throw err;
    }
  }

  // --- 📁 Создание каталога ---
  const handleCreateFolder = async e => {
    e.preventDefault();
    const input = qs("#folderName");
    const name = input.value.trim();
    if (!name) return showMessage("❗Введите имя каталога", "warn");

    const res = await fetch("/create_folder", {
      method: "POST",
      body: new URLSearchParams({ name }),
      headers: { ...authHeaders(), Accept: "application/json" }
    });
    const data = await res.json();

    if (data.ok) {
      showMessage(`✅ Каталог '${name}' создан`);
      renderFolder(name);
      addFolderToSelect(name);
      input.value = "";
    } else if (data.error === "exists") {
      showMessage("⚠️ Такой каталог уже существует", "warn");
    } else {
      showMessage("❌ Ошибка при создании каталога", "error");
    }
  };

  // --- 📄 Добавление каталога в селект ---
  const addFolderToSelect = (name) => {
    const select = qs("#folder-select");
    if (!select) return;
    if ([...select.options].some(o => o.value === name)) return;
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  };

  // --- 🎨 Отрисовка каталога на странице ---
  const renderFolder = (name) => {
    const container = qs("#folders-container");
    if (!container || qs(`#folder-${name}`)) return;

    const html = `
      <section id="folder-${name}" class="folder" data-folder="${name}">
        <div class="folder-header">
          <h2 class="folder-title" onclick="AIManager.toggleFolder('${name}')">📂 ${name}</h2>
          <i data-lucide="rocket"></i> 
          <div class="folder-actions">
            <button class="delete-folder-btn" onclick="AIManager.deleteFolder('${name}')">
              <i data-lucide="trash-2"></i> Удалить
            </button>
          </div>
        </div>
        <div class="task-box hidden" id="task-box-${name}">
          <textarea placeholder="Введите задачу для всех сотрудников каталога '${name}'..." id="task-input-${name}"></textarea>
          <button onclick="AIManager.assignTaskToFolder('${name}')">Отправить</button>
        </div>
        <ul class="agents-list" id="agents-${name}" style="display:none;">
          <li><em>Пока пусто</em></li>
        </ul>
      </section>`;
    container.insertAdjacentHTML("afterbegin", html);
  };

  window.toggleTaskBox = (folder) => {
    const box = document.querySelector(`#task-box-${folder}`);
    if (box) box.classList.toggle("hidden");
  };

  // === Удаление каталога ===
// === Удаление каталога ===
  async function deleteFolder(folderName) {
     const row = document.querySelector(`.folder[data-folder="${folderName}"]`);
  if (!row) {
    console.warn(`⚠️ Агент ${folderName} не найден в DOM`);
    return;
  }

  // если подтверждение уже открыто — не дублируем
  if (row.querySelector(".confirm-delete")) return;

  // создаём встроенный confirm-блок
  const confirmBox = document.createElement("div");
  confirmBox.className = "confirm-delete";
  confirmBox.innerHTML = `
    <span style="margin-right:8px;">Удалить?</span>
    <button class="yes">Да</button>
    <button class="no">Отмена</button>
  `;
  confirmBox.style.display = "inline-flex";
  confirmBox.style.gap = "6px";
  confirmBox.style.marginLeft = "10px";
  confirmBox.style.alignItems = "center";

  row.appendChild(confirmBox);

  confirmBox.querySelector(".yes").onclick = async () => {
    try {
      const res = await fetch("/delete_folder", {
        method: "POST",
        headers: { ...authHeaders(), Accept: "application/json" },
        body: new URLSearchParams({ name: folderName })
      });

      const data = await res.json();

      if (data.ok) {
        showMessage(`🗑️ Каталог '${folderName}' удалён`);
        document.querySelector(`#folder-${folderName}`)?.remove();
        setSystemStatus("active", `🧹 Каталог '${folderName}' успешно удалён`);
      } 
      else if (data.error === "not_empty") {
        // ✅ человекопонятное уведомление
        showMessage(`⚠️ Каталог '${folderName}' не может быть удалён — он не пуст.`, "warn");
        setSystemStatus("error", `❗ Каталог '${folderName}' содержит сотрудников`);
      }
      else {
        showMessage(`❌ Ошибка при удалении каталога: ${data.error || "неизвестно"}`, "error");
        setSystemStatus("error", `Ошибка: ${data.error || res.statusText}`);
      }
    } 
    catch (err) {
      console.error("Ошибка удаления:", err);
      showMessage("❌ Ошибка при удалении каталога", "error");
      setSystemStatus("error", "Ошибка при удалении каталога");
    }
  };


  confirmBox.querySelector(".no").onclick = () => confirmBox.remove();
  }



  

  // --- 🤖 Создание сотрудника ---
  const handleCreateAgent = async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    try {
      const res = await fetch("/create_agent", { method: "POST", body: formData , headers: { ...authHeaders(), Accept: "application/json" }});
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Ошибка создания");

      const folder = formData.get("folder") || "root";
      const name   = formData.get("name");
      const slug   = name.toLowerCase().replace(/[^a-z0-9_-]/g, "_");
      addAgentToFolder(folder, name, slug);
      showMessage(`✅ Сотрудник '${name}' создан`);
      form.reset();
    } catch (err) {
      showMessage(`❌ ${err.message}`, "error");
    }
  };

  const addAgentToFolder = (folder, name, slug) => {
    const section = document.querySelector(`#folder-${folder} ul`);
    if (!section) return;
    section.insertAdjacentHTML("beforeend", `
      <li>
        🤖 <a href="/agent/${slug}" target="_blank">${name}</a>
        <button class="icon-btn delete-agent-btn" onclick="AIManager.deleteAgent('${slug}', '${folder}')">
          <i data-lucide="trash-2"></i>
        </button>
      </li>`);
    if (window.lucide) lucide.createIcons();
  };

  // --- 🗑 Удаление сотрудника (без alert) ---
 // --- 🗑 Удаление сотрудника (с подтверждением без alert) ---
const deleteAgent = async (slug) => {
  const row = document.querySelector(`.agent-row[data-slug="${slug}"]`);
  if (!row) {
    console.warn(`⚠️ Агент ${slug} не найден`);
    return;
  }

  // предотвращаем дубли подтверждений
  if (row.querySelector(".confirm-delete")) return;

  // создаём мини confirm прямо рядом с кнопкой
  const confirmBox = document.createElement("div");
  confirmBox.className = "confirm-delete";
  confirmBox.innerHTML = `
    <span>Удалить?</span>
    <button class="yes">Да</button>
    <button class="no">Отмена</button>
  `;
  confirmBox.style.display = "inline-flex";
  confirmBox.style.gap = "5px";
  confirmBox.style.marginLeft = "10px";
  row.appendChild(confirmBox);

  // === Обработчики ===
  confirmBox.querySelector(".yes").onclick = async () => {
    try {
      const res = await fetch("/delete_agent", {
        method: "POST",
        headers: { ...authHeaders(), Accept: "application/json" },
        body: new URLSearchParams({ slug })
      });
      const data = await res.json();

      if (res.ok && data.ok) {
        row.style.transition = "opacity 0.3s ease, transform 0.3s ease";
        row.style.opacity = "0";
        row.style.transform = "translateX(-15px)";
        setTimeout(() => row.remove(), 300);
        if (typeof showMessage === "function") showMessage(`🗑️ Удалён '${slug}'`);
        setSystemStatus("active", `🧹 Сотрудник '${slug}' удалён`);
      } else {
        console.error(data.error || data.detail);
        showMessage(`❌ ${data.error || "Ошибка удаления"}`, "error");
      }
    } catch (err) {
      console.error("Ошибка удаления:", err);
      showMessage("❌ Ошибка при удалении сотрудника", "error");
    }
  };

  confirmBox.querySelector(".no").onclick = () => confirmBox.remove();
};

 // ===============================
  // 5. Поручить задачу агенту
  // ===============================
const assignTask = async (slug) => {
    const input = document.getElementById(`task-${slug}`);
    const task = input?.value.trim();
    if (!task) return alert("Введите задачу");

    const card = document.querySelector(`#agent-card-${slug}`);
    const status = card.querySelector(".agent-status");
    const resultBox = card.querySelector(".result");
    const button = card.querySelector("button");

    // Обновляем UI перед запросом
    setSystemStatus("busy", "⚙️ Выполняется задача...");
    button.disabled = true;
    status.textContent = "Статус: ⚙️ Выполняется...";
    status.className = "agent-status running";
    resultBox.innerHTML = `<div class="spinner"></div> Выполняется...`;

    try {
      const res = await fetch("/assign_task", {
        method: "POST",
        body: new URLSearchParams({ slug, task }),
        headers: { ...authHeaders(), Accept: "application/json" }
      });
      const data = await res.json();

      if (!data.ok) throw new Error(data.error || "Ошибка выполнения");

      // 🟢 Успешное выполнение
      status.textContent = "Статус: ✅ Готово";
      status.className = "agent-status done";
      resultBox.innerHTML = data.result?.html || data.result || "—";
      taskBox.textContent = `🧩 Последняя задача: ${task}`;
      resultBox.style.display = "block";

      // Визуальный отклик
      card.classList.add("done");
      setTimeout(() => card.classList.remove("done"), 1500);
      setSystemStatus("active", "🧠 Все агенты активны");
    } catch (err) {
      console.error(err);
      status.textContent = "Статус: ❌ Ошибка";
      status.className = "agent-status error";
      resultBox.textContent = err.message || "Ошибка выполнения задачи";
      setSystemStatus("error", "❌ Ошибка при выполнении задачи");
    } finally {
      button.disabled = false;
    }
  }



// 6. Поручить задачу всему каталогу (с анимацией)
// ===============================
// === 🧩 Поручить задачу всему каталогу ===
async function assignTaskToFolder(folder, taskText) {
  const input = document.getElementById(`task-input-${folder}`);
  const task = taskText || input?.value?.trim();
  if (!task) return alert("Введите задачу для каталога");

  // 🧩 Ищем кнопку "Отправить", если она есть
  const button = input?.nextElementSibling || document.querySelector(`#folder-${folder} .assign-btn`);
  const originalText = button ? button.textContent : null;

  if (button) {
    button.disabled = true;
    button.textContent = "⚙️ Выполняется...";
  }

  setSystemStatus("active", `🧩 Каталог '${folder}' выполняет задачу`);

  try {
    const res = await fetch("/assign_task_to_folder", {
      method: "POST",
      headers: { ...authHeaders(), Accept: "application/json" },
      body: new URLSearchParams({ folder, task })
    });
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      showMessage(`❌ Ошибка: ${data.error || "неизвестно"}`, "error");
      setSystemStatus("error", "Ошибка при назначении задачи каталогу");
      return;
    }
    else{
      // 🧠 Успешное завершение задачи всеми сотрудниками
      setSystemStatus("active", `✅ Задача выполнена сотрудниками каталога "${folder}"`);
  
      addShowResultButton(folder,data);

      setTimeout(() => {
        setSystemStatus("active", "🧩 Все агенты активны");
      }, 2000);
    }


  } catch (err) {
    console.error("Ошибка assignTaskToFolder:", err);
    showMessage("❌ Ошибка при назначении задачи каталогу", "error");
    setSystemStatus("error", "Ошибка при назначении задачи каталогу");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText || "Отправить";
    }
  }
}

async function addShowResultButton(folder,data) {
  console.log('addShowResultButton')
  // === Отображаем результат под task-box ===
    const box = document.getElementById(`task-box-${folder}`);
    if (box) {
      // удаляем старое сообщение, если уже было
      const oldResult = box.querySelector(".task-result-block");
      if (oldResult) oldResult.remove();

      // создаём новый блок
      const resultBlock = document.createElement("div");
      resultBlock.className = "task-result-block";
      resultBlock.innerHTML = `
        <span class="task-done-text">✅ Задача выполнена</span>
        <button class="btn-mini show-results-btn">Посмотреть результат</button>
      `;
      resultBlock.style.marginTop = "8px";
      resultBlock.style.display = "flex";
      resultBlock.style.alignItems = "center";
      resultBlock.style.gap = "8px";

      // сохраняем результаты в элемент
      resultBlock.dataset.results = JSON.stringify(data.results);

      // обработчик открытия модалки
      resultBlock.querySelector(".show-results-btn").onclick = () => showResultsModal(data.results);

      box.appendChild(resultBlock);
    }
  }

function showResultsModal(results) {
  const modal = document.getElementById("results-modal");
  const content = document.getElementById("results-content");
  const closeBtn = document.getElementById("close-results-modal");
  if (!modal || !content) return;

  content.innerHTML = results.map(r => {
    const name = r.agent || "Неизвестный агент";
    const raw = r.result?.html || r.result?.markdown || r.result || r.error || "—";
    const safeText = typeof raw === "string" ? raw.trim() : JSON.stringify(raw, null, 2);
    const rendered = safeText.startsWith("<")
      ? safeText
      : marked.parse(safeText); // Markdown → HTML при необходимости
    return `
      <div class="result-agent-block">
        <h4>🤖 ${name}</h4>
        <div class="markdown-body">${rendered}</div>
      </div>
    `;
  }).join("");


  modal.style.display = "flex";
  closeBtn.onclick = () => modal.style.display = "none";
  modal.onclick = (e) => { if (e.target === modal) modal.style.display = "none"; };
}





  // --- 📂 Раскрытие каталога (загрузка сотрудников) ---
 // === Переключение раскрытия каталога ===
async function toggleFolder(folderName) {
  // Ищем контейнер каталога
  const safeId = `folder-${folderName}`;
  const box = document.getElementById(safeId);
  if (!box) {
    console.warn(`⚠️ Каталог ${folderName} не найден (id="${safeId}")`);
    return;
  }

  // Ищем или создаём контейнер для списка агентов
  let listEl = box.querySelector(".folder-agents");
  if (!listEl) {
    listEl = document.createElement("div");
    listEl.className = "folder-agents";
    listEl.style.marginLeft = "15px";
    box.appendChild(listEl);
  }

  const expanded = box.getAttribute("data-expanded") === "1";

  if (expanded) {
    // свернуть
    listEl.innerHTML = "";
    box.setAttribute("data-expanded", "0");
    return;
  }

  // развернуть
  try {
    const res = await fetch(`/folder/${encodeURIComponent(folderName)}`,{headers: { ...authHeaders(), Accept: "application/json" }});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const agents = await res.json();

    if (!Array.isArray(agents) || agents.length === 0) {
      listEl.innerHTML = `<div class="muted">Нет сотрудников</div>`;
    } else {
      listEl.innerHTML = agents.map(a => `
        <div class="agent-row" data-slug="${a.slug}">
          <a href="/agent/${a.slug}" class="agent-name">${a.name || a.slug}</a>
          <button class="btn-mini" onclick="AIManager.deleteAgent('${a.slug}')">Удалить</button>
        </div>
      `).join("");
      
    }

    box.setAttribute("data-expanded", "1");
  } catch (e) {
    console.error("toggleFolder error:", e);
    listEl.innerHTML = `<div class="error">Ошибка загрузки сотрудников</div>`;
  }
}

// document.getElementById("logoutBtn").onclick = () => {
//   localStorage.removeItem("token");
//   window.location.href = "/login";
// };

// 👇 чтобы старые inline onclick продолжали работать
  window.AIManager = window.AIManager || {};
  window.AIManager.deleteFolder = deleteFolder;
  window.AIManager.toggleFolder = toggleFolder;
  window.AIManager.assignTask = assignTask;
  window.AIManager.assignTaskToFolder = assignTaskToFolder;
  console.log("✅ AIManager.deleteAgent инициализирован");
  console.log("✅ AIManager.toggleFolder инициализирован");



  const init = () => {
    qs("#folderForm")?.addEventListener("submit", handleCreateFolder);
  };

  return { init, toggleFolder, assignTask, assignTaskToFolder,  deleteFolder, deleteAgent, setSystemStatus };
})();


// 👇 Делаем функцию доступной глобально
// window.refreshFolderSelect = refreshFolderSelect;

// ========================================================================
// 👥 Управление модальным окном добавления сотрудника
// ========================================================================
document.addEventListener("DOMContentLoaded", () => {
  const modal     = document.getElementById("agent-modal");
  const openBtn   = document.getElementById("open-agent-modal");
  const closeBtn  = document.getElementById("close-agent-modal");
  const form      = document.getElementById("create-agent-form");
  const nameInput = document.getElementById("agent-name");
  const errorBox  = document.getElementById("agent-name-error");
  const msgBox    = document.getElementById("agent-message");

  if (!modal || !openBtn) return; // если на странице нет модалки

  // --- Открыть окно ---
  openBtn.addEventListener("click", () => {
    modal.style.display = "flex";
    refreshFolderSelect();
  });

  // --- Закрыть окно ---
  closeBtn?.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  function closeModal() {
    modal.style.display = "none";
    form.reset();
    clearError();
    msgBox.style.display = "none";
  }

  // --- Очистка ошибки при вводе ---
  nameInput.addEventListener("input", clearError);

  function showError(msg) {
    nameInput.classList.add("input-error");
    errorBox.textContent = msg;
  }

  function clearError() {
    nameInput.classList.remove("input-error");
    errorBox.textContent = "";
  }

  // --- Проверка существования агента ---
  async function agentExists(name) {
    try {
      const res = await fetch("/agents");
      if (!res.ok) return false;
      const agents = await res.json();
      return agents.some(a => a.name.toLowerCase() === name.toLowerCase());
    } catch {
      return false;
    }
  }

  // --- Отправка формы ---
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();
    msgBox.style.display = "none";
    msgBox.className = "form-message";

    const formData = new FormData(form);
    const name = formData.get("name").trim();
    const folder = formData.get("folder");

    const biasSlider = document.getElementById("team-bias");
    if (biasSlider) {
      formData.append("team_bias", biasSlider.value);
    }

    if (!name) {
      showError("Введите имя сотрудника");
      return;
    }

    // 🔹 Быстрая локальная проверка
    const existing = document.querySelectorAll(".agent-card h2");
    if ([...existing].some(h2 => h2.textContent.trim().toLowerCase() === name.toLowerCase())) {
      showError("⚠️ Сотрудник с таким именем уже есть");
      return;
    }

    // 🔹 Серверный запрос
    try {
      const res = await fetch("/create_agent", { method: "POST", body: formData,headers: { ...authHeaders(), Accept: "application/json" } });
      const data = await res.json();

      if (!data.ok) {
        msgBox.textContent = data.error || "❌ Ошибка при создании";
        msgBox.classList.add("error");
        msgBox.style.display = "block";
        return;
      }

      msgBox.textContent = `✅ Сотрудник "${name}" создан в каталоге "${folder}"`;
      msgBox.classList.add("success");
      msgBox.style.display = "block";

      form.reset();
      await AIManager.toggleFolder(folder);

      setTimeout(closeModal, 1500);
    } catch (err) {
      msgBox.textContent = "❌ Ошибка подключения к серверу";
      msgBox.classList.add("error");
      msgBox.style.display = "block";
    }
  });

  
});

// ==========================================================
// 🚀 Автоматическая загрузка каталогов при открытии страницы
// ==========================================================
document.addEventListener("DOMContentLoaded", async () => {
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.href = "/login";
    return;
  }

  try {
    const res = await fetch("/folders", {
      headers: {
        "Authorization": `Bearer ${token}`,
        "Accept": "application/json"
      }
    });

    if (!res.ok) throw new Error(`Ошибка ${res.status}`);
    const folders = await res.json();

    console.log("📂 Каталоги получены:", folders);

    const container = document.getElementById("folders-container");
    if (!container) return;

    container.innerHTML = ""; // очистка

    // для каждого каталога создаём блок
    folders.forEach(folder => {
      const html = `
        <section id="folder-${folder}" class="folder" data-folder="${folder}">
          <div class="folder-header">
            <div class="left-side">
              <i data-lucide="folder"></i>
              <h2 class="folder-title" onclick="AIManager.toggleFolder('${folder}')">${folder}</h2>
            </div>
            <div class="right-side">
              <div class="folder-actions">
                <button class="delete-folder-btn" onclick="AIManager.deleteFolder('${folder}')">
                  <i data-lucide="trash-2"></i>
                  <span>Удалить</span>
                </button>
              </div>
            </div>
          </div>

          <div class="task-box hidden" id="task-box-${folder}">
            <textarea id="task-input-${folder}" placeholder="Введите задачу для каталога '${folder}'..."></textarea>
            <button onclick="AIManager.assignTaskToFolder('${folder}')">Отправить</button>
          </div>

          <ul class="agents-list" id="agents-${folder}" style="display:none;">
            <li><em>Пока пусто</em></li>
          </ul>
        </section>
      `;

      container.insertAdjacentHTML("beforeend", html);
    });

    // Перерисовать иконки lucide
    if (window.lucide) lucide.createIcons();

  } catch (err) {
    console.error("❌ Ошибка загрузки каталогов:", err);
  }
});


// ========================================================================
// 📁 Быстрое создание каталога (рядом с "Создать сотрудника")
// ========================================================================
document.addEventListener("DOMContentLoaded", () => {
  const folderBtn = document.getElementById("open-folder-modal");
  if (!folderBtn) return;

  folderBtn.addEventListener("click", async () => {
    const name = prompt("Введите имя нового каталога:");
    if (!name) return;

    try {
      const res = await fetch("/create_folder", {
        method: "POST",
        headers: { ...authHeaders(), Accept: "application/json" },
        body: new URLSearchParams({ name }),
      });

      const data = await res.json();
      if (data.ok) {
        alert(`✅ Каталог '${name}' создан`);
        if (typeof refreshFolderSelect === "function") await refreshFolderSelect();
      } else if (data.error === "exists") {
        alert(`⚠️ Каталог '${name}' уже существует`);
      } else {
        alert(`❌ Ошибка при создании: ${data.error || "неизвестно"}`);
      }
    } catch (err) {
      console.error("Ошибка при создании каталога:", err);
      alert("❌ Ошибка соединения с сервером");
    }
  });
});


// ========================================================================
// 🌍 Глобальные экспорты (для office.js и других модулей)
// ========================================================================

// Безопасное обновление списка каталогов
window.refreshFolderSelect = async function refreshFolderSelect() {
  try {
    const token = localStorage.getItem("token");
    const headers = token
      ? { "Authorization": `Bearer ${token}`, "Accept": "application/json" }
      : { "Accept": "application/json" };

    const res = await fetch("/folders", { headers });
    if (!res.ok) {
      const text = await res.text();
      console.warn("⚠️ Ошибка загрузки каталогов:", res.status, text);
      return;
    }

    const folders = await res.json();
    const select = document.getElementById("folder-select");
    if (!select) return;
    select.innerHTML = folders.map(f => `<option value="${f}">${f}</option>`).join("");

  } catch (e) {
    console.error("Ошибка при загрузке каталогов:", e);
  }
};




// Экспортируем buildGraphData, чтобы office.js мог строить граф
window.buildGraphData = function buildGraphData(agents) {
  const folderSet = new Set(agents.map(a => a.folder || "root"));

  const folderNodes = Array.from(folderSet).map((f, i) => ({
    id: `folder:${f}`,
    label: f,
    type: "folder",
    folder: f,
    fx: 250 * Math.cos((i / folderSet.size) * 2 * Math.PI),
    fy: 250 * Math.sin((i / folderSet.size) * 2 * Math.PI)
  }));

  const agentNodes = agents.map(a => ({
    id: a.slug,
    label: a.name,
    type: "agent",
    folder: a.folder || "root",
    status: a.status || "done",
    last_task: a.last_task || null,
  }));

  agentNodes.forEach(a => {
    const style = getAgentStyle(a);
    a.baseColor = style.color;
  });

  const links = agentNodes.map(a => ({
    source: a.id,
    target: `folder:${a.folder}`
  }));

  return { nodes: [...folderNodes, ...agentNodes], links };
};

// ========================================================================
// 🎨 Экспорт функции определения цвета узлов (для office.js)
// ========================================================================
window.colorByStatus = function colorByStatus(node) {
  if (node.type === "folder") return "#48cae4"; // голубой — каталоги

  switch (node.status) {
    case "running": return "#ffd166"; // жёлтый
    case "error":   return "#ef476f"; // красный
    case "done":    return "#06d6a0"; // зелёный
    default:        return node.baseColor || "#9ba9bb"; // базовый серый
  }
};

// ========================================================================
// 🧠 Экспорт обработчика кликов по узлам графа (для office.js)
// ========================================================================
window.onGraphNodeClick = function onGraphNodeClick(node) {

  // проверяем, есть ли fillSidepanel
  if (typeof fillSidepanel === "function") {
    centerOnFolder(node.id, 1000);//  из brainstorm.js
    fillSidepanel(node);
  } else {
    console.warn("⚠️ fillSidepanel не найден, клик обработан без панели");
  }

  // отмечаем выбранный узел
  if (window.__OfficeGraph__) {
    window.__OfficeGraph__.selectedNodeId = node.id;
  }

  // перерисовка графа, чтобы подсветка применялась сразу
  const G = window.__OfficeGraph__?.Graph;
  if (G) G.graphData(G.graphData());

};

// === Отключаем автозум ForceGraph навсегда ===
function disableForceGraphAutoZoom(Graph) {
  console.log('disableForceGraphAutoZoom')
   if (!Graph || Graph.__autoZoomPatched) return;

  const noop = () => {};
  // 1️⃣ Глушим встроенные методы автоцентрирования
  ['zoomToFit', 'fitToScene', '_updateScene'].forEach(fn => {
    if (typeof Graph[fn] === 'function') {
      Graph[`__orig_${fn}`] = Graph[fn];
      Graph[fn] = noop;
    }
  });

  // 2️⃣ Отключаем встроенный "center" force, чтобы граф не стягивался к (0,0)
  try {
    const centerForce = Graph.d3Force('center');
    if (centerForce) Graph.d3Force('center', null);
  } catch (err) {
    console.warn('Не удалось отключить d3Force(center):', err);
  }

  Graph.__autoZoomPatched = true;
  console.log('✅ ForceGraph авто-зум и авто-центрирование отключены');
}

// === 🧠 Глобальный статус системы ===
function setSystemStatus(state, message) {
  const bar = document.getElementById("system-status-bar");
  const text = document.getElementById("system-status-text");
  const icon = document.getElementById("system-status-icon");
  if (!bar || !text ) return;

  bar.classList.remove("active", "busy", "error");

  switch (state) {
    case "busy":
      text.textContent = message || "Идёт обработка задачи...";
      bar.classList.add("busy");
      break;
    case "error":
      text.textContent = message || "Ошибка системы";
      bar.classList.add("error");
      break;
    default:
      text.textContent = message || "Все агенты активны";
      bar.classList.add("active");
      break;
  }
}

// === 📁 Добавление кнопки "Добавить сотрудника" в карточку каталога ===
function addCreateAgentButtonToFolder(folderName) {
  const folderSection = document.querySelector(`#folder-${folderName} .folder-actions`);
  if (!folderSection) return;

  // не дублируем кнопку
  if (folderSection.querySelector(".add-agent-btn")) return;

  const btn = document.createElement("button");
  btn.className = "add-agent-btn";
  btn.innerHTML = `<i data-lucide="user-plus"></i> Добавить сотрудника`;
  btn.onclick = () => openAgentModalForFolder(folderName);

  folderSection.prepend(btn);
  if (window.lucide) lucide.createIcons();
}

// === 🧩 Открытие модального окна создания сотрудника для конкретного каталога ===
window.openAgentModalForFolder = function openAgentModalForFolder(folderName) {
  const modal = document.getElementById("agent-modal");
  if (!modal) return;

  const title = modal.querySelector("h2");
  const folderSelect = modal.querySelector("#folder-select");
  const folderLabel = modal.querySelector("label[for='folder-select']");
  const form = modal.querySelector("form");

  // Изменяем заголовок
  if (title) title.textContent = `👤 Добавить сотрудника в каталог "${folderName}"`;

  // Скрываем выбор каталога
  if (folderSelect) folderSelect.style.display = "none";
  if (folderLabel) folderLabel.style.display = "none";

  // Добавляем скрытое поле с именем каталога
  let hiddenInput = form.querySelector("input[name='folder']");
  if (!hiddenInput) {
    hiddenInput = document.createElement("input");
    hiddenInput.type = "hidden";
    hiddenInput.name = "folder";
    form.appendChild(hiddenInput);
  }
  hiddenInput.value = folderName;

  // Открываем модалку
  modal.style.display = "flex";
};

// === 🚀 Расширяем renderFolder так, чтобы добавлялась кнопка сотрудника ===
const originalRenderFolder = renderFolder;
renderFolder = (name) => {
  originalRenderFolder(name);
  addCreateAgentButtonToFolder(name);
};

// === 🚀 После загрузки каталогов с сервера добавляем кнопки ===
document.addEventListener("DOMContentLoaded", () => {
  const observer = new MutationObserver(() => {
    document.querySelectorAll(".folder").forEach(folder => {
      const name = folder.dataset.folder;
      addCreateAgentButtonToFolder(name);
    });
  });
  const container = document.getElementById("folders-container");
  if (container) observer.observe(container, { childList: true, subtree: true });
});






