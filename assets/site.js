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
  'teaching.html': {
    ru: {title: 'Преподавание — Ситковский А.М.', description: 'Преподавательская деятельность Арсения Михайловича Ситковского: курсы высшего образования, онлайн-курсы и лекции ДПО по демографии, ГИС и государственному управлению.'},
    en: {title: 'Teaching — Arseniy M. Sitkovskiy', description: 'Teaching by Arseniy M. Sitkovskiy: higher education courses, online courses and continuing professional education lectures in demography, GIS and public administration.'}
  },
  'media.html': {
    ru: {title: 'СМИ — Ситковский А.М.', description: 'Материалы СМИ, публичные упоминания, интервью и аналитические публикации Арсения Михайловича Ситковского.'},
    en: {title: 'Media — Arseniy M. Sitkovskiy', description: 'Media articles, public mentions, interviews and analytical publications related to Arseniy M. Sitkovskiy.'}
  },
  'it.html': {
    ru: {title: 'ИТ-ресурсы — Ситковский А.М.', description: 'Интерактивные дашборды, карты, симуляторы и учебные веб-приложения Арсения Михайловича Ситковского.'},
    en: {title: 'IT Resources — Arseniy M. Sitkovskiy', description: 'Interactive dashboards, maps, simulators and educational web applications by Arseniy M. Sitkovskiy.'}
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

const LOCALIZED_PAGES = new Set([
  'index.html',
  'projects.html',
  'publications.html',
  'teaching.html',
  'media.html',
  'diplomas.html',
  'it.html',
  'materials.html',
  'metrics.html'
]);

function pageLangFromUrl(){
  const path = location.pathname.replace(/\\/g, '/');
  if(/\/en(?:\/|$)/.test(path)) return 'en';
  const declared = document.documentElement.getAttribute('data-default-lang');
  return declared === 'en' ? 'en' : 'ru';
}

function preferredLang(){
  return pageLangFromUrl();
}

function localizedPath(lang){
  const key = pageKey();
  if(!LOCALIZED_PAGES.has(key)) return null;
  if(lang === 'en') return key === 'index.html' ? '/en/' : `/en/${key}`;
  return key === 'index.html' ? '/' : `/${key}`;
}

function normalizedPath(path){
  return String(path || '/').replace(/\/index\.html$/i, '/');
}

function navHref(fileName){
  const key = fileName || 'index.html';
  if(pageLangFromUrl() === 'en' && LOCALIZED_PAGES.has(key)){
    return key === 'index.html' ? 'en/' : `en/${key}`;
  }
  return key;
}

function faviconHref(){
  return new URL('assets/favicon.svg?v=20260603', document.baseURI).href;
}

function installFavicon(){
  const href = faviconHref();
  document.querySelectorAll('link[rel~="icon"], link[rel="shortcut icon"]').forEach(el => el.remove());
  const icon = document.createElement('link');
  icon.rel = 'icon';
  icon.type = 'image/svg+xml';
  icon.href = href;
  document.head.appendChild(icon);
  const shortcut = document.createElement('link');
  shortcut.rel = 'shortcut icon';
  shortcut.href = href;
  document.head.appendChild(shortcut);
}

function installVisualFixes(){
  if(document.getElementById('site-visual-fixes')) return;
  const style = document.createElement('style');
  style.id = 'site-visual-fixes';
  style.textContent = `
    .social-links a{overflow:hidden;isolation:isolate;}
    .social-links a:hover{background:#4b4b4b!important;transform:translateY(-2px);}
    .social-links img{width:28px!important;height:28px!important;display:block!important;object-fit:contain!important;object-position:center!important;}
  `;
  document.head.appendChild(style);
}

function updatePageMeta(lang){
  // SEO-critical title and meta description are defined statically in HTML.
  // Do not mutate them at runtime: crawlers and localized URLs must see stable metadata.
  return;
}

function setLang(lang, options){
  const normalized = lang === 'ru' ? 'ru' : 'en';
  const opts = options || {};
  const targetPath = localizedPath(normalized);
  if(!opts.noNavigate && targetPath && normalizedPath(location.pathname) !== normalizedPath(targetPath)){
    try{ localStorage.setItem('lang', normalized); }catch(e){}
    location.href = targetPath + location.search + location.hash;
    return;
  }
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
    <a class="brand brand-link" href="${navHref('index.html')}" aria-label="Home"><span class="ru">Ситковский А.М.</span><span class="en">Arseniy M. Sitkovskiy</span></a>
    <nav class="nav" aria-label="Main navigation">
      <a href="${navHref('projects.html')}"><span class="ru">Проекты</span><span class="en">Projects</span></a>
      <a href="${navHref('publications.html')}"><span class="ru">Статьи</span><span class="en">Articles</span></a>
      <a href="${navHref('teaching.html')}"><span class="ru">Преподавание</span><span class="en">Teaching</span></a>
      <a href="${navHref('media.html')}"><span class="ru">СМИ</span><span class="en">Media</span></a>
      <a href="${navHref('diplomas.html')}"><span class="ru">Дипломы</span><span class="en">Diplomas</span></a>
      <a href="${navHref('it.html')}"><span class="ru">ИТ-ресурсы</span><span class="en">IT Resources</span></a>
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
        <a href="https://vk.com/arseniy24gamer" target="_blank" rel="noopener noreferrer" aria-label="VK"><img src="assets/social/vk.svg?v=20260603" alt="" aria-hidden="true"></a>
        <a href="https://t.me/omnistat" target="_blank" rel="noopener noreferrer" aria-label="Telegram"><img src="assets/social/telegram.svg?v=20260603" alt="" aria-hidden="true"></a>
      </div>
    </div>`;
}

function orderHomeSections(){
  if(!document.body.classList.contains('home')) return;
  const profile = document.querySelector('.profile-hero');
  if(!profile) return;
  let anchor = profile;
  ['career', 'education', 'dpo', 'grants', 'research'].forEach(id => {
    const section = document.getElementById(id);
    if(section){
      anchor.after(section);
      anchor = section;
    }
  });
}

installFavicon();
installVisualFixes();

document.addEventListener('DOMContentLoaded', () => {
  installFavicon();
  installVisualFixes();
  installHeader();
  installFooter();
  orderHomeSections();
  setLang(preferredLang(), {noNavigate: true});
});
