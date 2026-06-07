let DPO_ITEMS = [];

function dpoEsc(value){
  return String(value || '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function dpoSorted(items){
  return (items || []).slice().sort((a, b) => {
    const ay = Number(a.year) || -1;
    const by = Number(b.year) || -1;
    if (ay !== by) return by - ay;
    return String(a.title || a.id || '').localeCompare(String(b.title || b.id || ''), 'ru');
  });
}

function dpoThumbClass(item){
  return 'diploma-thumb' + ((Number(item.span) > 1 || item.orientation === 'landscape') ? ' is-landscape' : '');
}

function renderDpoGallery(){
  const box = document.getElementById('dpo-gallery');
  if (!box) return;
  if (!DPO_ITEMS.length) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = DPO_ITEMS.map((item, index) => (
    `<button class="${dpoThumbClass(item)}" data-index="${index}" title="${dpoEsc(item.title)}">` +
      `<img loading="lazy" src="${dpoEsc(item.thumb)}" alt="${dpoEsc(item.title)}">` +
    `</button>`
  )).join('');
  box.querySelectorAll('.diploma-thumb').forEach(btn => {
    btn.onclick = () => openDpoItem(Number(btn.dataset.index));
  });
}

function openDpoItem(index){
  const item = DPO_ITEMS[index];
  if (!item) return;
  const modal = document.getElementById('dpo-modal');
  const pagesBox = document.getElementById('dpo-modal-pages');
  const title = document.getElementById('dpo-modal-title');
  const download = document.getElementById('dpo-modal-download');
  const pages = item.pages && item.pages.length ? item.pages : [{src:item.full, page:1}];
  title.textContent = (item.year ? item.year + ' · ' : '') + (item.title || '');
  download.href = item.download || item.full || pages[0].src;
  download.download = (item.id || 'dpo') + '.webp';
  pagesBox.innerHTML = pages.map(page => (
    `<img src="${dpoEsc(page.src)}" alt="${dpoEsc(item.title)}${pages.length > 1 ? ' · ' + page.page : ''}">`
  )).join('');
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeDpoItem(){
  const modal = document.getElementById('dpo-modal');
  const pagesBox = document.getElementById('dpo-modal-pages');
  if (modal) modal.classList.remove('open');
  if (pagesBox) pagesBox.innerHTML = '';
  document.body.style.overflow = '';
}

async function loadDpoGallery(){
  const box = document.getElementById('dpo-gallery');
  if (!box) return;
  try {
    const data = await fetch('data/dpo/gallery.json', {cache:'no-store'}).then(r => r.json());
    DPO_ITEMS = dpoSorted(data.items || []);
  } catch (error) {
    DPO_ITEMS = [];
  }
  renderDpoGallery();
}

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeDpoItem();
});
document.addEventListener('DOMContentLoaded', loadDpoGallery);
