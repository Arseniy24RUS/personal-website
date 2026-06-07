(function(){
  const FRAME_ALLOW = 'autoplay; encrypted-media; fullscreen; picture-in-picture; clipboard-write; web-share';
  const MOBILE_QUERY = '(max-width: 640px)';

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

  function playerDialog(){
    return document.querySelector('[data-teaching-player]');
  }

  function selectedCard(catalog){
    const id = catalog.dataset.selectedLecture;
    return id ? catalog.querySelector(`[data-lecture-card][data-lecture-id="${id}"]`) : null;
  }

  function setButtonState(button, active){
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  }

  function syncPlatformButtons(catalog){
    const platform = catalog.dataset.platform || defaultPlatform();
    catalog.querySelectorAll('[data-video-platform]').forEach(button => {
      setButtonState(button, button.dataset.videoPlatform === platform);
    });
    const dialog = playerDialog();
    if(!dialog) return;
    dialog.querySelectorAll('[data-dialog-platform]').forEach(button => {
      setButtonState(button, button.dataset.dialogPlatform === platform);
    });
  }

  function clearPlayer(dialog){
    const frame = dialog?.querySelector('[data-teaching-frame]');
    if(frame) frame.innerHTML = '';
    document.body.classList.remove('teaching-dialog-open');
  }

  function closePlayer(){
    const dialog = playerDialog();
    if(!dialog) return;
    if(typeof dialog.close === 'function' && dialog.open){
      dialog.close();
    }else{
      dialog.removeAttribute('open');
      clearPlayer(dialog);
    }
  }

  function renderPlayer(catalog, card){
    const dialog = playerDialog();
    const frame = dialog?.querySelector('[data-teaching-frame]');
    const titleNode = dialog?.querySelector('[data-teaching-player-title]');
    const external = dialog?.querySelector('[data-teaching-external]');
    if(!dialog || !frame || !titleNode || !external || !card) return;

    const platform = catalog.dataset.platform || defaultPlatform();
    const src = platform === 'youtube' ? card.dataset.youtubeSrc : card.dataset.vkSrc;
    const href = platform === 'youtube' ? card.dataset.youtubeLink : card.dataset.vkLink;
    const title = card.querySelector('.teaching-lecture-title')?.textContent.trim() || 'Video lecture';
    if(!src) return;

    titleNode.textContent = title;
    external.href = href || src;
    external.innerHTML = platformExternalText(platform);
    syncPlatformButtons(catalog);

    frame.innerHTML = '';
    const iframe = document.createElement('iframe');
    iframe.src = src;
    iframe.title = title;
    iframe.allow = FRAME_ALLOW;
    iframe.allowFullscreen = true;
    iframe.loading = 'lazy';
    frame.appendChild(iframe);

    if(typeof dialog.showModal === 'function'){
      if(!dialog.open) dialog.showModal();
    }else{
      dialog.setAttribute('open', '');
    }
    document.body.classList.add('teaching-dialog-open');
  }

  function setPlatform(catalog, platform){
    const normalized = platform === 'youtube' ? 'youtube' : 'vk';
    catalog.dataset.platform = normalized;
    syncPlatformButtons(catalog);
    const card = selectedCard(catalog);
    const dialog = playerDialog();
    if(card && dialog?.open) renderPlayer(catalog, card);
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

  function installMobileDetails(catalog){
    const details = catalog.querySelector('.teaching-lecture-details');
    if(!details || !window.matchMedia) return;
    const media = window.matchMedia(MOBILE_QUERY);
    const sync = () => { details.open = !media.matches; };
    sync();
    if(typeof media.addEventListener === 'function'){
      media.addEventListener('change', sync);
    }else if(typeof media.addListener === 'function'){
      media.addListener(sync);
    }
  }

  function installDialog(catalog){
    const dialog = playerDialog();
    if(!dialog || dialog.dataset.teachingInstalled === 'true') return;
    dialog.dataset.teachingInstalled = 'true';

    dialog.querySelectorAll('[data-dialog-platform]').forEach(button => {
      button.addEventListener('click', () => setPlatform(catalog, button.dataset.dialogPlatform));
    });
    dialog.querySelector('[data-teaching-close]')?.addEventListener('click', closePlayer);
    dialog.addEventListener('click', event => {
      if(event.target === dialog) closePlayer();
    });
    dialog.addEventListener('close', () => clearPlayer(dialog));
    document.addEventListener('keydown', event => {
      if(event.key === 'Escape' && dialog.open) closePlayer();
    });
  }

  function installCatalog(catalog){
    installMobileDetails(catalog);
    installDialog(catalog);

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
