(function(){
  const FRAME_ALLOW = 'autoplay; encrypted-media; fullscreen; picture-in-picture; clipboard-write; web-share';

  function currentLang(){
    return document.documentElement.classList.contains('lang-en') || document.body.classList.contains('lang-en') ? 'en' : 'ru';
  }

  function defaultPlatform(){
    return currentLang() === 'en' ? 'youtube' : 'vk';
  }

  function platformExternalText(platform){
    return platform === 'youtube'
      ? '<span class="ru">Открыть на YouTube</span><span class="en">Open on YouTube</span>'
      : '<span class="ru">Открыть в VK Видео</span><span class="en">Open in VK Video</span>';
  }

  function selectedCard(catalog){
    const id = catalog.dataset.selectedLecture;
    return id ? catalog.querySelector(`[data-lecture-card][data-lecture-id="${id}"]`) : null;
  }

  function renderPlayer(catalog, card){
    const player = catalog.querySelector('[data-teaching-player]');
    const frame = catalog.querySelector('[data-teaching-frame]');
    const titleNode = catalog.querySelector('[data-teaching-player-title]');
    const external = catalog.querySelector('[data-teaching-external]');
    if(!player || !frame || !titleNode || !external || !card) return;

    const platform = catalog.dataset.platform || defaultPlatform();
    const src = platform === 'youtube' ? card.dataset.youtubeSrc : card.dataset.vkSrc;
    const href = platform === 'youtube' ? card.dataset.youtubeLink : card.dataset.vkLink;
    const title = card.querySelector('.teaching-lecture-title')?.textContent.trim() || 'Video lecture';
    if(!src) return;

    titleNode.textContent = title;
    external.href = href || src;
    external.innerHTML = platformExternalText(platform);
    frame.innerHTML = '';

    const iframe = document.createElement('iframe');
    iframe.src = src;
    iframe.title = title;
    iframe.allow = FRAME_ALLOW;
    iframe.allowFullscreen = true;
    iframe.loading = 'lazy';
    frame.appendChild(iframe);

    player.hidden = false;
  }

  function setPlatform(catalog, platform){
    const normalized = platform === 'youtube' ? 'youtube' : 'vk';
    catalog.dataset.platform = normalized;
    catalog.querySelectorAll('[data-video-platform]').forEach(button => {
      const active = button.dataset.videoPlatform === normalized;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    const card = selectedCard(catalog);
    if(card) renderPlayer(catalog, card);
  }

  function selectCard(catalog, card){
    catalog.querySelectorAll('[data-lecture-card]').forEach(item => {
      const active = item === card;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    catalog.dataset.selectedLecture = card.dataset.lectureId || '';
    renderPlayer(catalog, card);
  }

  function installCatalog(catalog){
    catalog.querySelectorAll('[data-lecture-card]').forEach((card, index) => {
      card.dataset.lectureId = card.dataset.lectureId || String(index + 1);
      card.setAttribute('aria-pressed', 'false');
      card.addEventListener('click', () => selectCard(catalog, card));
    });

    catalog.querySelectorAll('[data-video-platform]').forEach(button => {
      button.addEventListener('click', () => setPlatform(catalog, button.dataset.videoPlatform));
    });

    setPlatform(catalog, defaultPlatform());
    window.addEventListener('site:languagechange', () => setPlatform(catalog, defaultPlatform()));
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-video-catalog]').forEach(installCatalog);
  });
})();
