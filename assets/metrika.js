/* Yandex Metrika: explicit page and outbound-link events only. */
(() => {
  'use strict';

  const script = document.currentScript;
  const eventName = 'portfolio-metrika';
  const numberPattern = /^[1-9]\d{0,11}$/;
  const toPublicUrl = (raw) => {
    try {
      const url = new URL(raw);
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
      url.search = '';
      url.hash = '';
      return url;
    } catch {
      return null;
    }
  };

  if (script.hasAttribute('data-frame')) {
    if (window.parent === window) return;
    let counter;
    let lastView;
    addEventListener(eventName, ({detail}) => {
      if (!detail) return;
      if (detail.type === 'view') {
        const url = new URL(detail.url);
        if (url.origin !== location.origin || url.search) return;
        // Keep the noindex frame on its own URL. Only the hit uses the public URL.
        if (!counter) {
          if (!numberPattern.test(detail.counter)) return;
          counter = Number(detail.counter);
          window.ym = function () { (window.ym.a ||= []).push(arguments); };
          window.ym.l = Date.now();
          window.ym(counter, 'init', {
            defer: true,
            trackHash: false,
            trackLinks: false,
            clickmap: false,
            webvisor: false,
            childIframe: false,
            ecommerce: false,
            accurateTrackBounce: true,
            disableYtm: true,
            sendTitle: false
          });
          const tag = document.createElement('script');
          tag.async = true;
          tag.referrerPolicy = 'no-referrer';
          tag.src = 'https://mc.yandex.ru/metrika/tag.js';
          document.head.append(tag);
        }
        if (lastView === url.href) return;
        window.ym(counter, 'hit', url.href, { referer: lastView || detail.referrer });
        lastView = url.href;
      } else if (counter && detail.type === 'outbound') {
        const url = toPublicUrl(detail.url);
        if (url && url.origin !== location.origin) {
          window.ym(counter, 'extLink', url.href, {
            params: { outbound_source_page: lastView }
          });
        }
      }
    });
    return;
  }

  if (window.parent !== window) return;
  const counter = script.dataset.counter;
  if (!numberPattern.test(counter) || location.origin !== 'https://sitkovskiy.ru') return;

  const pageUrl = new URL(location.pathname.replace(/\/index\.html$/, '/'), location.origin).href;
  const source = toPublicUrl(document.referrer);
  const referrer = source ? `${source.origin}/` : '';
  const frame = document.createElement('iframe');
  frame.hidden = true;
  frame.tabIndex = -1;
  frame.setAttribute('aria-hidden', 'true');
  frame.title = 'Веб-аналитика';
  frame.referrerPolicy = 'no-referrer';
  frame.src = new URL('./metrika-frame.html', script.src).href;
  let ready = false;
  function emit(detail) {
    if (!ready) return;
    try {
      const target = frame.contentWindow;
      if (target) target.dispatchEvent(new target.CustomEvent(eventName, { detail }));
    } catch {
      // Tracking should never interrupt navigation if the frame is blocked.
    }
  }
  function view() {
    emit({ type: 'view', counter, url: pageUrl, referrer });
  }
  function outbound(event) {
    if (!event.isTrusted || event.defaultPrevented || (event.type === 'auxclick' && event.button !== 1)) return;
    const link = event.target.closest?.('a[href]');
    if (!link) return;
    const url = toPublicUrl(link.href);
    if (url && url.origin !== location.origin) emit({ type: 'outbound', url: url.href });
  }
  frame.addEventListener('load', () => {
    ready = true;
    view();
  }, { once: true });
  document.body.append(frame);
  document.addEventListener('click', outbound);
  document.addEventListener('auxclick', outbound);
})();
