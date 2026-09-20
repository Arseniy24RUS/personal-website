/* Observation dates belong to each provider, not the website build date. */
(() => {
  let profile;
  const english = () => document.documentElement.lang === 'en';
  function render() {
    let box = document.querySelector('[data-source-health]');
    if (!box && document.getElementById('gen')) {
      box = document.createElement('div');
      box.dataset.sourceHealth = '';
      box.className = 'muted';
      box.style.fontSize = '12px';
      box.setAttribute('aria-live', 'polite');
      document.getElementById('gen').parentElement.after(box);
    }
    if (!box || !profile) return;
    const en = english();
    const providers = [['elibrary', en ? 'RSCI' : 'РИНЦ'], ['scopus', 'Scopus'], ['wos', 'Web of Science']];
    box.replaceChildren();
    for (const [key, label] of providers) {
      const source = (profile.source_health || {})[key];
      if (!source) continue;
      const line = document.createElement('div');
      const stamp = source.last_success_at && new Date(source.last_success_at);
      const date = stamp && Number.isFinite(stamp.getTime()) ? stamp.toLocaleDateString(en ? 'en-GB' : 'ru-RU') : null;
      const verified = source.status === 'success' && source.origin === 'live' && source.complete;
      line.textContent = label + ': ' + (date
        ? (en ? 'data verified ' : 'данные подтверждены ') + date
        : (en ? 'last verified date unavailable' : 'дата подтверждения не установлена'));
      if (!verified) line.textContent += en ? ' · saved data; latest refresh incomplete' : ' · сохранённые данные; последнее обновление не завершено';
      if (key === 'scopus') {
        const method = (((profile.scientometrics || {}).sources || {}).scopus || {}).method || {};
        const names = en
          ? {publications: 'publications', citations: 'citations', h_index: 'h-index'}
          : {publications: 'публикации', citations: 'цитирования', h_index: 'h-индекс'};
        const calculated = Object.keys(method).filter(name => method[name] === 'calculated_from_complete_search');
        if (calculated.length) {
          line.textContent += (en ? ' · calculated from complete Search API results: ' : ' · рассчитаны по полной выдаче Search API: ')
            + calculated.map(name => names[name] || name).join(', ');
        }
      }
      box.append(line);
    }
  }
  document.addEventListener('DOMContentLoaded', async () => {
    try {
      const response = await fetch('data/public/profile.json', {cache: 'no-store'});
      if (!response.ok) return;
      profile = await response.json();
      render();
    } catch (_) { /* Publication content remains available independently. */ }
  });
  window.addEventListener('site:languagechange', render);
})();
