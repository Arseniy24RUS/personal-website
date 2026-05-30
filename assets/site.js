const SOCIAL_ICONS = {
  vk: "data:image/png;base64,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",
  telegram: "data:image/png;base64,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"
};

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
      <a href="materials.html#diplomas"><span class="ru">Дипломы</span><span class="en">Diplomas</span></a>
      <a href="maps.html"><span class="ru">Карты</span><span class="en">Maps</span></a>
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
        <a href="https://vk.com/arseniy24gamer" target="_blank" rel="noopener noreferrer" aria-label="VK">
          <img src="${SOCIAL_ICONS.vk}" alt="VK">
        </a>
        <a href="https://t.me/omnistat" target="_blank" rel="noopener noreferrer" aria-label="Telegram">
          <img src="${SOCIAL_ICONS.telegram}" alt="Telegram">
        </a>
      </div>
    </div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  installHeader();
  installFooter();
  setLang(localStorage.getItem('lang') || 'ru');
});