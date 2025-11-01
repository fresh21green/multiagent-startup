// ========================================================================
// 🧠 BRAINSTORM MODULE — коллективная работа агентов
// ========================================================================

// === П÷╖═ п≈п╟п©я┐я│п╨ п╪п╬п╥пЁп╬п╡п╬пЁп╬ я┬я┌я┐я─п╪п╟ п╦п╥ п©п╟п╫п╣п╩п╦ ===
// === П÷╖═ п≈п╟п©я┐я│п╨ п╪п╬п╥пЁп╬п╡п╬пЁп╬ я┬я┌я┐я─п╪п╟ п╦п╥ п©п╟п╫п╣п╩п╦ ===
async function runBrainstormFromOffice(folder, topic) {
  const progress = document.getElementById("sp-brainstorm-progress");
  const output = document.getElementById("sp-brainstorm-output");

  if (!progress || !output) {
    console.warn("Б ═О╦▐ п╜п╩п╣п╪п╣п╫я┌я▀ п╪п╬п╥пЁп╬п╡п╬пЁп╬ я┬я┌я┐я─п╪п╟ п╫п╣ п╫п╟п╧п╢п╣п╫я▀.");
    return;
  }

  output.style.display = "block";
  output.classList.add("markdown-body");
  // Override header message to avoid mojibake and ensure scroll
  try {
    output.innerHTML = `Запуск <b>мозгового штурма</b> для папки "${folder}"<br>Тема: <i>${topic}</i><br><br>`;
    output.scrollTop = output.scrollHeight;
  } catch(_) {}
  output.innerHTML = `П÷╖═ <b>п°п╬п╥пЁп╬п╡п╬п╧ я┬я┌я┐я─п╪ п╡ п╨п╟я┌п╟п╩п╬пЁп╣ "${folder}"</b><br>п╒п╣п╪п╟: <i>${topic}</i><br><br>`;
  setSystemStatus("busy", `П÷╖═ п°п╬п╥пЁп╬п╡п╬п╧ я┬я┌я┐я─п╪: ${topic}`);

  const Graph = window.__OfficeGraph__?.Graph;
  const data = Graph?.graphData();
  const agents = data?.nodes.filter(n => n.type === "agent" && n.folder === folder) || [];
  const total = agents.length;

  if (total === 0) {
    try { output.innerHTML = 'Нет агентов в выбранной папке.'; output.scrollTop = output.scrollHeight; } catch(_) {}
    output.innerHTML = "Б ═О╦▐ п▓ п╨п╟я┌п╟п╩п╬пЁп╣ п╫п╣я┌ я│п╬я┌я─я┐п╢п╫п╦п╨п╬п╡ п╢п╩я▐ я┬я┌я┐я─п╪п╟.";
    setSystemStatus("error", "п²п╣я┌ п╟пЁп╣п╫я┌п╬п╡ п╢п╩я▐ я┬я┌я┐я─п╪п╟");
    return;
  }


  try {
    // === 🟡 1. Мгновенная реакция — мигание всех агентов каталога ===
    agents.forEach(a => {
      a.status = "running";
      a._pulsePhase = Date.now();
    });
    Graph.graphData(data);

    // 🔄 Пульсация активности
    const pulseIntervalId = setInterval(() => {
      const active = agents.filter(a => a.status === "running");
      if (active.length < 2) return;
      const a1 = active[Math.floor(Math.random() * active.length)];
      const a2 = active[Math.floor(Math.random() * active.length)];
      if (a1.id === a2.id) return;
      Graph.graphData(data);
      setTimeout(() => Graph.graphData(data), 300);
    }, 400);

    let context = topic;
    const discussion = [];

    // 2️⃣ Передаём контекст агентам последовательно
    for (let i = 0; i < agents.length; i++) {
      
      const currentAgent = agents[i];
      const nextAgent = agents[i + 1];
      const percent = Math.round(((i + 1) / total) * 100);
      if (progress) progress.style.width = `${percent}%`;

      const res = await fetch("/assign_task", {
        method: "POST",
        headers: { ...authHeaders(), Accept: "application/json" },
        body: new URLSearchParams({
          slug: currentAgent.id,
          task: `п÷я─п╬п╢п╬п╩п╤п╦ п╪п╬п╥пЁп╬п╡п╬п╧ я┬я┌я┐я─п╪ п©п╬ я┌п╣п╪п╣ "${topic}". п п╬п╫я┌п╣п╨я│я┌ п©я─п╣п╢я▀п╢я┐я┴п╣пЁп╬ я┐я┤п╟я│я┌п╫п╦п╨п╟:\n\n${context}`
        }),
      });

      const json = await res.json();
      const responseText = json.result?.html || json.result || json.error || "(нет ответа)";
      discussion.push({ agent: currentAgent.label, response: responseText });

      // === красивый вывод markdown с эффектом "печати" ===
      const block = document.createElement("div");
      block.className = "agent-block markdown-body";
      block.style.marginBottom = "16px";
      block.innerHTML = `<p><b>👤 ${currentAgent.label}</b></p><div class="typed-output"></div>`;
      output.appendChild(block);

      const typedContainer = block.querySelector(".typed-output");
      const parsedHTML = marked.parse(responseText);
      typeMarkdown(typedContainer, parsedHTML, 10);
      block.scrollIntoView({ behavior: "smooth" });

      if (nextAgent) {
        // 🔄 Анимация передачи контекста
        animateLinkTransfer(currentAgent.id, nextAgent.id,currentAgent.label,nextAgent.label);
      }
      else {
        setSystemStatus("busy", `🧠 ${currentAgent.label} завершает обсуждение...`);
      }

      currentAgent.status = "done";
      Graph.nodeColor(colorByStatus);
      Graph.graphData(data);

      context = responseText;
      await new Promise(r => setTimeout(r, 600));
    }

    // 🧩 Итоговый результат
    const summaryAgent = agents[0];
    const res = await fetch("/assign_task", {
      method: "POST",
      headers: { ...authHeaders(), Accept: "application/json" },
      body: new URLSearchParams({
        slug: summaryAgent.id,
        task: `Сделай общий вывод по теме "${topic}" на основе контекста:\n\n${context}`
      }),
    });
    const summaryJson = await res.json();
    const summaryText = summaryJson.result?.html || summaryJson.result || "(нет ответа)";

    output.innerHTML += `
      <hr>
      <div class="markdown-body">
        <h4>🧩 Итоговое мнение ассистента</h4>
        ${marked.parse(summaryText)}
      </div>
    `;

    // Добавляем кнопку “📊 Показать результаты”
    const link = document.createElement("a");
    link.href = "#brainstorm-results-block";
    link.textContent = "📊 Показать результаты";
    link.className = "show-results-link";
    link.onclick = (e) => {
      e.preventDefault();
      showBrainstormResults(summaryText, discussion);
    };
    output.appendChild(link);

    // 🟢 Остановка пульсации
    clearInterval(pulseIntervalId);
    agents.forEach(a => {
      a.status = "done";
      a._pulsePhase = null;
    });
    Graph.graphData(data);

    // Возвращаем исходные цвета и активируем авто-зум
    setTimeout(() => {
      agents.forEach(a => (a.status = null));
      Graph.graphData(data);
      enableAutoZoom();
    }, 1000);

    setSystemStatus("active", "🧠 Все агенты активны");
  } catch (err) {
    clearInterval(pulseIntervalId);
    console.error("Ошибка мозгового штурма:", err);
    output.innerHTML = `<p class="error">❌ Ошибка: ${err.message}</p>`;
    setSystemStatus("error", "❌ Ошибка мозгового штурма");
    enableAutoZoom(); // возвращаем даже при ошибке
  }
}


