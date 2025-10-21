// ========================================================================
// 🧭 9. Отрисовка ForceGraph — интерактивный виртуальный офис
// ========================================================================
// Создаёт граф: каталоги (шестиугольники) и сотрудники (узлы)
// Поддерживает:
// - визуальное мигание во время задач
// - подсветку выбранного узла
// - плавную интерполяцию цвета при изменении статуса
// ========================================================================

async function loadOfficeGraph() {
  const el = document.getElementById("office-graph");
  if (!el) return;

  setSystemStatus("busy", "⚙️ Загружается виртуальный офис...");

  // === Текущий выбранный узел (агент или каталог)
  let currentNode = null;


  // Загружаем каталоги и сотрудников
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

  const data = buildGraphData(agents);

  // Создаём ForceGraph
  const Graph = ForceGraph()(el)
    .width(el.clientWidth)
    .height(740)
    .graphData(data)
    .nodeId("id")
    .nodeRelSize(8)
    .nodeVal(n => (n.type === "folder" ? 16 : 8))
    .nodeColor(colorByStatus)
    .nodeLabel(n => n.label)
    .linkColor(() => "rgba(100,200,255,0.2)")
    .linkDirectionalParticles(0)

    // 💫 Линия передачи контекста (анимация при штурме)
    .linkCanvasObject((link, ctx) => {
      const progress = link.transferProgress || 0;
      const src = link.source;
      const tgt = link.target;
      if (!src || !tgt) return;

      const x1 = src.x, y1 = src.y, x2 = tgt.x, y2 = tgt.y;

      // Основная линия
      ctx.strokeStyle = "rgba(100,200,255,0.15)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();

      // Волна передачи
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

    // ⚙️ Настройки физических сил графа
    .d3Force("charge", d3.forceManyBody().strength(-200))
    .d3Force("center", null)
    .cooldownTicks(100)
    .onEngineStop(() => Graph.zoomToFit(400))

    // 🖱️ Клик по узлу → заполнение боковой панели
    .onNodeClick(n => onGraphNodeClick(n))

    // 🎨 Отрисовка узлов (иконки, подсветка, анимация)
    .nodeCanvasObject((node, ctx, globalScale) => {
      const label = node.label;
      const fontSize = 10 / globalScale;
      const size = node.type === "folder" ? 34 : 16;

      let { color, icon } = getAgentStyle(node);

      // Плавный переход цвета (интерполяция)
      const startColor = node._colorTransition || node.baseColor || "#9ba9bb";
      const targetColor = color || "#06d6a0";
      node._colorTransition = lerpColor(startColor, targetColor, 0.15);
      ctx.strokeStyle = node._colorTransition;
      ctx.fillStyle = (node._colorTransition || "#9ba9bb") + "33";

      // === Функция плавного перехода цвета ===
      function lerpColor(a, b, amount) {
        if (!a) return b;
        if (!b) return a;
        if (!a.startsWith("#") || !b.startsWith("#")) return b;

        const ah = parseInt(a.replace("#", ""), 16);
        const bh = parseInt(b.replace("#", ""), 16);
        const ar = ah >> 16, ag = (ah >> 8) & 0xff, ab = ah & 0xff;
        const br = bh >> 16, bg = (bh >> 8) & 0xff, bb = bh & 0xff;
        const rr = Math.round(ar + amount * (br - ar));
        const rg = Math.round(ag + amount * (bg - ag));
        const rb = Math.round(ab + amount * (bb - ab));
        return "#" + ((1 << 24) + (rr << 16) + (rg << 8) + rb).toString(16).slice(1);
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

      // === Иконки: визуальные символы ролей ===
      ctx.save();
      ctx.lineWidth = 1.6;
      ctx.strokeStyle = "#e0f7ff";
      ctx.fillStyle = "#e0f7ff";

      if (node.type === "folder") {
        // 👥 — символ отдела
        ctx.beginPath();
        ctx.arc(node.x - 4, node.y - 2, 3, 0, 2 * Math.PI);
        ctx.arc(node.x + 4, node.y - 2, 3, 0, 2 * Math.PI);
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(node.x - 8, node.y + 4);
        ctx.lineTo(node.x + 8, node.y + 4);
        ctx.stroke();
      } else {
        // 👨‍💻 / 🎨 / 🧠 / ⚙️ — в зависимости от типа
        drawAgentIcon(icon, node, ctx);
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

      // === Мягкое мигание (при выполнении задачи) ===
      if (node.status === "running") {
        const t = (Date.now() / 250);
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
    });

    

  // 🔗 Регистрируем глобальный объект для обновлений
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
      Graph.graphData(Graph.graphData()); // безопасная перерисовка
    },
    refresh() { Graph.graphData(Graph.graphData()); }
  };

    // вызываем после создания Graph
  disableForceGraphAutoZoom(window.__OfficeGraph__?.Graph);

  setSystemStatus("active", "🧠 Все агенты активны");

  // Автоматическая подстройка ширины
  window.addEventListener("resize", () => Graph.width(el.clientWidth));

  // Настройки расстояний
  Graph.d3Force('charge').strength(-50);
  Graph.d3Force('link').distance(link => link.source.type === 'folder' ? 100 : 90);
}


// ------------------------------------------------------------------------
// 🎨 10. Определение цвета и иконки агента
// ------------------------------------------------------------------------
function getAgentStyle(agent) {
  // Приоритет текущего статуса
  if (["running", "done", "error"].includes(agent.status)) {
    return { color: colorByStatus(agent), icon: agent.icon || "generic" };
  }

  // Если базовый цвет сохранён
  if (agent.baseColor) {
    return { color: agent.baseColor, icon: agent.icon || "generic" };
  }

  // Назначаем цвет по роли
  let color = "#9ba9bb", icon = "generic";
  switch (agent.id) {
    case "copywriter": color = "#00e0ff"; icon = "copywriter"; break;
    case "designer":   color = "#ff80ed"; icon = "designer"; break;
    case "analyst":    color = "#ffd166"; icon = "analyst"; break;
    case "manager":    color = "#06d6a0"; icon = "manager"; break;
    case "strategist": color = "#8b80ff"; icon = "strategist"; break;
  }
  agent.baseColor = color;
  agent.icon = icon;
  return { color, icon };
}

// === 🧠 Завершение мозгового штурма: показ результатов и возврат цветов ===
async function finalizeBrainstorm(Graph, agents, summaryText, discussion) {
  try {
    // 🟢 Все агенты завершают работу (становятся done)
    agents.forEach(a => (a.status = "done"));
    Graph.nodeColor(colorByStatus);
    Graph.graphData(Graph.graphData());

    // через небольшую паузу возвращаем цвета к исходным
    setTimeout(() => {
      agents.forEach(a => (a.status = null)); // вернёт baseColor
      Graph.graphData(Graph.graphData());
    }, 1000);

    // === 📊 Добавляем ссылку "Показать результаты" в правую панель ===
    // const output = document.getElementById("sp-brainstorm-output");
    // if (output) {
    //   output.style.display = "block"; // <— добавь сюда
    //   const link = document.createElement("a");
    //   link.href = "#brainstorm-results-block";
    //   link.textContent = "📊 Показать результаты";
    //   link.className = "show-result-link";
    //   link.style.display = "block";
    //   link.style.marginTop = "12px";
    //   link.style.cursor = "pointer";
    //   link.onclick = (e) => {
    //     e.preventDefault();
    //     showBrainstormResults(summaryText, discussion);
    //   };
    //   output.appendChild(link);
    // }

    setSystemStatus("active", "🧠 Все агенты активны");
  } catch (err) {
    console.error("Ошибка финализации штурма:", err);
  }
}

// === 📋 Отрисовка блока с результатами мозгового штурма ===
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


// ------------------------------------------------------------------------
// 🧱 11. Примитивы отрисовки и обновления графа
// ------------------------------------------------------------------------
function drawAgentIcon(iconType, node, ctx) {
  switch (iconType) {
    case "copywriter": // 👨‍💻 ноутбук
      ctx.beginPath();
      ctx.rect(node.x - 6, node.y, 12, 6);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(node.x - 5, node.y - 2);
      ctx.lineTo(node.x, node.y - 6);
      ctx.lineTo(node.x + 5, node.y - 2);
      ctx.stroke();
      break;
    case "designer": // 🎨 палитра
      ctx.beginPath();
      ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI);
      ctx.stroke();
      ctx.beginPath();
      [ [-3,-2], [2,-3], [3,2], [-2,3] ].forEach(([dx,dy]) => {
        ctx.arc(node.x + dx, node.y + dy, 1, 0, 2 * Math.PI);
      });
      ctx.fill();
      break;
    case "analyst": // 🧠 мозг
      ctx.beginPath();
      ctx.arc(node.x - 3, node.y - 1, 3, 0, Math.PI * 2);
      ctx.arc(node.x + 3, node.y + 1, 3, 0, Math.PI * 2);
      ctx.stroke();
      break;
    case "manager": // ⚙️ шестерёнка
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

// === 🧠 Отправка задачи из правой панели конкретному агенту ===
async function assignTaskFromOffice(slug, task) {
  const statusBlock = document.querySelector("#sp-meta");
  const resultBox = document.querySelector("#sp-last-result");

  setSystemStatus("busy", "⚙️ Выполняется задача...");
  if (statusBlock) statusBlock.innerHTML += `<div><b>⚙️ Выполняется...</b></div>`;
  if (resultBox) resultBox.innerHTML = `<div class="spinner"></div> Выполняется...`;

  try {
    // 🔹 Агент начинает выполнение (мигание)
    window.__OfficeGraph__?.setAgentStatus(slug, "running");
    window.__OfficeGraph__?.refresh();

    const res = await fetch("/assign_task", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ slug, task }),
    });

    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Ошибка выполнения");

    // ✅ Результат получен — обновляем граф и правую панель
    window.__OfficeGraph__?.setAgentStatus(slug, "done", data.result?.html, task);
    window.__OfficeGraph__?.refresh();

    if (statusBlock) {
      statusBlock.innerHTML = `
        <div>Тип: <b>Сотрудник</b></div>
        <div>Каталог: <b>${currentNode?.folder || "—"}</b></div>
        <div>Статус: <b>✅ Готово</b></div>
      `;
    }

    if (resultBox) {
      resultBox.innerHTML = data.result?.html || data.result || "—";
      resultBox.scrollTop = resultBox.scrollHeight;
    }

    // 🔗 Добавляем ссылку "Показать результат"
    const showLink = document.getElementById("sp-show-result");
    if (showLink) {
      showLink.style.display = "inline-block";
      showLink.textContent = "📊 Показать результат";
      showLink.onclick = (e) => {
        e.preventDefault();
        showAgentResultBlock(slug, data.result?.html || data.result || "—");
      };
    }

    setSystemStatus("active", "🧠 Все агенты активны");
  } catch (err) {
    console.error(err);
    window.__OfficeGraph__?.setAgentStatus(slug, "error");
    window.__OfficeGraph__?.refresh();

    if (resultBox)
      resultBox.innerHTML = `<p class="error">❌ Ошибка: ${err.message}</p>`;
    
    setSystemStatus("error", "❌ Ошибка при выполнении задачи");
  }
}


// ========================================================================
// 🧠 Отображение данных узла в правой панели
// ========================================================================
function fillSidepanel(node) {
  currentNode = node; // сохраняем текущий выбранный узел для других операций
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

  const brainstormBox = document.getElementById("sp-brainstorm");

  if (node.type === "agent") {
    // ==== Одиночный сотрудник ====
    console.log('node',node)
    const t = node.last_task?.task || "—";
    const r = node.last_task?.result?.html || node.last_task?.result || "—";
    last.style.display = "block";
    lastRes.style.display = "block";
    brainstormBox.style.display = "none";
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
    // === показать мозговой штурм только для каталогов ===
    console.log('node.type',node.type,brainstormBox)
    brainstormBox.style.display = "flex";
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

// === 📋 Отправка задачи из правой панели ===
// === Выполнение задачи одним агентом ===
async function assignTaskFromOffice(slug, task) {
  const resultBox = document.querySelector("#sp-last-result");
  setSystemStatus("busy", "⚙️ Выполняется задача...");
  if (resultBox) resultBox.innerHTML = `<div class="spinner"></div> Выполняется...`;

  const Graph = window.__OfficeGraph__?.Graph;
  const data = Graph?.graphData();
  const node = data?.nodes.find(n => n.id === slug);

  try {
    // 🟡 Устанавливаем статус "running" и включаем пульсацию
    if (node) node.status = "running";
    Graph?.graphData(data);

    // 🔁 Эффект мигания, пока агент работает
    const pulseIntervalId = setInterval(() => {
      const n = data?.nodes.find(n => n.id === slug && n.status === "running");
      if (!n) return; // если статус уже снят, ничего не делаем
      Graph.graphData(data);
      setTimeout(() => Graph.graphData(data), 300);
    }, 400);

    // Отправляем задачу агенту
    const res = await fetch("/assign_task", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ slug, task }),
    });
    const dataRes = await res.json();
    if (!dataRes.ok) throw new Error(dataRes.error || "Ошибка выполнения");

    // 🟢 Останавливаем пульсацию и ставим статус "done"
    clearInterval(pulseIntervalId);
    if (node) node.status = "done";
    Graph.graphData(data);

    // Показываем результат
    if (resultBox) {
      resultBox.innerHTML = dataRes.result?.html || dataRes.result || "—";
      resultBox.scrollTop = resultBox.scrollHeight;
    }

    // Кнопка "Показать результат"
    const showLink = document.getElementById("sp-show-result");
    if (showLink) {
      showLink.style.display = "inline-block";
      showLink.textContent = "📊 Показать результат";
      showLink.onclick = (e) => {
        e.preventDefault();
        showAgentResultBlock(slug, dataRes.result?.html || dataRes.result || "—");
      };
    }

    // 🔄 Через секунду возвращаем цвет и убираем подсветку
    setTimeout(() => {
      if (node) node.status = null;
      if (window.__OfficeGraph__) window.__OfficeGraph__.selectedNodeId = null;
      Graph.graphData(data);
    }, 1000);

    setSystemStatus("active", "🧠 Все агенты активны");
  } catch (err) {
    console.error('[office] assignTaskFromOffice error:', err);
    // ❌ Ошибка — останавливаем пульсацию и красим в error
    if (node) node.status = "error";
    clearInterval(pulseIntervalId);
    Graph.graphData(data);
    if (resultBox) resultBox.innerHTML = `<p class="error">❌ Ошибка: ${err.message}</p>`;
    setSystemStatus("error", "❌ Ошибка при выполнении задачи");
  }
}



