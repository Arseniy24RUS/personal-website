const PAGE_META = {
  'index.html': {
    ru: {
      title: 'Ситковский Арсений Михайлович — персональный сайт',
      description: 'Персональный сайт Арсения Михайловича Ситковского: демография, экономическая география, СМИ, проекты и научные идентификаторы.'
    },
    en: {
      title: 'Arseniy M. Sitkovskiy — personal website',
      description: 'Personal website of Arseniy M. Sitkovskiy: demography, economic geography, media, projects and research identifiers.'
    }
  },
  'projects.html': {
    ru: {title: 'Проекты — Ситковский А.М.', description: 'Научные и прикладные проекты Арсения Михайловича Ситковского.'},
    en: {title: 'Projects — Arseniy M. Sitkovskiy', description: 'Research and applied projects by Arseniy M. Sitkovskiy.'}
  },
  'publications.html': {
    ru: {title: 'Научные статьи — Ситковский А.М.', description: 'Список научных публикаций Арсения Михайловича Ситковского по данным eLibrary/РИНЦ, Scopus, WoS и справочника качества журналов.'},
    en: {title: 'Research articles — Arseniy M. Sitkovskiy', description: 'Research publications by Arseniy M. Sitkovskiy based on eLibrary/RSCI, Scopus, WoS and journal quality references.'}
  },
  'media.html': {
    ru: {title: 'СМИ — Ситковский А.М.', description: 'Материалы СМИ, публичные упоминания, интервью и аналитические публикации Арсения Михайловича Ситковского.'},
    en: {title: 'Media — Arseniy M. Sitkovskiy', description: 'Media articles, public mentions, interviews and analytical publications related to Arseniy M. Sitkovskiy.'}
  },
  'it.html': {
    ru: {title: 'Ресурсы — Ситковский А.М.', description: 'Интерактивные дашборды, карты, симуляторы и учебные веб-приложения Арсения Михайловича Ситковского.'},
    en: {title: 'Resources — Arseniy M. Sitkovskiy', description: 'Interactive dashboards, maps, simulators and educational web applications by Arseniy M. Sitkovskiy.'}
  },
  'diplomas.html': {
    ru: {title: 'Дипломы и сертификаты — Ситковский А.М.', description: 'Дипломы, сертификаты, благодарности и подтверждённые профессиональные достижения Арсения Михайловича Ситковского.'},
    en: {title: 'Diplomas and certificates — Arseniy M. Sitkovskiy', description: 'Diplomas, certificates, letters of appreciation and verified professional achievements of Arseniy M. Sitkovskiy.'}
  },
  'materials.html': {
    ru: {title: 'Материалы — Ситковский А.М.', description: 'Дополнительные материалы профессионального портфолио Арсения Михайловича Ситковского.'},
    en: {title: 'Materials — Arseniy M. Sitkovskiy', description: 'Additional materials from the professional portfolio of Arseniy M. Sitkovskiy.'}
  },
  'metrics.html': {
    ru: {title: 'Наукометрия — Ситковский А.М.', description: 'Наукометрические показатели и научные идентификаторы Арсения Михайловича Ситковского.'},
    en: {title: 'Research metrics — Arseniy M. Sitkovskiy', description: 'Research metrics and scholarly identifiers of Arseniy M. Sitkovskiy.'}
  },
  'admin.html': {
    ru: {title: 'Администрирование данных — Ситковский А.М.', description: 'Служебная страница контроля автоматизированных данных портфолио.'},
    en: {title: 'Data administration — Arseniy M. Sitkovskiy', description: 'Utility page for checking automated portfolio data.'}
  }
};

function pageKey(){
  const name = (location.pathname.split('/').pop() || 'index.html');
  return name || 'index.html';
}

function browserPreferredLang(){
  const langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || ''];
  return langs.some(lang => String(lang).toLowerCase().startsWith('ru')) ? 'ru' : 'en';
}

function preferredLang(){
  try{
    const saved = localStorage.getItem('lang');
    if(saved === 'ru' || saved === 'en') return saved;
  }catch(e){}
  return browserPreferredLang();
}

function installFavicon(){
  if(document.querySelector('link[rel~="icon"]')) return;
  const icon = document.createElement('link');
  icon.rel = 'icon';
  icon.type = 'image/svg+xml';
  icon.href = 'assets/favicon.svg';
  document.head.appendChild(icon);
}

function updatePageMeta(lang){
  const meta = (PAGE_META[pageKey()] || PAGE_META['index.html'] || {})[lang];
  if(!meta) return;
  if(meta.title) document.title = meta.title;
  const desc = document.querySelector('meta[name="description"]');
  if(desc && meta.description) desc.setAttribute('content', meta.description);
}

function setLang(lang){
  const normalized = lang === 'ru' ? 'ru' : 'en';
  document.documentElement.lang = normalized;
  document.documentElement.classList.toggle('lang-en', normalized === 'en');
  document.body.classList.toggle('lang-en', normalized === 'en');
  try{ localStorage.setItem('lang', normalized); }catch(e){}
  updatePageMeta(normalized);
  document.querySelectorAll('[data-lang-toggle]').forEach(btn => {
    btn.textContent = normalized === 'en' ? 'RU' : 'EN';
    btn.setAttribute('aria-label', normalized === 'en' ? 'Switch to Russian' : 'Переключить на английский');
  });
  window.dispatchEvent(new CustomEvent('site:languagechange', {detail: {lang: normalized}}));
}

function toggleLang(){ setLang((document.documentElement.classList.contains('lang-en') || document.body.classList.contains('lang-en')) ? 'ru' : 'en'); }

function installHeader(){
  const header = document.querySelector('[data-header]');
  if(!header) return;
  header.className = 'top';
  header.innerHTML = `
    <a class="brand brand-link" href="index.html" aria-label="Home"><span class="ru">Ситковский А.М.</span><span class="en">Arseniy M. Sitkovskiy</span></a>
    <nav class="nav" aria-label="Main navigation">
      <a href="projects.html"><span class="ru">Проекты</span><span class="en">Projects</span></a>
      <a href="publications.html"><span class="ru">Статьи</span><span class="en">Articles</span></a>
      <a href="media.html"><span class="ru">СМИ</span><span class="en">Media</span></a>
      <a href="diplomas.html"><span class="ru">Дипломы</span><span class="en">Diplomas</span></a>
      <a href="it.html"><span class="ru">Ресурсы</span><span class="en">Resources</span></a>
      <a class="email-btn" href="mailto:omnistat@yandex.ru">omnistat@yandex.ru</a>
      <button class="lang-toggle" data-lang-toggle onclick="toggleLang()" aria-label="Переключить на английский">EN</button>
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
        <a href="https://vk.com/arseniy24gamer" target="_blank" rel="noopener noreferrer" aria-label="VK"><img src="assets/social/vk.svg" alt="" aria-hidden="true"></a>
        <a href="https://t.me/omnistat" target="_blank" rel="noopener noreferrer" aria-label="Telegram"><img src="assets/social/telegram.svg" alt="" aria-hidden="true"></a>
      </div>
    </div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  installFavicon();
  installHeader();
  installFooter();
  setLang(preferredLang());
});