function typeMarkdown(container, html, speed = 15) {
  const temp = document.createElement("div");
  temp.innerHTML = html;
  const text = temp.textContent || temp.innerText || "";

  container.innerHTML = "";
  let i = 0;

  // Родительский блок с прокруткой
  const scrollParent = container.closest("#sp-brainstorm-output") || container.parentElement;

  const typing = setInterval(() => {
    if (i < text.length) {
      container.textContent = text.slice(0, i + 1);
      i++;

      // === Автоматическая прокрутка вниз ===
      if (scrollParent) {
        scrollParent.scrollTop = scrollParent.scrollHeight;
      }
    } else {
      clearInterval(typing);
      container.innerHTML = html;

      // Финальный скролл до самого низа
      if (scrollParent) {
        scrollParent.scrollTop = scrollParent.scrollHeight;
      }
    }
  }, speed);
}




// === Анимация передачи контекста ===
function animateLinkTransfer(sourceId, targetId,currentAgentLabel,nextAgentLabel) {
  const Graph = window.__OfficeGraph__?.Graph;
  if (!Graph) return;
  const data = Graph.graphData();

  const link = { source: sourceId, target: targetId, temp: true, transferProgress: 0 };
  data.links.push(link);
  Graph.graphData(data);

  let start = Date.now();
  const step = () => {
    link.transferProgress = Math.min((Date.now() - start) / 700, 1);
    Graph.graphData(data);
    // === обновляем статус в статус-баре ===
    setSystemStatus("busy", `🧠 Идёт мозговой штурм: ${currentAgentLabel} передал задачу ${nextAgentLabel}...`);
    if (link.transferProgress < 1) requestAnimationFrame(step);
    else setTimeout(() => {
      setSystemStatus("busy", `🧠 ${nextAgentLabel} решает задачу...`);
      data.links = data.links.filter(l => l !== link);
      Graph.graphData(data);
    }, 300);
  };
  step();
}

