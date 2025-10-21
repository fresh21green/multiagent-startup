// ===============================
// AI Менеджер — основной модуль
// ===============================
const AIManager = (() => {
  // ===============================
  // Вспомогательные функции
  // ===============================
  const qs = (selector) => document.querySelector(selector);
  const qsa = (selector) => document.querySelectorAll(selector);

  const showMessage = (text, type = "info") => {
    const msgBox = qs("#folderMessage");
    if (!msgBox) return;
    msgBox.textContent = text;
    msgBox.className = type;
    setTimeout(() => (msgBox.textContent = ""), 1500); // исчезает через секунду
  };

  // ===============================
  // 1. Создание каталога
  // ===============================
  const handleCreateFolder = async (e) => {
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

  // Добавить в список селектов
  const addFolderToSelect = (name) => {
    const select = qs("#folder-select");
    if (!select) return;
    if ([...select.options].some((o) => o.value === name)) return;
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    select.appendChild(opt);
  };

  // Отрисовать новый блок каталога
 const renderFolder = (name) => {
  const container = qs("#folders-container");
  if (!container) return;
  if (qs(`#folder-${name}`)) return; // уже есть

  const html = `
    <section id="folder-${name}" class="folder" data-folder="${name}">
      <div class="folder-header">
        <h2 class="folder-title" onclick="AIManager.toggleFolder('${name}')">📂 ${name}</h2>
        <div class="folder-actions">
          <button class="assign-btn" onclick="toggleTaskBox('{{ folder }}')">
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

// === Показ / скрытие поля задачи ===
window.toggleTaskBox = (folder) => {
  const box = document.querySelector(`#task-box-${folder}`);
  if (!box) return;
  box.classList.toggle("hidden");
};

  // ===============================
  // 2. Создание агента
  // ===============================
  const handleCreateAgent = async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    try {
      const res = await fetch("/create_agent", { method: "POST", body: formData });
      if (res.redirected || res.ok) {
        const folder = formData.get("folder") || "root";
        const name = formData.get("name");
        const slug = name.toLowerCase().replace(/[^a-z0-9_-]/g, "_");

        addAgentToFolder(folder, name, slug);
        addAgentCard(folder, name, slug);
        showMessage(`✅ Сотрудник '${name}' создан`);
        form.reset();
      } else {
        showMessage("❌ Ошибка при создании агента", "error");
      }
    } catch (err) {
      console.error(err);
      showMessage("⚠️ Ошибка соединения с сервером", "error");
    }
  };

const addAgentToFolder = (folder, name, slug) => {
  const section = document.querySelector(`#folder-${folder} ul`);
  if (!section) return;

  const empty = section.querySelector("em");
  if (empty) empty.parentElement.remove();

  section.insertAdjacentHTML(
    "beforeend",
    `
    <li>
      🤖 <a href="/agent/${slug}" target="_blank">${name}</a>
      <button class="icon-btn delete-agent-btn"
              title="Удалить сотрудника"
              onclick="AIManager.deleteAgent('${slug}', '${folder}')">
        <i data-lucide="trash-2"></i>
      </button>
    </li>`
  );

  // после вставки обновляем иконки
  if (window.lucide) lucide.createIcons();
};


 const addAgentCard = (folder, name, slug) => {
  const list = qs(".ai-agents ul") || createAgentsSection();
  const card = `
    <li class="agent-card" id="agent-card-${slug}">
      <div class="ai-agent-header">
        <h2>${name}</h2>
        <div class="agent-status" id="status-${slug}">Статус: Готов</div>
        <a href="/agent/${slug}" target="_blank" class="agent-link">🔗 Перейти к сотруднику</a>
      </div>

      <div style="display:inline;">
        <input type="hidden" name="slug" value="${slug}">
        <textarea name="task" class="task" id="task-${slug}" placeholder="Задача для этого сотрудника" required></textarea>
        <button type="submit" class="send-task-button" id="btn-${slug}" onclick="AIManager.assignTask('${slug}')">Отправить задачу</button>
        <div class="result markdown-body" id="result-${slug}"></div>
      </div>

      <form action="/delete_agent" method="post" style="display:inline;">
        <input type="hidden" name="slug" value="${slug}">
        <button type="submit" class="delete-agent-button">Удалить сотрудника</button>
      </form>
    </li>`;
  if (folder === "root") list.insertAdjacentHTML("beforeend", card);
};

  const createAgentsSection = () => {
    const div = document.createElement("div");
    div.className = "ai-agents";
    div.innerHTML = "<ul></ul>";
    qs(".container").appendChild(div);
    return div.querySelector("ul");
  };

  // ===============================
  // 3. Удаление
  // ===============================
const deleteAgent = async (slug, folder) => {
  const li = document.querySelector(`#agents-${folder} li:has(a[href="/agent/${slug}"])`);
  if (!li) return;

  // если уже открыто подтверждение — ничего не делаем
  if (li.querySelector(".confirm-delete")) return;

  // создаём блок подтверждения
  const confirmBox = document.createElement("div");
  confirmBox.className = "confirm-delete";
  confirmBox.innerHTML = `
    <span>Удалить?</span>
    <button class="yes">Да</button>
    <button class="no">Отмена</button>
  `;
  li.appendChild(confirmBox);

  const btnYes = confirmBox.querySelector(".yes");
  const btnNo = confirmBox.querySelector(".no");

  // === Нажатие "Да"
  btnYes.addEventListener("click", async () => {
    try {
      const res = await fetch("/delete_agent", {
        method: "POST",
        body: new URLSearchParams({ slug }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Ошибка удаления");

      // плавное исчезновение
      li.style.transition = "opacity 0.3s ease";
      li.style.opacity = "0";
      setTimeout(() => li.remove(), 300);

      showMessage(`🗑️ Сотрудник '${slug}' удалён`);
    } catch (err) {
      console.error(err);
      showMessage(`❌ ${err.message}`, "error");
    }
  });

  // === Нажатие "Отмена"
  btnNo.addEventListener("click", () => confirmBox.remove());

  // авто-удаление блока подтверждения через 3 с
  setTimeout(() => confirmBox.remove(), 3000);
};



  const deleteFolder = async (folder) => {
    if (!confirm(`Удалить каталог '${folder}'? Он должен быть пуст.`)) return;
    const res = await fetch("/delete_folder", {
      method: "POST",
      body: new URLSearchParams({ name: folder }),
    });
    const data = await res.json();
    if (data.ok) {
      qs(`#folder-${folder}`)?.remove();
      showMessage(`✅ Каталог '${folder}' удалён`);
    } else if (data.error === "not_empty") {
      showMessage(`⚠️ Каталог не пуст (${data.count})`);
    } else {
      showMessage(`❌ Ошибка: ${data.error}`, "error");
    }
  };

  // ===============================
  // 4. Раскрытие каталогов
  // ===============================
const toggleFolder = async (folder) => {
  const encoded = encodeURIComponent(folder);
  const list = document.getElementById(`agents-${folder}`);
  if (!list) return;

  // Скрываем другие каталоги
  document.querySelectorAll(".agents-list").forEach((ul) => (ul.style.display = "none"));
  list.style.display = "block";

  try {
    const res = await fetch(`/folder/${encoded}`);
    if (!res.ok) throw new Error("Ошибка загрузки сотрудников");

    const agents = await res.json();
    list.innerHTML = "";

    if (!agents.length) {
      list.innerHTML = "<li><em>Нет сотрудников.</em></li>";
      return;
    }

    agents.forEach((a) => {
      const li = document.createElement("li");
      li.innerHTML = `
        🤖 <a href="/agent/${a.slug}" target="_blank">${a.name}</a>
        <button class="icon-btn delete-agent-btn"
          onclick="AIManager.deleteAgent('${a.slug}', '${folder}')"
          title="Удалить сотрудника">
          <i data-lucide="trash-2"></i>
        </button>
      `;
      list.appendChild(li);
    });

    // переинициализировать иконки
    if (window.lucide) lucide.createIcons();
  } catch (err) {
    console.error("Ошибка при загрузке:", err);
    list.innerHTML = "<li><em>⚠️ Ошибка загрузки сотрудников</em></li>";
  }
};



const renderAgentsInSection = (agents) => {
  let ul = qs(".ai-agents ul");
  if (!ul) {
    const div = document.createElement("div");
    div.className = "ai-agents";
    div.innerHTML = "<ul></ul>";
    qs(".container").appendChild(div);
    ul = div.querySelector("ul");
  }

  ul.innerHTML = "";

  if (!agents.length) {
    ul.innerHTML = "<p><em>Нет сотрудников.</em></p>";
    return;
  }

  for (const a of agents) {
    const last = a.last_task || {};
    const taskText = last.task ? last.task : "—";
    const resultHtml = last.result?.html || last.result || "—";

    const html = `
      <li class="agent-card" id="agent-card-${a.slug}">
        <div class="ai-agent-header">
          <h2>${a.name}</h2>
          <div class="agent-status" id="status-${a.slug}">Статус: Готов</div>
          <a href="/agent/${a.slug}" target="_blank" class="agent-link">🔗 Перейти к сотруднику</a>
        </div>

        <div class="task-input">
          <input type="hidden" name="slug" value="${a.slug}">
          <textarea name="task" id="task-${a.slug}" placeholder="Задача для этого сотрудника" required></textarea>
          <button type="submit" id="btn-${a.slug}" onclick="AIManager.assignTask('${a.slug}')">
            Отправить задачу
          </button>
        </div>

        <form action="/delete_agent" method="post" style="display:inline;">
          <input type="hidden" name="slug" value="${a.slug}">
          <button type="submit" class="delete-agent-button">Удалить сотрудника</button>
        </form>

         <div class="last-task">
          <div class="task-header">
            <span>📝 Последняя задача:</span>
          </div>
          <div class="result markdown-body">${resultHtml}</div>
        </div>
      </li>
    `;
    ul.insertAdjacentHTML("beforeend", html);
  }
};

  // ===============================
  // 5. Поручить задачу агенту
  // ===============================
  async function assignTask(slug) {
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


  // ===============================
// 6. Поручить задачу всему каталогу
// ===============================
// ===============================
// 6. Поручить задачу всему каталогу (с анимацией)
// ===============================
// === 🧩 Поручить задачу всему каталогу ===
async function assignTaskToFolder(folder) {
  const task = document.getElementById(`task-input-${folder}`)?.value.trim();
  if (!task) return alert("Введите задачу для каталога");

  const button = document.querySelector(`#folder-${folder} .assign-btn`);
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "⚙️ Выполняется...";

  setSystemStatus("busy", `⚙️ Выполняется задача для каталога "${folder}"...`);

  // Находим все карточки сотрудников в этом каталоге
  const cards = Array.from(document.querySelectorAll(".agent-card"))
    .filter(c => c.dataset.folder === folder);

  // Визуально переводим всех сотрудников в статус "выполняется"
  for (const card of cards) {
    const status = card.querySelector(".agent-status");
    const resultBox = card.querySelector(".result");
    if (status) {
      status.textContent = "Статус: ⚙️ Выполняется...";
      status.className = "agent-status running";
    }
    if (resultBox) {
      resultBox.innerHTML = `<div class="spinner"></div> Выполняется...`;
      resultBox.style.display = "block";
    }
  }

  try {
    const res = await fetch("/assign_task_folder", {
      method: "POST",
      body: new URLSearchParams({ folder, task }),
    });
    const data = await res.json();

    if (!data.ok) throw new Error(data.error || "Ошибка выполнения");

    // 🧩 Обновляем карточки каждого сотрудника
    for (const { agent, result } of data.results) {
      const card = document.querySelector(`#agent-card-${agent}`);
      if (!card) continue;

      const status = card.querySelector(".agent-status");
      const resultBox = card.querySelector(".result");

      status.textContent = "Статус: ✅ Готово";
      status.className = "agent-status done";
      resultBox.innerHTML = result?.html || result || "—";
      resultBox.style.display = "block";

      // Добавляем визуальную вспышку успешного выполнения
      card.classList.add("done");
      setTimeout(() => card.classList.remove("done"), 1500);
    }

    setSystemStatus("active", "🧠 Все агенты активны");
  } catch (err) {
    console.error(err);
    setSystemStatus("error", "❌ Ошибка при выполнении задачи каталога");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

// === 🧠 Управление верхним статус-баром ===
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
    case "active":
    default:
      icon.textContent = "🧠";
      text.textContent = message || "Все агенты активны";
      bar.classList.add("active");
      break;
  }
}


  // ===============================
  // Инициализация
  // ===============================
  const init = () => {
    qs("#folderForm")?.addEventListener("submit", handleCreateFolder);
  };

  return { init, toggleFolder, deleteAgent, deleteFolder, assignTask, assignTaskToFolder, setSystemStatus };
})();

// === Запуск ===
document.addEventListener('DOMContentLoaded', () => {
  AIManager.init
  if (window.lucide) lucide.createIcons();
});

// === Управление модальным окном добавления сотрудника ===
// === Управление модальным окном добавления сотрудника ===
document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("agent-modal");
  const openBtn = document.getElementById("open-agent-modal");
  const closeBtn = document.getElementById("close-agent-modal");
  const form = document.getElementById("create-agent-form");
  const nameInput = document.getElementById("agent-name");
  const errorBox = document.getElementById("agent-name-error");

  // открыть модалку
  openBtn?.addEventListener("click", () => {
    modal.style.display = "flex";
    refreshFolderSelect();
  });

  // закрыть модалку
  closeBtn?.addEventListener("click", () => {
    modal.style.display = "none";
    form.reset();
    clearError();
  });

  // клик по фону — закрыть
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.style.display = "none";
      form.reset();
      clearError();
    }
  });

  // Очистка ошибки при вводе
  nameInput.addEventListener("input", () => {
    clearError();
  });

  function showError(msg) {
    nameInput.classList.add("input-error");
    errorBox.textContent = msg;
  }

  function clearError() {
    nameInput.classList.remove("input-error");
    errorBox.textContent = "";
  }

  // === Проверка, существует ли агент ===
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

  // === Отправка формы ===
form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();

    const formData = new FormData(form);
    const name = formData.get("name").trim();
    const folder = formData.get("folder");
    const msgBox = document.getElementById("agent-message");

    msgBox.style.display = "none";
    msgBox.className = "form-message"; // сброс цвета

    if (!name) {
      showError("Введите имя сотрудника");
      return;
    }

    // 🔹 Быстрая локальная проверка (в памяти)
    const existing = document.querySelectorAll(".agent-card h2");
    if ([...existing].some(h2 => h2.textContent.trim().toLowerCase() === name.toLowerCase())) {
      showError("⚠️ Сотрудник с таким именем уже есть в этом каталоге");
      return;
    }

    try {
      // 🔹 Один запрос — без дублирования
      const res = await fetch("/create_agent", { method: "POST", body: formData });
      const data = await res.json();

      // 🔹 Проверяем ответ сервера
      if (!data.ok) {
        const errorText = data.error?.includes("существует")
          ? "⚠️ Сотрудник с таким именем уже существует"
          : data.error || "❌ Ошибка при создании сотрудника";

        msgBox.textContent = errorText;
        msgBox.classList.add("error");
        msgBox.style.display = "block";
        return;
      }

      // ✅ Успешное создание
      msgBox.textContent = `✅ Сотрудник "${name}" создан в каталоге "${folder}"`;
      msgBox.classList.add("success");
      msgBox.style.display = "block";

      // Очистка формы
      form.reset();
      clearError();

      // Обновляем каталог
      await AIManager.toggleFolder(folder);

      // Закрываем модалку через 1.5 сек
      setTimeout(() => {
        modal.style.display = "none";
        msgBox.style.display = "none";
      }, 1500);
    } catch (err) {
      console.error(err);
      msgBox.textContent = "❌ Ошибка подключения к серверу";
      msgBox.classList.add("error");
      msgBox.style.display = "block";
    }
  });


});


 async function refreshFolderSelect() {
    console.log('refreshFolderSelect')
    try {
      const res = await fetch("/folders");
      if (!res.ok) throw new Error("Не удалось получить список каталогов");
      const folders = await res.json();
      const select = document.getElementById("folder-select");
      if (!select) {
        console.warn("⚠️ Не найден элемент #folder-select");
        return;
      }

      select.innerHTML = folders
        .map(f => `<option value="${f}">${f}</option>`)
        .join("");
    } catch (e) {
      console.error("Ошибка при загрузке каталогов:", e);
    }
}

