function setLang(lang){
  const normalized = lang === 'en' ? 'en' : 'ru';
  document.body.classList.toggle('lang-en', normalized === 'en');
  document.documentElement.lang = normalized;
  localStorage.setItem('lang', normalized);
  document.querySelectorAll('[data-lang-toggle]').forEach(btn => { btn.textContent = normalized === 'en' ? 'RU' : 'EN'; });
}
function toggleLang(){ setLang(document.body.classList.contains('lang-en') ? 'ru' : 'en'); }
function installHeader(){
  const header = document.querySelector('[data-header]');
  if(!header) return;
  header.className = 'top';
  header.innerHTML = `
    <div class="brand">Ситковский А.М.</div>
    <nav class="nav">
      <a href="projects.html"><span class="ru">Проекты</span><span class="en">Projects</span></a>
      <a href="publications.html"><span class="ru">Статьи</span><span class="en">Articles</span></a>
      <a href="materials.html#books"><span class="ru">Книги</span><span class="en">Books</span></a>
      <a href="media.html"><span class="ru">Публикации</span><span class="en">Media</span></a>
      <a href="media.html#video"><span class="ru">Видео</span><span class="en">Video</span></a>
      <a href="materials.html#photos"><span class="ru">Фото</span><span class="en">Photos</span></a>
      <a href="materials.html#diplomas"><span class="ru">Дипломы</span><span class="en">Diplomas</span></a>
      <a href="maps.html"><span class="ru">Карты</span><span class="en">Maps</span></a>
      <a class="email-btn" href="mailto:omnistat@yandex.ru">omnistat@yandex.ru</a>
      <button class="lang-toggle" data-lang-toggle onclick="toggleLang()" aria-label="Switch language">EN</button>
    </nav>`;
}
document.addEventListener('DOMContentLoaded', () => { installHeader(); setLang(localStorage.getItem('lang') || 'ru'); });
