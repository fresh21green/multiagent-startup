function toggleTaskBox(folder) {
  const box = document.querySelector(`#task-box-${folder}`);
  box.classList.toggle('open');
  box.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function setTheme(name) {
  const link = document.getElementById('themeStylesheet');
  if (!link) return;
  link.href = `/static/themes/${name}.css`;
  localStorage.setItem('theme', name);
}

// При загрузке страницы применяем сохранённую тему
document.addEventListener('DOMContentLoaded', () => {
  const saved = localStorage.getItem('theme');
  if (saved) setTheme(saved);
});