// =============== ВИРТУАЛЬНЫЙ ОФИС: ForceGraph ===============
// === 🧩 Получаем всех агентов из всех каталогов ===
async function fetchAgentsForOffice() {
  try {
    // Получаем список всех папок
    const resFolders = await fetch("/folders");
    if (!resFolders.ok) throw new Error("Не удалось получить каталоги");
    const folders = await resFolders.json(); // ['root', 'demo', 'research', ...]

    const agents = [];
    // Поочередно загружаем агентов из каждой папки
    for (const folder of folders) {
      try {
        const res = await fetch(`/folder/${folder}`);
        if (!res.ok) continue;
        const list = await res.json();
        for (const a of list) {
          a.folder = folder; // помечаем, из какой папки
          agents.push(a);
        }
      } catch (e) {
        console.warn(`⚠️ Ошибка при загрузке ${folder}:`, e);
      }
    }

    console.log("✅ Всего агентов:", agents.length);
    return agents;
  } catch (err) {
    console.error("Ошибка при загрузке всех агентов:", err);
    return [];
  }
}

function buildGraphData(agents) {
  // Собираем все папки
  const folderSet = new Set(agents.map(a => a.folder || "root"));

  const folderNodes = Array.from(folderSet).map((f, i) => ({
    id: `folder:${f}`,
    label: f,
    type: "folder",
    folder: f,
    // 📍фиксированные координаты для папок (распределяем в круг)
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
    a.baseColor = style.color; // 🔹 сохраняем исходный цвет
  });

  // Связи агент → его папка
  const links = agentNodes.map(a => ({
    source: a.id,
    target: `folder:${a.folder}`
  }));

  return { nodes: [...folderNodes, ...agentNodes], links };
}



function colorByStatus(node) {
  console.log('node',node)
  if (node.type === "folder") return "#48cae4";

  // 🔹 Если агент выполняет задачу
  if (node.status === "running") return "#ffd166";

  // 🔹 Если ошибка
  if (node.status === "error") return "#ef476f";

  // 🔹 Если агент завершил задачу
  if (node.status === "done") return "#08f070ff"; // зелёный

  // 🔹 Если агент просто “активен”, показываем его базовый цвет (по роли)
  return node.baseColor || "#9ba9bb";
}


let currentNode = null;

function fillSidepanel(node) {
  const title = document.getElementById("sp-title");
  const meta  = document.getElementById("sp-meta");
  const last  = document.getElementById("sp-last");
  // const lastTask = document.getElementById("sp-last-task");
  const lastRes  = document.getElementById("sp-last-result");
  const actions = document.getElementById("sp-actions");
  const folderActions = document.getElementById("sp-folder-actions");
  const folderResults = document.getElementById("sp-folder-results");
  const sendBtn = document.getElementById("sp-send");
  const sendFolderBtn = document.getElementById("sp-folder-send");

  title.textContent = node.label || "Узел";
  title.dataset.slug = (node.type === "agent") ? node.id : "";

  meta.innerHTML = `
    <div>Тип: <b>${node.type === "folder" ? "Каталог" : "Сотрудник"}</b></div>
    <div>Группа: <b>${node.folder || "—"}</b></div>
    ${node.type === "agent" ? `<div>Статус: <span class="status ${node.status || "done"}">${node.status || "—"}</span></div>` : ""}
  `;

  if (node.type === "agent") {
    // ==== Одиночный сотрудник ====
    console.log('node',node)
    const t = node.last_task?.task || "—";
    const r = node.last_task?.result?.html || node.last_task?.result || "—";
    last.style.display = "block";
    lastRes.style.display = "block";
    // lastTask.innerHTML = marked.parse(`🧩 Последняя задача:\n\n${t}`);
    lastRes.innerHTML = r;
    const showLink = document.getElementById("sp-show-result");
    if (r && r.trim() && r !== "—") {
      showLink.style.display = "inline-block";
      showLink.textContent = "📊 Показать результат";
      showLink.onclick = (e) => {
        e.preventDefault();
        showAgentResultBlock(node.label, r);
      };
    } else {
      showLink.style.display = "none";
    }
    // lastTask.textContent = `🧩 Последняя задача: ${t}`;
    
    actions.style.display = "flex";
    folderActions.style.display = "none";
    folderResults.style.display = "none";

    sendBtn.onclick = async () => {
      const task = (document.getElementById("sp-task")?.value || "").trim();
      if (!task) return alert("Введите задачу");
      await assignTaskFromOffice(node.id, task);
    };
  } 
  else if (node.type === "folder") {
    actions.style.display = "none";
    last.style.display = "none";
    folderActions.style.display = "flex";
    folderResults.style.display = "none";

    // 🧠 показываем секцию мозгового штурма
    const brainstormBox = document.getElementById("sp-brainstorm");
    if (brainstormBox) brainstormBox.style.display = "flex";

    sendFolderBtn.onclick = async () => {
      const task = (document.getElementById("sp-folder-task")?.value || "").trim();
      if (!task) return alert("Введите задачу для каталога");
      await assignTaskToFolderFromOffice(node.folder, task);
    };

    const brainstormBtn = document.getElementById("sp-brainstorm-send");
    brainstormBtn.onclick = async () => {
      const topic = (document.getElementById("sp-brainstorm-topic")?.value || "").trim();
      if (!topic) return alert("Введите тему штурма");
      await runBrainstormFromOffice(node.folder, topic);
    };
  }
  else {
    actions.style.display = "none";
    folderActions.style.display = "none";
    folderResults.style.display = "none";
    last.style.display = "none";
  }
}


function onGraphNodeClick(node) {
  fillSidepanel(node);
  // снимаем прошлое выделение
  if (window.__OfficeGraph__) {
    window.__OfficeGraph__.selectedNodeId = node.id;
  }

  // 🔄 перерисовка
  const G = window.__OfficeGraph__?.Graph;
  if (G) G.graphData(G.graphData());
}

// отправка задачи из боковой панели конкретному сотруднику
// === 🧠 Отправка задачи из правой панели (office.html) ===
async function assignTaskFromOffice(slug, task) {
  const statusBlock = document.querySelector("#sp-meta");
  // const lastTask = document.querySelector("#sp-last-task");
  const resultBox = document.querySelector("#sp-last-result");

  setSystemStatus("busy", "⚙️ Выполняется задача...");
  statusBlock.innerHTML += `<div><b>⚙️ Выполняется...</b></div>`;
  // lastTask.textContent = `🧩 Последняя задача: ${task}`;
  resultBox.innerHTML = `<div class="spinner"></div> Выполняется...`;

  try {
    // включаем мигание
    window.__OfficeGraph__?.setAgentStatus(slug, "running");
    window.__OfficeGraph__?.refresh();

    const res = await fetch("/assign_task", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ slug, task }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Ошибка выполнения");

    window.__OfficeGraph__?.setAgentStatus(slug, "done", data.result?.html, task);
    window.__OfficeGraph__?.refresh();

    // ✅ результат получен — обновляем правую панель
    statusBlock.innerHTML = `
      <div>Тип: <b>Сотрудник</b></div>
      <div>Каталог: <b>${currentNode?.folder || "—"}</b></div>
      <div>Статус: <b>✅ Готово</b></div>
    `;
    // lastTask.textContent = `🧩 Последняя задача: ${task}`;
    resultBox.innerHTML = data.result?.html || data.result || "—";
    resultBox.scrollTop = resultBox.scrollHeight; // автопрокрутка вниз

    // обновляем состояние узла на графе
    window.__OfficeGraph__?.setAgentStatus(slug, "done", data.result?.html, task);
    setSystemStatus("active", "🧠 Все агенты активны");
  } catch (err) {
    console.error(err);
    window.__OfficeGraph__?.setAgentStatus(slug, "error");
    window.__OfficeGraph__?.refresh();;
    resultBox.innerHTML = `<p class="error">❌ Ошибка: ${err.message}</p>`;
    window.__OfficeGraph__?.setAgentStatus(slug, "error");
    setSystemStatus("error", "❌ Ошибка при выполнении задачи");
  }
}

async function assignTaskToFolderFromOffice(folder, task) {
  const folderResults = document.getElementById("sp-folder-results");
  folderResults.style.display = "block";
  folderResults.innerHTML = `<div class="spinner"></div> ⚙️ Выполняется задача для каталога <b>${folder}</b>...`;

  setSystemStatus("busy", `⚙️ Задача выполняется для каталога "${folder}"`);

  // === 🟡 1. Мгновенная реакция UI: все сотрудники начинают мигать ===
  try {
    const graphData = window.__OfficeGraph__?.Graph?.graphData();
    if (graphData) {
      for (const node of graphData.nodes) {
        if (node.type === "agent" && node.folder === folder) {
          window.__OfficeGraph__?.setAgentStatus(node.id, "running");
        }
      }
      window.__OfficeGraph__?.refresh(); // 🔄 мгновенная перерисовка графа
    }
  } catch (err) {
    console.warn("Не удалось обновить статусы перед выполнением:", err);
  }

  // === 🧠 2. Выполняем реальный запрос на сервер ===
  try {
    const res = await fetch("/assign_task_folder", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ folder, task }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Ошибка выполнения");

    // === 🧩 3. Показываем результаты выполнения ===
    let html = `<h4>📊 Результаты выполнения:</h4><ul style="list-style:none; padding-left:0;">`;
    for (const { agent, result } of data.results) {
      html += `
        <li style="margin:6px 0; padding:6px; border-bottom:1px solid rgba(255,255,255,0.1)">
          <b>${agent}</b>: ${result?.html || result || "—"}
        </li>`;
      // обновляем узлы графа
      window.__OfficeGraph__?.setAgentStatus(agent, "done", result?.html, task);
    }
    html += `</ul>`;
    folderResults.innerHTML = html;

    setSystemStatus("active", "🧠 Все агенты активны");
    window.__OfficeGraph__?.refresh();
  } catch (err) {
    console.error(err);
    folderResults.innerHTML = `<p class="error">❌ Ошибка: ${err.message}</p>`;
    setSystemStatus("error", "❌ Ошибка при выполнении задачи каталога");
  }
}

async function runBrainstormFromOffice(folder, topic) {
  const progress = document.getElementById("sp-brainstorm-progress");
  const output = document.getElementById("sp-brainstorm-output");

  progress.style.width = "0%";
  output.style.display = "block";
  output.textContent = `🧠 Мозговой штурм в каталоге "${folder}" — тема: "${topic}"\n\n`;
  setSystemStatus("busy", `🧠 Мозговой штурм: ${topic}`);

  const Graph = window.__OfficeGraph__?.Graph;
  const data = Graph?.graphData();
  const agents = data?.nodes.filter(n => n.type === "agent" && n.folder === folder) || [];
  const total = agents.length;

  if (total === 0) {
    output.textContent = "⚠️ В каталоге нет сотрудников для штурма.";
    setSystemStatus("error", "Нет агентов для штурма");
    return;
  }

  try {
    // 1️⃣ Все агенты начинают мигать
    agents.forEach(a => (a.status = "running"));
    Graph.graphData(data);

    let context = topic;
    const discussion = [];

    // 2️⃣ Передаём контекст агентам последовательно
    for (let i = 0; i < agents.length; i++) {
      const currentAgent = agents[i];
      const nextAgent = agents[i + 1];
      const percent = Math.round(((i + 1) / total) * 100);
      progress.style.width = `${percent}%`;

      // ⚙️ Отправляем запрос на локального агента
      const res = await fetch("/assign_task", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          slug: currentAgent.id,
          task: `Продолжи мозговой штурм по теме "${topic}". Контекст предыдущего участника:\n\n${context}`
        }),
      });

      const json = await res.json();
      const responseText = json.result?.html || json.result || json.error || "(нет ответа)";
      discussion.push({ agent: currentAgent.label, response: responseText });

      output.textContent += `👤 ${currentAgent.label}:\n${responseText}\n\n`;

      // 🔗 Добавляем линию передачи контекста
      if (nextAgent) {
        data.links.push({
          source: currentAgent.id,
          target: nextAgent.id,
          temp: true,
          transferProgress: 0
        });
        Graph.graphData(data);
        animateLinkTransfer(currentAgent.id, nextAgent.id);
      }

      // 🟢 Агент завершил — перестаёт мигать
      currentAgent.status = "done";
      Graph.nodeColor(colorByStatus); // 🔹 пересчитать цвета
      Graph.graphData(data);

      // контекст переходит следующему агенту
      context = responseText;

      await new Promise(r => setTimeout(r, 600));
    }

    // 3️⃣ После всех агентов — финальное обобщение
    const summaryAgent = agents[0]; // пусть первый делает сводку
    const res = await fetch("/assign_task", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        slug: summaryAgent.id,
        task: `Сформулируй общий вывод мозгового штурма по теме "${topic}", основываясь на следующем контексте:\n\n${context}`
      }),
    });

    const summaryJson = await res.json();
    const summaryText = summaryJson.result?.html || summaryJson.result || summaryJson.error || "(нет ответа)";
    output.textContent += "\n----------------------------------\n";
    output.textContent += `🧩 Итоговое мнение ассистента:\n${summaryText}\n`;

   // 4️⃣ Завершение штурма — очистка статусов и возврат цветов
    agents.forEach(a => (a.status = "done"));
    data.links = data.links.filter(l => !l.temp);
    Graph.nodeColor(colorByStatus);
    Graph.graphData(data);

    // через небольшую паузу (0.5 сек), вернуть цвета
    setTimeout(() => {
      agents.forEach(a => {
        a.status = null; // сбрасываем статус, возвращается baseColor
      });
      Graph.graphData(data);
    }, 1000);

    // 5️⃣ Кнопка “Посмотреть результаты”
    const link = document.createElement("a");
    link.href = "#brainstorm-results-block";
    link.textContent = "📊 Посмотреть результаты";
    link.style.display = "block";
    link.style.marginTop = "12px";
    link.style.cursor = "pointer";
    link.onclick = (e) => {
      e.preventDefault();
      showBrainstormResults(summaryText, discussion);
    };
    output.appendChild(link);

  } catch (err) {
    console.error("Ошибка мозгового штурма:", err);
    output.textContent = `❌ Ошибка: ${err.message}`;
    progress.style.background = "#ef476f";
    setSystemStatus("error", "❌ Ошибка мозгового штурма");
  }
}

