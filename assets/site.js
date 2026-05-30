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
    <a class="brand brand-link" href="index.html" aria-label="Перейти на главную страницу">Ситковский А.М.</a>
    <nav class="nav">
      <a href="projects.html"><span class="ru">Проекты</span><span class="en">Projects</span></a>
      <a href="publications.html"><span class="ru">Статьи</span><span class="en">Articles</span></a>
      <a href="materials.html#books"><span class="ru">Книги</span><span class="en">Books</span></a>
      <a href="media.html"><span class="ru">Публикации</span><span class="en">Media</span></a>
      <a href="media.html#video"><span class="ru">Видео</span><span class="en">Video</span></a>
      <a href="materials.html#photos"><span class="ru">Фото</span><span class="en">Photos</span></a>
      <a href="diplomas.html"><span class="ru">Дипломы</span><span class="en">Diplomas</span></a>
      <a href="it.html"><span class="ru">ИТ-ресурсы</span><span class="en">IT resources</span></a>
      <a class="email-btn" href="mailto:omnistat@yandex.ru">omnistat@yandex.ru</a>
      <button class="lang-toggle" data-lang-toggle onclick="toggleLang()" aria-label="Switch language">EN</button>
    </nav>`;
}

function installFooter(){
  const footer = document.querySelector('.footer');
  if(!footer) return;
  footer.innerHTML = `
    <div class="footer-inner">
      <div>
        <div class="footer-title"><span class="ru">Персональный сайт Ситковского А.М.</span><span class="en">Personal website of Arseniy M. Sitkovskiy</span></div>
        <a class="footer-email" href="mailto:omnistat@yandex.ru">omnistat@yandex.ru</a>
      </div>
      <div class="social-links" aria-label="Social links">
        <a href="https://vk.com/arseniy24gamer" target="_blank" rel="noopener noreferrer" aria-label="VK"><span aria-hidden="true">VK</span></a>
        <a href="https://t.me/omnistat" target="_blank" rel="noopener noreferrer" aria-label="Telegram"><span aria-hidden="true">TG</span></a>
      </div>
    </div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  installHeader();
  installFooter();
  setLang(localStorage.getItem('lang') || 'ru');
});