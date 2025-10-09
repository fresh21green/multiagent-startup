async function assignTaskAll() {
  const task = document.getElementById('global-task').value;
  if (!task.trim()) return alert('Введите задачу');
  const btn = document.getElementById('assign-all-btn');
  btn.disabled = true;
  btn.textContent = 'Выполняется...';
  const allStatuses = document.querySelectorAll('.agent-status');
  allStatuses.forEach(status => {
    if (status) {
      status.innerHTML = "Статус: Выполняется...";
    }
  });

  const res = await fetch('/assign_task_all', {
    method: 'POST',
    body: new URLSearchParams({ task })
  });
  const data = await res.json();
  btn.disabled = false;
  btn.textContent = 'Поручить задачу сотрудникам';

  data.results.forEach(r => {
    const card = document.getElementById('result-' + r.agent);
    const statusBox = document.getElementById('status-' + r.agent);

    if (card) {
        statusBox.innerHTML = "Статус: Выполнено";
        card.classList.add("is-result");
        card.innerHTML = r.result?.result || r.error || 'Ошибка';
    }
  });
}

async function assignTask(slug) {
  const input = document.getElementById('task-' + slug);
  const btn = document.getElementById('btn-' + slug);
  const statusBox = document.getElementById('status-' + slug);
  statusBox.innerHTML = "Статус: Выполняется...";
  
  const resultBox = document.getElementById('result-' + slug);

  btn.disabled = true;
  btn.textContent = 'Выполняется...';

  const res = await fetch('/assign_task', {
    method: 'POST',
    body: new URLSearchParams({ slug, task: input.value })
  });

  const data = await res.json();
  console.log('data',data)

  btn.disabled = false;
  btn.textContent = 'Отправить задачу';
  console.log('resultBox',resultBox)
  
  if(data.result){
    statusBox.innerHTML = "Статус: Выполнено";
    resultBox.classList.add("is-result");
    resultBox.innerHTML = data.result.result; ;
  }
  else{
    statusBox.innerHTML = "Статус: Ошибка";
    resultBox.classList.add("is-result");
    resultBox.innerHTML = data.error
  }
  
}