function animateLinkTransfer(sourceId, targetId) {
  const Graph = window.__OfficeGraph__?.Graph;
  if (!Graph) return;
  const data = Graph.graphData();

  const link = data.links.find(l => l.source === sourceId && l.target === targetId && l.temp);
  if (!link) return;

  let startTime = Date.now();

  function update() {
    const elapsed = Date.now() - startTime;
    link.transferProgress = Math.min(elapsed / 700, 1); // 0 → 1 за 0.7 сек
    Graph.graphData(data);

    if (link.transferProgress < 1) {
      requestAnimationFrame(update);
    } else {
      // убираем линию после завершения
      setTimeout(() => {
        data.links = data.links.filter(l => l !== link);
        Graph.graphData(data);
      }, 300);
    }
  }

  update();
}


function pulseBrainstormNetwork(folder) {
  const Graph = window.__OfficeGraph__?.Graph;
  if (!Graph) return null;
  const data = Graph.graphData();

  const agents = data.nodes.filter(n => n.type === "agent" && n.folder === folder);
  if (agents.length < 2) return null;

  // создаём “волну” — повторяющиеся связи каждые 400 мс
  const intervalId = setInterval(() => {
    const a1 = agents[Math.floor(Math.random() * agents.length)];
    const a2 = agents[Math.floor(Math.random() * agents.length)];
    if (a1.id === a2.id) return;

    // добавляем временную связь
    data.links.push({ source: a1.id, target: a2.id, temp: true });
    Graph.graphData(data);

    // через 300 мс удаляем её
    setTimeout(() => {
      data.links = data.links.filter(l => !l.temp);
      Graph.graphData(data);
    }, 300);
  }, 400);

  return intervalId; // чтобы можно было остановить
}



