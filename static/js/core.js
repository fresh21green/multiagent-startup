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
          <div class="folder-actions">
            <button class="assign-btn" onclick="toggleTaskBox('${name}')">
              <i data-lucide="rocket"></i> Задать задачу
            </button>
            <button class="delete-folder-btn" onclick="AIManager.deleteFolder('${name}')">
              <i data-lucide="trash-2"></i> Удалить
            </button>
          </div>
        </div>
        <div class="task-box hidden" id="task-box-${name}">
          <textarea placeholder="Введите задачу для всех сотрудников каталога '${name}'..." id="task-input-${name}"></textarea>
          <button onclick="assignTaskToFolder('${name}')">Отправить</button>
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

  // --- 🤖 Создание сотрудника ---
  const handleCreateAgent = async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    try {
      const res = await fetch("/create_agent", { method: "POST", body: formData });
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
  const deleteAgent = async (slug, folder) => {
    const li = document.querySelector(`#agents-${folder} li:has(a[href="/agent/${slug}"])`);
    if (!li) return;

    const confirmBox = document.createElement("div");
    confirmBox.className = "confirm-delete";
    confirmBox.innerHTML = `
      <span>Удалить?</span>
      <button class="yes">Да</button>
      <button class="no">Отмена</button>
    `;
    li.appendChild(confirmBox);

    confirmBox.querySelector(".yes").onclick = async () => {
      const res = await fetch("/delete_agent", {
        method: "POST",
        body: new URLSearchParams({ slug }),
      });
      const data = await res.json();
      if (data.ok) {
        li.style.opacity = "0";
        setTimeout(() => li.remove(), 300);
        showMessage(`🗑️ Удалён '${slug}'`);
      } else showMessage(`❌ ${data.error}`, "error");
    };
    confirmBox.querySelector(".no").onclick = () => confirmBox.remove();
  };

  // --- 📂 Раскрытие каталога (загрузка сотрудников) ---
 // === Переключение раскрытия каталога ===
  async function toggleFolder(folder) {
    const list = document.getElementById(`agents-${folder}`);
    if (!list) return;

    // Проверяем текущее состояние
    const isOpen = list.style.display === "block";

    // Скрываем все другие списки
    document.querySelectorAll(".agents-list").forEach(ul => (ul.style.display = "none"));

    // Если кликнули на уже открытый — просто свернуть
    if (isOpen) {
      list.style.display = "none";
      return;
    }

    // Иначе — открыть и подгрузить сотрудников
    list.style.display = "block";

    try {
      const res = await fetch(`/folder/${encodeURIComponent(folder)}`);
      if (!res.ok) throw new Error("Ошибка загрузки сотрудников");
      const agents = await res.json();
      list.innerHTML = agents.length
        ? agents.map(a => `
            <li>
              🤖 <a href="/agent/${a.slug}" target="_blank">${a.name}</a>
              <button class="icon-btn delete-agent-btn" onclick="AIManager.deleteAgent('${a.slug}', '${folder}')">
                <i data-lucide="trash-2"></i>
              </button>
            </li>`).join("")
        : "<li><em>Нет сотрудников.</em></li>";
      if (window.lucide) lucide.createIcons();
    } catch {
      list.innerHTML = "<li><em>⚠️ Ошибка загрузки сотрудников</em></li>";
    }
  }

  // --- ⚙️ Установка системного статуса ---
  const setSystemStatus = (state, message) => {
    const bar  = qs("#system-status-bar");
    const text = qs("#system-status-text");
    const icon = qs("#system-status-icon");
    if (!bar || !text || !icon) return;
    bar.classList.remove("active", "busy", "error");
    switch (state) {
      case "busy":  icon.textContent = "⚙️"; bar.classList.add("busy"); break;
      case "error": icon.textContent = "⚠️"; bar.classList.add("error"); break;
      default:      icon.textContent = "🧠"; bar.classList.add("active");
    }
    text.textContent = message || "Все агенты активны";
  };

  const init = () => {
    qs("#folderForm")?.addEventListener("submit", handleCreateFolder);
  };

  return { init, toggleFolder, deleteAgent, setSystemStatus };
})();

// --- 🔄 Обновление выпадающего списка каталогов ---
async function refreshFolderSelect() {
  try {
    const res = await fetch("/folders");
    if (!res.ok) throw new Error("Не удалось получить список каталогов");

    const folders = await res.json();
    const select = document.getElementById("folder-select");
    if (!select) return console.warn("⚠️ Не найден элемент #folder-select");

    select.innerHTML = folders.map(f => `<option value="${f}">${f}</option>`).join("");
  } catch (err) {
    console.error("Ошибка при обновлении списка каталогов:", err);
  }
}

// 👇 Делаем функцию доступной глобально
window.refreshFolderSelect = refreshFolderSelect;

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
      const res = await fetch("/create_agent", { method: "POST", body: formData });
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

// ========================================================================
// 🌍 Глобальные экспорты (для office.js и других модулей)
// ========================================================================

// Безопасное обновление списка каталогов
window.refreshFolderSelect = async function refreshFolderSelect() {
  try {
    const res = await fetch("/folders");
    if (!res.ok) throw new Error("Не удалось получить список каталогов");
    const folders = await res.json();
    const select = document.getElementById("folder-select");
    if (!select) return; // просто выходим, если на странице нет селекта
    select.innerHTML = folders.map(f => `<option value="${f}">${f}</option>`).join("");
  } catch (e) {
    console.warn("⚠️ Ошибка при загрузке каталогов:", e.message);
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
  if (!bar || !text || !icon) return;

  bar.classList.remove("active", "busy", "error");

  switch (state) {
    case "busy":
      icon.textContent = "⚙️";
      text.textContent = message || "Идёт обработка задачи...";
      bar.classList.add("busy");
      break;
    case "error":
      icon.textContent = "⚠️";
      text.textContent = message || "Ошибка системы";
      bar.classList.add("error");
      break;
    default:
      icon.textContent = "🧠";
      text.textContent = message || "Все агенты активны";
      bar.classList.add("active");
      break;
  }
}


