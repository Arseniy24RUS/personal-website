function esc(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function hasCyr(s){return /[А-Яа-яЁё]/.test(String(s||''))}
function isEn(){return document.documentElement.classList.contains('lang-en')||document.body.classList.contains('lang-en')}
function normalize(s){return String(s||'').toLowerCase().replace(/ё/g,'е').replace(/[^a-zа-я0-9]+/g,' ').trim()}

const RU_LAT={'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'};
const ACR={'рф':'РФ','ран':'РАН','ринц':'РИНЦ','вак':'ВАК','рудн':'РУДН','фнисц':'ФНИСЦ','ранхигс':'РАНХиГС','рнф':'РНФ','рффи':'РФФИ','гис':'ГИС','дпо':'ДПО','еаэс':'ЕАЭС','снг':'СНГ','ссср':'СССР','кмнр':'КМНР','кмнс':'КМНС','оон':'ООН','рцни':'РЦНИ','doi':'DOI'};
const PROPER=[['российской федерации','Российской Федерации'],['республика тыва','Республика Тыва'],['республики тыва','Республики Тыва'],['республике тыва','Республике Тыва'],['северного казахстана','Северного Казахстана'],['евразийского макрорегиона','Евразийского макрорегиона'],['челябинской области','Челябинской области'],['московского региона','Московского региона'],['л. л. рыбаковского','Л. Л. Рыбаковского'],['рыбаковского','Рыбаковского'],['севастополя','Севастополя'],['чувашии','Чувашии'],['россии','России'],['россия','Россия'],['россию','Россию'],['россией','Россией'],['тыва','Тыва'],['тувы','Тувы'],['казахстана','Казахстана']];
const BAD_ONE_LETTER=new Set(['К','к','Ы','ы']);

function translit(s){return String(s||'').split('').map(ch=>{const low=ch.toLowerCase();const v=RU_LAT[low];if(v==null)return ch;return ch===low?v:v.charAt(0).toUpperCase()+v.slice(1)}).join('').replace(/\s+/g,' ').trim()}
function mostlyUpper(s){const letters=String(s||'').match(/[A-Za-zА-Яа-яЁё]/g)||[];if(letters.length<8)return false;const up=letters.filter(x=>x.toUpperCase()===x&&x.toLowerCase()!==x);return up.length/letters.length>.65}
function capFirst(s){s=String(s||'');for(let i=0;i<s.length;i++){if(/[A-Za-zА-Яа-яЁё]/.test(s[i]))return s.slice(0,i)+s[i].toUpperCase()+s.slice(i+1)}return s}
function wordRe(src){return new RegExp('(?<![\\wА-Яа-яЁё])'+src.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?![\\wА-Яа-яЁё])','gi')}
function smartRuTitle(s){
  s=String(s||'').replace(/\s+/g,' ').trim();
  if(!s)return '';
  if(!hasCyr(s))return mostlyUpper(s)?capFirst(s.toLowerCase()):capFirst(s);
  let r=mostlyUpper(s)?s.toLowerCase():s;
  r=r.replace(/\s+([:;,.!?])/g,'$1').replace(/([:;,.!?])([^\s])/g,'$1 $2').replace(/\s+[-–—]\s+/g,' — ').replace(/\s+/g,' ').trim();
  r=capFirst(r);
  r=r.replace(/([.!?]\s+)([а-яё])/g,(m,a,b)=>a+b.toUpperCase());
  PROPER.forEach(([a,b])=>{r=r.replace(wordRe(a),b)});
  Object.entries(ACR).forEach(([a,b])=>{r=r.replace(wordRe(a),b)});
  r=r.replace(/(?<![А-ЯA-Z])\b([а-яёa-z])\.\s*([а-яёa-z])\./g,(m,a,b)=>`${a.toUpperCase()}. ${b.toUpperCase()}.`);
  r=r.replace(/\bг\.\s*([а-яё])/g,(m,a)=>`г. ${a.toUpperCase()}`);
  return r;
}

function parseTSV(t){
  const lines=String(t||'').trim().split(/\n/).filter(Boolean);
  if(!lines.length)return [];
  const h=lines[0].split('\t');
  return lines.slice(1).map(line=>{
    const c=line.split('\t');const r={};h.forEach((k,i)=>r[k]=c[i]||'');
    return sanitizePub({number:r.number,year:r.year,rinc:+r.rinc_citations||0,rinc_citations:+r.rinc_citations||0,scopus_citations:r.scopus_citations,title:r.title,title_ru:r.title_ru||r.title,title_ru_display:r.title_ru_display,title_en:r.title_en,authors_raw:r.authors,venue:r.venue,venue_ru:r.venue_ru||r.venue,venue_en:r.venue_en,volume:r.volume,issue:r.issue,pages:r.pages,doi:r.doi,url:r.url,gost_ru:r.gost_ru,apa_en:r.apa_en,sources:r.sources||''});
  });
}

function cleanValue(v){return String(v||'').replace(/\s+/g,' ').trim()}
function validVenue(v){v=cleanValue(v);return v.length>=3&&!BAD_ONE_LETTER.has(v)&&!/^[A-ZА-ЯЁ]$/.test(v)}
function validVolume(v){v=cleanValue(v);return !!v&&(!/^[А-Яа-яЁё]$/.test(v)||/^[IVXLC]+$/i.test(v))&&!BAD_ONE_LETTER.has(v)}
function validIssue(v){v=cleanValue(v);return !!v&&v.length<=20&&!BAD_ONE_LETTER.has(v)}
function validPages(v){v=cleanValue(v);return /^[0-9]+\s*[-–—]?\s*[0-9]*$/.test(v)}
function badReferenceText(s){s=String(s||'');return /\/\/\s*[КЫ]\.|—\s*Т\.\s*[КЫ]\.|,\s*[КЫ](?:\(|,|\.)/.test(s)}
function sanitizedCopy(p){
  const q=Object.assign({},p||{});
  if(!validVenue(q.venue))q.venue='';
  if(!validVenue(q.venue_ru))q.venue_ru=q.venue||'';
  if(!validVenue(q.venue_en))q.venue_en='';
  if(!validVolume(q.volume))q.volume='';
  if(!validIssue(q.issue))q.issue='';
  if(!validPages(q.pages))q.pages='';
  q.title_ru_display=smartRuTitle(q.title_ru_display||q.title_ru||q.title||'');
  if(badReferenceText(q.gost_ru))q.gost_ru='';
  if(badReferenceText(q.apa_en))q.apa_en='';
  return q;
}
function sanitizePub(p){
  const q=sanitizedCopy(p);
  if(q.title_ru_display && (!q.title_ru || mostlyUpper(q.title_ru)))q.title_ru=q.title_ru_display;
  if(q.title_ru_display && (!q.title || mostlyUpper(q.title)))q.title=q.title_ru_display;
  return q;
}

function sourcesOf(p){return Array.isArray(p.sources)?p.sources.join(','):String(p.sources||'')}
function doiUrl(doi){doi=String(doi||'').replace(/^https?:\/\/(dx\.)?doi\.org\//i,'').trim();return doi?`https://doi.org/${doi}`:''}
function pageRange(s){return String(s||'').replace(/\s*[-–—]\s*/g,'–').replace(/^[СC]\.?\s*/,'')}
function initials(s){return String(s||'').replace(/\s+/g,'').replace(/([A-ZА-ЯЁ])\.?/g,'$1. ').trim()}
function authorPartToApa(part){
  part=String(part||'').trim();
  if(!part)return '';
  if(/^(и др\.?|et al\.?)$/i.test(part))return 'et al.';
  part=translit(part).replace(/\s+/g,' ').trim();
  let m=part.match(/^(.+?)\s+([A-Z](?:\.?\s*[A-Z]\.?)+)$/);
  if(m)return `${m[1].replace(/\.$/,'')}, ${initials(m[2])}`;
  m=part.match(/^(.+?),\s*(.+)$/);
  if(m)return `${m[1].replace(/\.$/,'')}, ${initials(m[2])}`;
  return part;
}
function authorsApa(raw){
  let parts=String(raw||'').split(',').map(authorPartToApa).filter(Boolean);
  if(!parts.length)return 'Sitkovskiy, A. M.';
  if(parts.some(x=>/^et al\.?$/i.test(x)))return (parts.find(x=>!/^et al\.?$/i.test(x))||parts[0])+' et al.';
  if(parts.length===1)return parts[0];
  if(parts.length===2)return parts[0]+' & '+parts[1];
  return parts.slice(0,-1).join(', ')+', & '+parts[parts.length-1];
}
function fallbackApa(pub){
  const p=sanitizedCopy(pub);
  const authors=authorsApa(p.authors_en||p.authors_raw||p.authors||'');
  const year=p.year||'n.d.';
  const title=(p.title_en||translit(p.title_ru_display||p.title_ru||p.title||'')).replace(/\.$/,'');
  const venue=p.venue_en||translit(p.venue_ru||p.venue||p.publisher||'');
  const vol=p.volume||'';const issue=p.issue||'';const pages=pageRange(p.pages);const doi=doiUrl(p.doi);
  let out=`${authors} (${year}). ${title}.`;
  if(venue){out+=` ${venue}`;if(vol){out+=`, ${vol}`;if(issue)out+=`(${issue})`}else if(issue){out+=`, (${issue})`}if(pages)out+=`, ${pages}`;out+='.'}
  if(doi)out+=` ${doi}`;else if(p.url)out+=` ${p.url}`;
  return out.replace(/\s+/g,' ').trim();
}
function fallbackGost(pub){
  const p=sanitizedCopy(pub);
  const authors=(p.authors_raw||p.authors||'').replace(/\.$/,'');
  const title=smartRuTitle(p.title_ru_display||p.title_ru||p.title||'');
  const venue=p.venue_ru||p.venue||p.book_title||'';const vol=p.volume||'';const issue=p.issue||'';const pages=pageRange(p.pages);const doi=String(p.doi||'').replace(/^https?:\/\/(dx\.)?doi\.org\//i,'');
  let out='';if(authors)out+=authors+'. ';if(title)out+=title.replace(/\.$/,'')+'.';if(venue)out+=` // ${venue.replace(/\.$/,'')}.`;if(p.year)out+=` — ${p.year}.`;if(vol)out+=` — Т. ${vol}.`;if(issue)out+=` — № ${issue}.`;if(pages)out+=` — С. ${pages}.`;if(doi)out+=` — DOI: ${doi}.`;else if(p.url)out+=` — URL: ${p.url}.`;
  return out.replace(/\s+/g,' ').trim();
}
function citation(pub){const p=sanitizedCopy(pub);return isEn()?((p.apa_en&&!badReferenceText(p.apa_en))?p.apa_en:fallbackApa(p)):((p.gost_ru&&!badReferenceText(p.gost_ru))?p.gost_ru:fallbackGost(p))}

function qualityFor(p){if(!window.QUALITY)return null;if(window.QUALITY[p.venue])return window.QUALITY[p.venue];const nv=normalize(p.venue);for(const [k,v] of Object.entries(window.QUALITY)){if(normalize(k)===nv)return v}return null}
function badgeHtml(q,p){const out=[];const src=sourcesOf(p);if(src.includes('scopus'))out.push(`<span class="badge">Scopus API</span>`);if(src.includes('wos'))out.push(`<span class="badge">Web of Science</span>`);if(q){if(q.scopus)out.push(`<span class="badge">Scopus ${esc(q.scopus_snip_quartile||q.scopus_sjr_quartile||'')}</span>`);if(q.wos_core)out.push(`<span class="badge">WoS ${esc(q.wos_jif_quartile||'CC')}</span>`);if(q.rsci)out.push(`<span class="badge">RSCI</span>`);if(q.white_list_2025)out.push(`<span class="badge light">${isEn()?'RCNI list':'БС РЦНИ'}-${esc(q.white_list_2025)}</span>`);else if(q.white_list_2023)out.push(`<span class="badge light">${isEn()?'List':'БС'}-${esc(q.white_list_2023)}</span>`);if(q.rudn_points)out.push(`<span class="badge light">RUDN ${esc(q.rudn_points)}</span>`)}if((p.rinc||p.rinc_citations)>0)out.push(`<span class="badge light">${isEn()?'RSCI cit.':'РИНЦ цит.'}: ${p.rinc||p.rinc_citations}</span>`);if(p.scopus_citations!==''&&p.scopus_citations!=null)out.push(`<span class="badge light">Scopus cit.: ${p.scopus_citations}</span>`);return out.join('')}
function fmtMetric(v){return v==null||v===''?'—':String(v)}
async function loadScientometrics(){try{const profile=await fetch('data/public/profile.json',{cache:'no-store'}).then(r=>r.json());window.SCIENTOMETRICS=profile.scientometrics||null}catch(e){window.SCIENTOMETRICS=null}renderScientometrics()}
function renderScientometrics(){const box=document.getElementById('scientometrics');if(!box)return;const m=window.SCIENTOMETRICS;if(!m||!m.sources){box.innerHTML='';return}const cols=m.columns||['rinc','scopus','wos'];const rows=m.rows||[];const ids={rinc:{label:isEn()?'RSCI':'РИНЦ',url:'https://www.elibrary.ru/author_profile.asp?id=1012909'},scopus:{label:'Scopus',url:'http://www.scopus.com/inward/authorDetails.url?authorID=57220956828&partnerID=MN8TOARS'},wos:{label:'Web of Science',url:'https://www.webofscience.com/wos/author/record/AAG-1530-2021'}};const colHead=cols.map(c=>{const info=ids[c]||{label:c,url:'#'};return `<div class="scientometrics-cell scientometrics-head"><a href="${esc(info.url)}" target="_blank" rel="noopener">${esc(info.label)}</a></div>`}).join('');const body=rows.map(r=>`<div class="scientometrics-cell scientometrics-rowhead">${esc(isEn()?(r.label_en||r.label_ru):(r.label_ru||r.label_en))}</div>${cols.map(c=>`<div class="scientometrics-cell"><span class="scientometrics-value">${esc(fmtMetric((m.sources[c]||{})[r.key]))}</span></div>`).join('')}`).join('');box.innerHTML=`<section class="scientometrics-card"><div class="scientometrics-grid"><div class="scientometrics-cell scientometrics-head"><span class="ru">Показатель</span><span class="en">Metric</span></div>${colHead}${body}</div></section>`}

let PUBS=[];window.QUALITY={};window.SCIENTOMETRICS=null;
async function loadPublications(){
  try{return (await fetch('data/public/publications.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject())).map(sanitizePub)}catch(e){}
  let txt;
  try{txt=await fetch('data/public/publications.tsv',{cache:'no-store'}).then(r=>r.ok?r.text():Promise.reject())}
  catch(e){txt=await fetch('data/elibrary/publications.tsv',{cache:'no-store'}).then(r=>r.text());txt='number\tyear\trinc_citations\tscopus_citations\ttitle\ttitle_ru\ttitle_ru_display\ttitle_en\ttitle_en_source\tauthors\tvenue\tvenue_ru\tvenue_en\tvolume\tissue\tpages\tdoi\turl\tgost_ru\tapa_en\tsources\n'+txt.split(/\n/).filter(Boolean).map(line=>{const c=line.split('\t');return [c[0],c[1],c[2],'',c[3],c[3],smartRuTitle(c[3]),'', '',c[4],c[5],c[5],'','','',c[6],'',c[7],fallbackGost({authors_raw:c[4],title_ru:c[3],venue:c[5],year:c[1],pages:c[6],url:c[7]}),'','elibrary'].join('\t')}).join('\n')}
  return parseTSV(txt);
}
function render(){
  const qEl=document.getElementById('q');const yearEl=document.getElementById('year');const srcEl=document.getElementById('src');const countEl=document.getElementById('count');const pubsEl=document.getElementById('pubs');
  if(!qEl||!yearEl||!srcEl||!countEl||!pubsEl)return;
  const q=(qEl.value||'').toLowerCase();const y=yearEl.value;const src=srcEl.value;
  const arr=PUBS.filter(p=>(!y||String(p.year)===String(y))&&(!src||sourcesOf(p).includes(src))&&(!q||[p.gost_ru,p.apa_en,p.title,p.title_ru,p.title_ru_display,p.title_en,p.authors_raw,p.venue,p.venue_ru,p.venue_en,p.year,p.doi].join(' ').toLowerCase().includes(q)));
  countEl.textContent=arr.length;qEl.placeholder=isEn()?'Search references by title, author, journal, DOI':'Поиск по названию, автору, журналу, DOI';
  const srcAll=document.getElementById('src-all');const yearAll=document.getElementById('year-all');
  if(srcAll)srcAll.textContent=isEn()?'All sources':'Все источники';
  if(yearAll)yearAll.textContent=isEn()?'All years':'Все годы';
  pubsEl.innerHTML=arr.map(pub=>{const p=sanitizedCopy(pub);const qual=qualityFor(p);const cit=citation(p);return `<article class="pub-row"><div><div class="pub-citation"><a href="${esc(p.url||doiUrl(p.doi)||'#')}" target="_blank" rel="noopener">${esc(cit)}</a></div><div class="meta">${esc(sourcesOf(p))}${qual&&qual.issn?' · ISSN '+esc(qual.issn):''}</div></div><aside class="pub-quality"><div class="metric-badges">${badgeHtml(qual,p)}</div><button class="copy-citation" type="button" data-copy="${esc(cit)}">${isEn()?'Copy APA':'Копировать ГОСТ'}</button></aside></article>`}).join('');
  document.querySelectorAll('[data-copy]').forEach(btn=>btn.onclick=()=>navigator.clipboard&&navigator.clipboard.writeText(btn.dataset.copy||''));
}

document.addEventListener('DOMContentLoaded',async()=>{PUBS=await loadPublications();loadScientometrics();try{window.QUALITY=await fetch('data/journals/quality_map.json',{cache:'no-store'}).then(r=>r.json())}catch(e){window.QUALITY={}}const years=[...new Set(PUBS.map(p=>p.year).filter(Boolean))].sort((a,b)=>b-a);document.getElementById('year').innerHTML='<option id="year-all" value="">Все годы</option>'+years.map(y=>`<option>${y}</option>`).join('');['q','year','src'].forEach(id=>document.getElementById(id).addEventListener(id==='q'?'input':'change',render));render()});
window.addEventListener('site:languagechange',()=>{render();renderScientometrics()});