// === Перманентное обновление графа для анимации ===
setInterval(() => {
  const Graph = window.__OfficeGraph__?.Graph;
  if (Graph) Graph.graphData(Graph.graphData());
}, 250);

function showBrainstormResults(summary, discussion) {
  let resultsBlock = document.getElementById("brainstorm-results-block");

  if (!resultsBlock) {
    resultsBlock = document.createElement("section");
    resultsBlock.id = "brainstorm-results-block";
    resultsBlock.className = "panel";
    resultsBlock.style.marginTop = "40px";
    resultsBlock.innerHTML = `
      <h2>🧠 Результаты мозгового штурма</h2>
      <div id="brainstorm-discussion"></div>
      <div id="brainstorm-summary" style="margin-top:15px; font-weight:500;"></div>
    `;
    document.body.appendChild(resultsBlock);
  }

  const discEl = document.getElementById("brainstorm-discussion");
  const sumEl = document.getElementById("brainstorm-summary");

    // === отрисовка диалога ===
  discEl.classList.add("markdown-body");
  discEl.innerHTML = discussion
    .map(d => `<div class="agent-block"><p><b>${d.agent}</b>:</p><div>${marked.parse(d.response)}</div></div>`)
    .join("");

  // === отрисовка финального вывода ===
  sumEl.classList.add("markdown-body");
  sumEl.innerHTML = marked.parse(summary || "_(нет данных)_");


  // плавная прокрутка к блоку
  resultsBlock.scrollIntoView({ behavior: "smooth" });
}

  function showAgentResultBlock(agentName, resultMarkdown) {
  let block = document.getElementById("agent-results-block");

  if (!block) {
    block = document.createElement("section");
    block.id = "agent-results-block";
    block.className = "panel";
    block.style.marginTop = "40px";
    block.innerHTML = `
      <h2>📋 Результат агента</h2>
      <div id="agent-results-content" class="markdown-body"></div>
    `;
    document.body.appendChild(block);
  }

  const content = document.getElementById("agent-results-content");
  content.innerHTML = `
    <h3>${agentName}</h3>
    ${marked.parse(resultMarkdown)}
  `;

  // плавная прокрутка к блоку
  block.scrollIntoView({ behavior: "smooth" });
}