async function assignTaskToFolderFromOffice(folder, task) {
  const folderResults = document.getElementById("sp-folder-results");
  folderResults.style.display = "block";
  folderResults.innerHTML = `<div class="spinner"></div> ⚙️ Выполняется задача для каталога <b>${folder}</b>...`;

  setSystemStatus("busy", `⚙️ Задача выполняется для каталога "${folder}"`);

  const Graph = window.__OfficeGraph__?.Graph;
  const data = Graph?.graphData();
  if (!Graph || !data) return;

  // === 🟡 1. Мгновенная реакция — мигание всех агентов каталога ===
  const agents = data.nodes.filter(n => n.type === "agent" && n.folder === folder);
  agents.forEach(a => {
    a.status = "running";
    a._pulsePhase = Date.now();
  });
  Graph.graphData(data);

  // 🔄 Анимация: как в мозговом штурме (пульсирующая активность)
  const pulseIntervalId = setInterval(() => {
    const active = agents.filter(a => a.status === "running");
    if (active.length < 2) return;
    const a1 = active[Math.floor(Math.random() * active.length)];
    const a2 = active[Math.floor(Math.random() * active.length)];
    if (a1.id === a2.id) return;
    Graph.graphData(data);
    // удаляем через 300мс
    setTimeout(() => {
      Graph.graphData(data);
    }, 300);
  }, 400);

  try {
    // === 🧠 2. Отправка запроса на сервер ===
    const res = await fetch("/assign_task_folder", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ folder, task }),
    });
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || "Ошибка выполнения");

    // === 🧩 3. Вывод результатов ===
    let html = `<h4>📊 Результаты выполнения:</h4><ul style="list-style:none; padding-left:0;">`;
    const discussion = [];

    for (const { agent, result } of json.results) {
      html += `
      <li style="margin:6px 0; padding:6px; border-bottom:1px solid rgba(255,255,255,0.1)">
        <b>${agent}</b>:
        <div class="markdown-body">${marked.parse(result?.html || result || "—")}</div>
      </li>`;
      folderResults.classList.add("markdown-body");
      const node = data.nodes.find(n => n.id === agent);
      if (node) {
        node.status = "done";
        node.last_task = { task, result };
      }
      discussion.push({ agent, response: result?.html || result || "—" });
    }
    html += `</ul>`;

    // === 📊 Добавляем ссылку "Посмотреть результат" ===
    html += `
      <a href="#folder-results-block" id="folder-results-link"
         style="display:block; margin-top:10px; color:#00b4ff; cursor:pointer;">
        📊 Посмотреть результат
      </a>`;

    folderResults.innerHTML = html;
    setSystemStatus("active", "🧠 Все агенты активны");

    // 🟢 4. Останавливаем пульсацию, восстанавливаем цвета
    clearInterval(pulseIntervalId);
    agents.forEach(a => {
      a.status = "done";
      a._pulsePhase = null;
    });
    Graph.graphData(data);

    // через паузу возвращаем исходные цвета
    setTimeout(() => {
      agents.forEach(a => (a.status = null));
      Graph.graphData(data);
    }, 1000);

    // === 📎 Клик по ссылке — показать блок внизу ===
    document.getElementById("folder-results-link").onclick = (e) => {
      e.preventDefault();
      showFolderResultsBlock(folder, task, discussion);
    };

  } catch (err) {
    console.error(err);
    clearInterval(pulseIntervalId);
    folderResults.innerHTML = `<p class="error">❌ Ошибка: ${err.message}</p>`;
    setSystemStatus("error", "❌ Ошибка при выполнении задачи каталога");
  }
}


