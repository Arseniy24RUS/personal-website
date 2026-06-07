(function(){
  'use strict';
  const DATA_URL='data/risi/articles.json';
  let records=[];

  function lang(){return document.documentElement.classList.contains('lang-en')||document.body.classList.contains('lang-en')?'en':'ru'}
  function esc(s){return String(s||'').replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]})}
  function safeArticleHtml(html){
    const template=document.createElement('template');
    template.innerHTML=String(html||'');
    template.content.querySelectorAll('script,iframe,object,embed,link,meta').forEach(function(el){el.remove()});
    template.content.querySelectorAll('*').forEach(function(el){
      Array.from(el.attributes).forEach(function(attr){
        const name=attr.name.toLowerCase();
        const value=String(attr.value||'').trim().toLowerCase();
        if(name.indexOf('on')===0||((name==='href'||name==='src')&&value.indexOf('javascript:')===0))el.removeAttribute(attr.name);
      });
    });
    return template.innerHTML;
  }
  function pick(r,key){const l=lang();return r[`${key}_${l}`]||r[`${key}_ru`]||r[key]||r[`${key}_en`]||''}
  function sourceText(r){return (lang()==='en'?'RISS archive':'Архив РИСИ')+' · '+(r.year||'')}
  function byId(id){return records.find(r=>r.id===id)}

  function cardHtml(r){
    const title=pick(r,'title');
    const desc=pick(r,'description');
    const hasImage=Boolean(r.image);
    const image=hasImage?`<a class="media-image" href="${esc(r.html)}" data-risi-open="${esc(r.id)}"><img loading="lazy" src="${esc(r.image)}" alt="${esc(title)}"></a>`:'';
    const note=r.thumbnail_note_ru?`<div class="risi-extra-note ru">${esc(r.thumbnail_note_ru)}</div><div class="risi-extra-note en">${esc(r.thumbnail_note_en||r.thumbnail_note_ru)}</div>`:'';
    return `<article class="media-card risi-card ${hasImage?'has-image':'no-image'}" data-risi-id="${esc(r.id)}" data-year="${esc(r.year)}">${image}<div class="media-body"><div class="media-source">${esc(sourceText(r))}</div><h2><a href="${esc(r.html)}" data-risi-open="${esc(r.id)}">${esc(title)}</a></h2>${desc?`<p>${esc(desc)}</p>`:''}${note}<div class="risi-actions"><a class="media-link" href="${esc(r.html)}" data-risi-open="${esc(r.id)}"><span class="ru">Читать на сайте</span><span class="en">Read on site</span></a><a class="risi-secondary-link" href="${esc(r.docx)}" download><span class="ru">Скачать DOCX</span><span class="en">Download DOCX</span></a></div></div></article>`;
  }

  function render(){
    const box=document.getElementById('risi-list');
    if(!box)return;
    if(!records.length){box.innerHTML='<div class="risi-loading ru">Архивные материалы загружаются.</div><div class="risi-loading en">Archival materials are loading.</div>';return}
    const years=[...new Set(records.map(r=>r.year))].sort((a,b)=>a-b);
    box.innerHTML=years.map(year=>{
      const items=records.filter(r=>r.year===year).sort((a,b)=>(a.order||0)-(b.order||0));
      return `<section class="risi-year-group" aria-labelledby="risi-year-${esc(year)}"><h3 class="risi-year-heading" id="risi-year-${esc(year)}">${esc(year)}</h3><div class="risi-year-cards">${items.map(cardHtml).join('')}</div></section>`;
    }).join('');
  }

  function setReaderBusy(isBusy){
    const content=document.getElementById('risi-reader-content');
    if(content&&isBusy){content.innerHTML='<div class="risi-loading ru">Загрузка полного текста…</div><div class="risi-loading en">Loading full text…</div>'}
  }

  async function openRecord(id, updateUrl){
    const r=byId(id); if(!r)return;
    const dialog=document.getElementById('risi-reader');
    const title=document.getElementById('risi-reader-title');
    const source=document.getElementById('risi-reader-source');
    const download=document.getElementById('risi-reader-download');
    const content=document.getElementById('risi-reader-content');
    if(!dialog||!title||!source||!download||!content)return;
    title.textContent=pick(r,'title');
    source.textContent=sourceText(r);
    download.href=r.docx;
    download.setAttribute('download','');
    setReaderBusy(true);
    document.body.classList.add('risi-body-no-scroll');
    if(typeof dialog.showModal==='function'&&!dialog.open){dialog.showModal()}else{dialog.setAttribute('open','')}
    try{
      const response=await fetch(r.html,{cache:'no-store'});
      if(!response.ok)throw new Error('HTTP '+response.status);
      content.innerHTML=safeArticleHtml(await response.text());
      content.scrollTop=0;
      dialog.querySelector('.risi-reader-shell').scrollTop=0;
    }catch(e){
      content.innerHTML='<div class="risi-error ru">Не удалось загрузить полный текст. Можно скачать Word-файл по кнопке выше.</div><div class="risi-error en">The full text could not be loaded. You can download the Word file using the button above.</div>';
    }
    if(updateUrl!==false){
      const url=new URL(window.location.href);
      url.searchParams.set('risi',id);
      url.hash='risi-reader';
      history.replaceState({risi:id},'',url);
    }
  }

  function closeReader(clearUrl){
    const dialog=document.getElementById('risi-reader');
    if(!dialog)return;
    if(dialog.open&&typeof dialog.close==='function')dialog.close();else dialog.removeAttribute('open');
    document.body.classList.remove('risi-body-no-scroll');
    if(clearUrl!==false){
      const url=new URL(window.location.href);
      url.searchParams.delete('risi');
      if(url.hash==='#risi-reader')url.hash='risi-archive';
      history.replaceState({},'',url);
    }
  }

  async function load(){
    const box=document.getElementById('risi-list'); if(!box)return;
    box.innerHTML='<div class="risi-loading ru">Архивные материалы загружаются.</div><div class="risi-loading en">Archival materials are loading.</div>';
    try{
      const data=await fetch(DATA_URL,{cache:'no-store'}).then(r=>r.json());
      records=(data.records||[]).slice();
      render();
      const id=new URL(window.location.href).searchParams.get('risi');
      if(id&&byId(id))openRecord(id,false);
    }catch(e){
      box.innerHTML='<div class="risi-error ru">Не удалось загрузить архив РИСИ. Проверьте наличие файла data/risi/articles.json.</div><div class="risi-error en">The RISS archive could not be loaded. Please check data/risi/articles.json.</div>';
    }
  }

  document.addEventListener('click',function(e){
    const opener=e.target.closest('[data-risi-open]');
    if(opener){e.preventDefault();openRecord(opener.getAttribute('data-risi-open'),true);return}
    if(e.target&&e.target.id==='risi-reader-close'){e.preventDefault();closeReader(true);return}
    const dialog=document.getElementById('risi-reader');
    if(dialog&&e.target===dialog)closeReader(true);
  });
  document.addEventListener('DOMContentLoaded',function(){
    load();
    const dialog=document.getElementById('risi-reader');
    if(dialog)dialog.addEventListener('close',function(){document.body.classList.remove('risi-body-no-scroll')});
  });
  window.addEventListener('site:languagechange',render);
  window.addEventListener('popstate',function(){
    const id=new URL(window.location.href).searchParams.get('risi');
    if(id&&byId(id))openRecord(id,false);else closeReader(false);
  });
})();