// Инициализация страницы офиса
// === 🧩 Граф: каталог в центре и сотрудники-гексагоны ===
async function loadOfficeGraph() {
  const el = document.getElementById("office-graph");
  if (!el) return;

  setSystemStatus("busy", "⚙️ Загружается виртуальный офис...");

  // Получаем каталоги и агентов
  const foldersRes = await fetch("/folders");
  const folders = foldersRes.ok ? await foldersRes.json() : ["root"];
  const agents = [];

  for (const folder of folders) {
    const res = await fetch(`/folder/${folder}`);
    if (res.ok) {
      const list = await res.json();
      for (const a of list) {
        a.folder = folder;
        agents.push(a);
      }
    }
  }

  const nodes = [];
  const links = [];

  for (const f of folders) {
    nodes.push({ id: `folder:${f}`, type: "folder", label: f });
  }

  for (const a of agents) {
    nodes.push({
      id: a.slug,
      type: "agent",
      label: a.name,
      folder: a.folder,
      status: a.status || "done",
    });
    links.push({ source: a.slug, target: `folder:${a.folder}` });
  }

  const data = buildGraphData(agents);


  const Graph = ForceGraph()(el)
  .width(el.clientWidth)
  .height(600)
  .graphData(data)
  .nodeId("id")
  .nodeRelSize(8)
  .nodeVal(n => (n.type === "folder" ? 16 : 8))
  .nodeColor(colorByStatus)
  .nodeLabel(n => n.label)
  .linkColor(() => "rgba(100,200,255,0.2)")
  .linkDirectionalParticles(0)
  .linkCanvasObject((link, ctx, globalScale) => {
    const progress = link.transferProgress || 0;
    const src = link.source;
    const tgt = link.target;

    if (!src || !tgt) return;

    const x1 = src.x;
    const y1 = src.y;
    const x2 = tgt.x;
    const y2 = tgt.y;

    // основная линия
    ctx.strokeStyle = "rgba(100,200,255,0.15)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    // === волна передачи контекста ===
    if (progress > 0 && progress < 1) {
      const cx = x1 + (x2 - x1) * progress;
      const cy = y1 + (y2 - y1) * progress;
      const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, 8);
      gradient.addColorStop(0, "rgba(0,200,255,0.9)");
      gradient.addColorStop(1, "rgba(0,200,255,0)");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(cx, cy, 8, 0, 2 * Math.PI);
      ctx.fill();
    }
  })

  .d3Force("charge", d3.forceManyBody().strength(-200))
  .d3Force("center", null)
  .cooldownTicks(100)
  .onEngineStop(() => Graph.zoomToFit(400))
  .onNodeClick(n => onGraphNodeClick(n))
  .nodeCanvasObject((node, ctx, globalScale) => {
      const label = node.label;
      const fontSize = 10 / globalScale;
      const size = node.type === "folder" ?  34 : 16; //Размер каталога

      let color = "#00b4d8";
      let iconType = "folder";

      if (node.type === "agent") {
        const style = getAgentStyle(node);
        color = style.color;
        iconType = style.icon;
      }
      
      // Плавное изменение цвета через линейную интерполяцию
      // === Плавный переход цвета ===
      const startColor = node._colorTransition || node.baseColor || "#9ba9bb";
      const targetColor = color || "#06d6a0";

      node._colorTransition = lerpColor(startColor, targetColor, 0.15);
      ctx.strokeStyle = node._colorTransition;
      ctx.fillStyle = (node._colorTransition || "#9ba9bb") + "33";

      function lerpColor(a, b, amount) {
        // если нет одного из цветов — возвращаем второй
        if (!a) return b || "#06d6a0";
        if (!b) return a || "#06d6a0";

        // если пришли не HEX цвета — тоже возвращаем второй
        if (!a.startsWith("#") || !b.startsWith("#")) return b;

        const ah = parseInt(a.replace("#", ""), 16);
        const ar = ah >> 16, ag = (ah >> 8) & 0xff, ab = ah & 0xff;
        const bh = parseInt(b.replace("#", ""), 16);
        const br = bh >> 16, bg = (bh >> 8) & 0xff, bb = bh & 0xff;

        const rr = Math.round(ar + amount * (br - ar));
        const rg = Math.round(ag + amount * (bg - ag));
        const rb = Math.round(ab + amount * (bb - ab));

        return (
          "#" +
          (1 << 24 | (rr << 16) | (rg << 8) | rb)
            .toString(16)
            .slice(1)
        );
      }


      // === Шестиугольник ===
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const angle = Math.PI / 3 * i + Math.PI / 6;
        const px = node.x + size * Math.cos(angle);
        const py = node.y + size * Math.sin(angle);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      ctx.fillStyle = color + "33";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // === Иконка ===
      ctx.save();
      ctx.lineWidth = 1.6;
      ctx.strokeStyle = "#e0f7ff";
      ctx.fillStyle = "#e0f7ff";

      if (node.type === "folder") {
        // 👥 — группа / отдел
        ctx.beginPath();
        ctx.arc(node.x - 4, node.y - 2, 3, 0, 2 * Math.PI);
        ctx.arc(node.x + 4, node.y - 2, 3, 0, 2 * Math.PI);
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(node.x - 8, node.y + 4);
        ctx.lineTo(node.x + 8, node.y + 4);
        ctx.stroke();
      } else {
        // 👨‍💻 / 🎨 / 🧠 / ⚙️ — по роли
        switch (iconType) {
          case "copywriter": // 👨‍💻 — ноутбук / tech
            ctx.beginPath();
            ctx.rect(node.x - 6, node.y, 12, 6);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(node.x - 5, node.y - 2);
            ctx.lineTo(node.x, node.y - 6);
            ctx.lineTo(node.x + 5, node.y - 2);
            ctx.stroke();
            break;

          case "designer": // 🎨 — палитра
            ctx.beginPath();
            ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI);
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(node.x - 3, node.y - 2, 1, 0, 2 * Math.PI);
            ctx.arc(node.x + 2, node.y - 3, 1, 0, 2 * Math.PI);
            ctx.arc(node.x + 3, node.y + 2, 1, 0, 2 * Math.PI);
            ctx.arc(node.x - 2, node.y + 3, 1, 0, 2 * Math.PI);
            ctx.fill();
            break;

          case "analyst": // 🧠 — мозг
            ctx.beginPath();
            ctx.arc(node.x - 3, node.y - 1, 3, 0, Math.PI * 2);
            ctx.arc(node.x + 3, node.y + 1, 3, 0, Math.PI * 2);
            ctx.stroke();
            break;

          case "manager": // ⚙️ — шестерёнка
            for (let i = 0; i < 8; i++) {
              const a = (i * Math.PI) / 4;
              const r1 = 3.5, r2 = 5.5;
              ctx.moveTo(node.x + r1 * Math.cos(a), node.y + r1 * Math.sin(a));
              ctx.lineTo(node.x + r2 * Math.cos(a), node.y + r2 * Math.sin(a));
            }
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(node.x, node.y, 2.2, 0, 2 * Math.PI);
            ctx.fill();
            break;

          default: // 👤 базовый силуэт
            ctx.beginPath();
            ctx.arc(node.x, node.y - 5, 3, 0, 2 * Math.PI);
            ctx.fill();
            ctx.beginPath();
            ctx.moveTo(node.x - 5, node.y + 4);
            ctx.quadraticCurveTo(node.x, node.y + 8, node.x + 5, node.y + 4);
            ctx.stroke();
            break;
        }
      }
      ctx.restore();

      // === Подсветка выбранного узла ===
      if (window.__OfficeGraph__?.selectedNodeId === node.id) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, size + 6, 0, 2 * Math.PI);
        ctx.fillStyle = "rgba(0,180,255,0.15)";
        ctx.fill();
        ctx.shadowColor = "#00b4ff";
        ctx.shadowBlur = 20;
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#00b4ff";
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      // === Мягкое мигание для выполняющих задачу ===
      if (node.status === "running") {
        const t = (Date.now() - (node._pulsePhase || 0)) / 250;
        const pulse = 0.6 + 0.4 * Math.sin(t);
        ctx.beginPath();
        ctx.arc(node.x, node.y, size + 6 + 4 * pulse, 0, 2 * Math.PI);
        ctx.fillStyle = `rgba(0,180,255,${0.3 + 0.3 * pulse})`;
        ctx.fill();
      }


      // === Подпись ===
      ctx.font = `${fontSize}px Inter`;
      ctx.textAlign = "center";
      ctx.fillStyle = "#9ba9bb";
      ctx.fillText(label, node.x, node.y + size + 12);
    })
    window.__OfficeGraph__ = {
      Graph,
      selectedNodeId: null,
      setAgentStatus(slug, status, resultHtml, taskText) {
        const data = Graph.graphData();
        const node = data.nodes.find(n => n.id === slug);
        if (!node) return;

        node.status = status;
        if (taskText || resultHtml) {
          node.last_task = node.last_task || {};
          if (taskText) node.last_task.task = taskText;
          if (resultHtml) node.last_task.result = { html: resultHtml };
        }

        // 🔄 безопасная перерисовка
        Graph.graphData(Graph.graphData());
      },

      // 👇 безопасный хелпер для ручного обновления графа
      refresh() {
        Graph.graphData(Graph.graphData());
      }
    };


  setSystemStatus("active", "🧠 Все агенты активны");

  window.addEventListener("resize", () => {
    Graph.width(el.clientWidth);
  });

  // Управление физикой
  Graph.d3Force('charge').strength(-50);        // сильнее отталкивание
  Graph.d3Force('link').distance(link => {       // длина связи
    const src = link.source;
    return src.type === 'folder' ? 100 : 90;    // папки дальше от сотрудников
  });
}