// === 🧩 Итоговое отображение результатов мозгового штурма ===
function finalizeBrainstorm(summary, discussion) {
  const output = document.getElementById("brainOut");
  const link = document.createElement("a");
  link.href = "#brainstorm-results-block";
  link.textContent = "📊 Показать результаты";
  link.className = "show-result-link";
  link.onclick = (e) => {
    e.preventDefault();
    showBrainstormResults(summary, discussion);
  };
  output.appendChild(link);
}

function showBrainstormResults(summary, discussion) {
  let resultsBlock = document.getElementById("brainstorm-results-block");
  if (!resultsBlock) {
    resultsBlock = document.createElement("section");
    resultsBlock.id = "brainstorm-results-block";
    resultsBlock.className = "panel";
    resultsBlock.style.marginTop = "40px";
    resultsBlock.innerHTML = `
      <h2>🧠 Результаты мозгового штурма</h2>
      <div id="brainstorm-discussion" class="markdown-body"></div>
      <div id="brainstorm-summary" class="markdown-body" style="margin-top:15px;"></div>`;
    document.body.appendChild(resultsBlock);
  }
  const discEl = document.getElementById("brainstorm-discussion");
  const sumEl = document.getElementById("brainstorm-summary");
  discEl.innerHTML = discussion.map(d => `<div><b>${d.agent}</b>: ${marked.parse(d.response)}</div>`).join("");
  sumEl.innerHTML = marked.parse(summary || "_(нет данных)_");
  resultsBlock.scrollIntoView({ behavior: "smooth" });
}

// 🎙️ Голосовой ввод для мозгового штурма
// 🎙️ Голосовой ввод для мозгового штурма с автозапуском
function initVoiceInput() {
  const btn = document.getElementById("voice-btn");
  const input = document.getElementById("sp-brainstorm-topic");
  const brainstormBtn = document.getElementById("sp-brainstorm-send");
  if (!btn || !input || !brainstormBtn) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    btn.disabled = true;
    btn.title = "Голосовой ввод не поддерживается этим браузером";
    btn.style.opacity = 0.5;
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "ru-RU";
  recognition.interimResults = true;
  recognition.continuous = false;

  let listening = false;
  let autoRunTimer = null;

  btn.addEventListener("click", () => {
    if (!listening) {
      recognition.start();
      listening = true;
      btn.textContent = "🎙️ Слушаю...";
      btn.classList.add("listening");
      btn.style.background = "#007bff";
      btn.style.color = "#fff";
    } else {
      recognition.stop();
    }
  });

  recognition.onresult = (event) => {
    const transcript = Array.from(event.results)
      .map((r) => r[0].transcript)
      .join("");
    input.value = transcript;

    // Если говорим — сбрасываем таймер автозапуска
    if (autoRunTimer) clearTimeout(autoRunTimer);
  };

  recognition.onend = () => {
    listening = false;
    btn.textContent = "🎤";
    btn.classList.remove("listening");
    btn.style.background = "#111";
    btn.style.color = "#ccc";

    // Автозапуск мозгового штурма через 1 секунду
    const topic = input.value.trim();
    if (topic) {
      autoRunTimer = setTimeout(() => {
        console.log("🎯 Автозапуск мозгового штурма:", topic);
        brainstormBtn.click(); // имитируем нажатие кнопки 🚀
      }, 1000);
    }
  };

  recognition.onerror = (e) => {
    console.error("Ошибка распознавания речи:", e);
    btn.textContent = "🎤";
    btn.classList.remove("listening");
    listening = false;
  };
}

async function centerOnFolder(folderId, ms = 1000) {
  const Graph = window.__OfficeGraph__?.Graph;
  if (!Graph) return;
  const data = Graph.graphData();

  // пробуем найти сам узел каталога
  let folderNode = data.nodes.find(n => n.id === folderId || n.slug === folderId);
  if (!folderNode) {
    console.warn("Каталог не найден в графе:", folderId);
    return;
  }

  // если координаты ещё не рассчитаны — подождём немного
  if (typeof folderNode.x !== "number" || typeof folderNode.y !== "number") {
    await new Promise(r => setTimeout(r, 300));
  }

  // определяем, 2D или 3D граф
  const is3D = typeof Graph.cameraPosition === "function";
  if (is3D) {
    const dist = 120;
    Graph.cameraPosition(
      { x: folderNode.x, y: folderNode.y, z: folderNode.z + dist },
      { x: folderNode.x, y: folderNode.y, z: folderNode.z },
      ms
    );
  } else {
    // 2D версия
    if (typeof Graph.centerAt === "function") {
      Graph.centerAt(folderNode.x, folderNode.y, ms);
    }
    if (typeof Graph.zoom === "function") {
      Graph.zoom(1.5, ms);
    }
  }
}

// Инициализация при загрузке страницы
document.addEventListener("DOMContentLoaded", initVoiceInput);

