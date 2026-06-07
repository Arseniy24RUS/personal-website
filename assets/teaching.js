(function(){
  const FRAME_ALLOW = 'autoplay; encrypted-media; fullscreen; picture-in-picture; clipboard-write; web-share';

  function currentLang(){
    return document.documentElement.classList.contains('lang-en') || document.body.classList.contains('lang-en') ? 'en' : 'ru';
  }

  function defaultPlatform(){
    return currentLang() === 'en' ? 'youtube' : 'vk';
  }

  function updateToggleLabel(lecture){
    const button = lecture.querySelector('.teaching-lecture-toggle');
    const state = lecture.querySelector('.teaching-lecture-state');
    if(!button || !state) return;
    const expanded = button.getAttribute('aria-expanded') === 'true';
    state.innerHTML = expanded
      ? '<span class="ru">Скрыть</span><span class="en">Hide</span>'
      : '<span class="ru">Открыть</span><span class="en">Open</span>';
  }

  function renderFrame(catalog, lecture){
    const platform = catalog.dataset.platform || defaultPlatform();
    const frame = lecture.querySelector('.teaching-lecture-frame');
    const title = lecture.querySelector('.teaching-lecture-title')?.textContent.trim() || 'Video lecture';
    const src = platform === 'youtube' ? lecture.dataset.youtubeSrc : lecture.dataset.vkSrc;
    const href = platform === 'youtube' ? lecture.dataset.youtubeLink : lecture.dataset.vkLink;
    if(!frame || !src) return;

    frame.hidden = false;
    frame.innerHTML = '';

    const holder = document.createElement('div');
    holder.className = 'teaching-lecture-frame-inner';

    const iframe = document.createElement('iframe');
    iframe.src = src;
    iframe.title = title;
    iframe.allow = FRAME_ALLOW;
    iframe.allowFullscreen = true;
    iframe.loading = 'lazy';
    holder.appendChild(iframe);
    frame.appendChild(holder);

    if(href){
      const link = document.createElement('a');
      link.className = 'teaching-lecture-external';
      link.href = href;
      link.target = '_blank';
      link.rel = 'noopener';
      link.innerHTML = platform === 'youtube'
        ? '<span class="ru">Открыть на YouTube</span><span class="en">Open on YouTube</span>'
        : '<span class="ru">Открыть в VK Видео</span><span class="en">Open in VK Video</span>';
      frame.appendChild(link);
    }
  }

  function setPlatform(catalog, platform){
    const normalized = platform === 'youtube' ? 'youtube' : 'vk';
    catalog.dataset.platform = normalized;
    catalog.querySelectorAll('[data-video-platform]').forEach(button => {
      const active = button.dataset.videoPlatform === normalized;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    catalog.querySelectorAll('.teaching-lecture').forEach(lecture => {
      const button = lecture.querySelector('.teaching-lecture-toggle');
      if(button?.getAttribute('aria-expanded') === 'true'){
        renderFrame(catalog, lecture);
      }
    });
  }

  function installCatalog(catalog){
    setPlatform(catalog, defaultPlatform());

    catalog.querySelectorAll('[data-video-platform]').forEach(button => {
      button.addEventListener('click', () => setPlatform(catalog, button.dataset.videoPlatform));
    });

    catalog.querySelectorAll('.teaching-lecture').forEach(lecture => {
      const button = lecture.querySelector('.teaching-lecture-toggle');
      const frame = lecture.querySelector('.teaching-lecture-frame');
      if(!button || !frame) return;
      updateToggleLabel(lecture);
      button.addEventListener('click', () => {
        const expanded = button.getAttribute('aria-expanded') === 'true';
        button.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        if(expanded){
          frame.hidden = true;
          frame.innerHTML = '';
        }else{
          renderFrame(catalog, lecture);
        }
        updateToggleLabel(lecture);
      });
    });

    window.addEventListener('site:languagechange', () => {
      setPlatform(catalog, defaultPlatform());
      catalog.querySelectorAll('.teaching-lecture').forEach(updateToggleLabel);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-video-catalog]').forEach(installCatalog);
  });
})();