function getAgentStyle(agent) {
  // Если статус установлен — приоритет у него
  if (agent.status === "running" || agent.status === "done" || agent.status === "error") {
    return { color: colorByStatus(agent), icon: agent.icon || "generic" };
  }

  // Если есть сохранённый базовый цвет — используем его
  if (agent.baseColor) {
    return { color: agent.baseColor, icon: agent.icon || "generic" };
  }

  // Если это первый запуск — определяем базовый цвет по роли
  let color = "#9ba9bb";
  let icon = "generic";

  switch (agent.id) {
    case "copywriter": color = "#00e0ff"; icon = "copywriter"; break;
    case "designer":   color = "#ff80ed"; icon = "designer"; break;
    case "analyst":    color = "#ffd166"; icon = "analyst"; break;
    case "manager":    color = "#06d6a0"; icon = "manager"; break;
    case "strategist": color = "#8b80ff"; icon = "strategist"; break;
    default:           color = "#9ba9bb"; icon = "generic"; break;
  }

  // Сохраняем, чтобы потом восстановить
  agent.baseColor = color;
  agent.icon = icon;

  return { color, icon };
}



setInterval(() => {
  const Graph = window.__OfficeGraph__?.Graph;
  if (Graph) Graph.graphData(Graph.graphData());
}, 120);

document.addEventListener("DOMContentLoaded", loadOfficeGraph);
document.addEventListener("DOMContentLoaded", refreshFolderSelect);
document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) lucide.createIcons();
  AIManager.init();
  refreshFolderSelect();
  loadOfficeGraph();
});
// ============= END ForceGraph =============

// Совместимость со старой разметкой (inline onclick)
window.AIManager   = AIManager;
window.toggleFolder = AIManager.toggleFolder;
window.deleteFolder = AIManager.deleteFolder;
window.assignTask   = AIManager.assignTask;
window.deleteAgent  = AIManager.deleteAgent;
window.assignTaskToFolder = AIManager.assignTaskToFolder;
window.setSystemStatus = AIManager.setSystemStatus;