function showFolderResultsBlock(folder, task, discussion) {
  let block = document.getElementById("folder-results-block");

  if (!block) {
    block = document.createElement("section");
    block.id = "folder-results-block";
    block.className = "panel";
    block.style.marginTop = "40px";
    block.innerHTML = `
      <h2>📂 Результаты задачи для каталога "${folder}"</h2>
      <p class="text-dim">🧩 Задача: ${task}</p>
      <div id="folder-discussion" class="markdown-body"></div>
    `;
    document.body.appendChild(block);
  }

  const content = document.getElementById("folder-discussion");
  content.innerHTML = discussion
    .map(d => `<div class="agent-block"><p><b>${d.agent}</b>:</p><div>${marked.parse(d.response)}</div></div>`)
    .join("");

  block.scrollIntoView({ behavior: "smooth" });
}


// === 📋 Показ результатов отдельного агента ===
function showAgentResultBlock(agentName, resultMarkdown) {
  // проверяем, есть ли уже блок результатов
  let block = document.getElementById("agent-results-block");

  if (!block) {
    // если нет — создаём
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

  // добавляем содержимое
  const content = document.getElementById("agent-results-content");
  content.innerHTML = `
    <h3>${agentName}</h3>
    ${marked.parse(resultMarkdown || "_(нет данных)_")}
  `;

  // плавно скроллим к результатам
  block.scrollIntoView({ behavior: "smooth" });

  // анимация появления (fade-in)
  block.style.opacity = "0";
  block.style.transition = "opacity 0.8s ease";
  requestAnimationFrame(() => (block.style.opacity = "1"));
}

// ================== CAMERA PIN — фиксация положения камеры ==================
function getGraph() { return window.__OfficeGraph__?.Graph || null; }
function now() { return (typeof performance !== 'undefined' ? performance.now() : Date.now()); }

window.__CAMERA_PIN__ = {
  untilTs: 0,
  target: null,   // {x,y,z,dist}
  lastMs: 0
};

function isCameraPinned() {
  return window.__CAMERA_PIN__.untilTs > now();
}

function setControlsEnabled(enabled) {
  const G = getGraph();
  if (!G || typeof G.controls !== 'function') return;
  const ctr = G.controls();
  if (!ctr) return;
  ctr.enableZoom   = enabled;
  ctr.enablePan    = enabled;
  // вращение можно оставить включённым — на вкус:
  // ctr.enableRotate = enabled;
}

function reapplyCamera() {
  const G = getGraph();
  if (!G || !window.__CAMERA_PIN__.target) return;

  const t = window.__CAMERA_PIN__.target;
  const is3D = typeof G.cameraPosition === 'function';

  if (is3D) {
    // моментально ставим камеру туда же (duration = 0)
    G.cameraPosition(
      { x: t.x, y: t.y, z: t.z + t.dist },
      { x: t.x, y: t.y, z: t.z },
      0
    );
  } else {
    if (typeof G.centerAt === 'function')  G.centerAt(t.x, t.y, 0);
    if (typeof G.zoom === 'function')      G.zoom(t.zoom || 1.5, 0);
  }
}

function startCameraPin(durationMs = 2000) {
  window.__CAMERA_PIN__.untilTs = now() + durationMs;
  setControlsEnabled(false);
  // RAF-петля: пока пин активен, каждый кадр мягко возвращаем камеру
  if (!window.__CAMERA_PIN__.rafId) {
    const loop = () => {
      if (isCameraPinned()) {
        reapplyCamera();
        window.__CAMERA_PIN__.rafId = requestAnimationFrame(loop);
      } else {
        cancelAnimationFrame(window.__CAMERA_PIN__.rafId);
        window.__CAMERA_PIN__.rafId = null;
        setControlsEnabled(true);
      }
    };
    window.__CAMERA_PIN__.rafId = requestAnimationFrame(loop);
  }
}

// Патчим чувствительные методы: если пин активен — откатываем камеру обратно
(function patchGraphMethodsOnce(){
  if (window.__CAMERA_PIN__.patched) return;
  const G = getGraph();
  if (!G) return;

  const wrap = (methodName) => {
    if (typeof G[methodName] !== 'function') return;
    const orig = G[methodName].bind(G);
    G[methodName] = function(...args) {
      const ret = orig(...args);
      if (isCameraPinned()) {
        // после любого изменения графа возвращаем камеру
        Promise.resolve().then(reapplyCamera);
      }
      return ret;
    };
  };

  // graphData/zoomToFit/fitToScene/centerAt/zoom — на всякий случай
  ['graphData','zoomToFit','fitToScene','centerAt','zoom'].forEach(wrap);
  window.__CAMERA_PIN__.patched = true;
})();


// ========================================================================
// 🌍 Экспорт fillSidepanel для использования в core.js / глобально
// ========================================================================
window.fillSidepanel = fillSidepanel;


// ------------------------------------------------------------------------
// 🚀 12. Инициализация визуализации при загрузке
// ------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) lucide.createIcons();
  AIManager.init();
  refreshFolderSelect();
  loadOfficeGraph();
});


// ========================================================================
// 🧩 Совместимость для inline-обработчиков
// ========================================================================
window.AIManager = AIManager;
window.toggleFolder = AIManager.toggleFolder;
window.deleteAgent = AIManager.deleteAgent;
window.assignTask = AIManager.assignTask;
window.assignTaskToFolder = AIManager.assignTaskToFolder;
window.setSystemStatus = AIManager.setSystemStatus;
