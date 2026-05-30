#!/usr/bin/env python3
from pathlib import Path
import csv, json, re
from datetime import datetime, timezone
try:
    import yaml
except Exception:
    yaml = None

DATA = Path('data')
PUBLIC = DATA / 'public'
PUBLIC.mkdir(parents=True, exist_ok=True)

def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default

def profile():
    if yaml and Path('config/profile.yml').exists():
        return (yaml.safe_load(Path('config/profile.yml').read_text(encoding='utf-8')) or {}).get('profile', {})
    return {'display_name_ru':'Ситковский Арсений Михайлович','display_name_en':'Arseniy M. Sitkovskiy','identifiers':{'scopus_author_id':'57220956828'}}

def nt(s):
    return re.sub(r'[^a-zа-я0-9]+',' ',(s or '').lower().replace('ё','е')).strip()

def nd(doi):
    if not doi: return None
    return re.sub(r'^https?://(dx\.)?doi\.org/','',str(doi).strip().lower()) or None

def addsrc(p, s):
    p.setdefault('sources', ['elibrary'])
    if s and s not in p['sources']:
        p['sources'].append(s)

def load_elib():
    j = DATA/'processed/elibrary_publications.json'
    if j.exists():
        rows = read_json(j, [])
        for p in rows: p.setdefault('sources', ['elibrary'])
        return rows
    rows=[]; t=DATA/'elibrary/publications.tsv'
    if not t.exists(): return rows
    for r in csv.reader(t.open(encoding='utf-8'), delimiter='\t'):
        if len(r)<8: continue
        m = re.search(r'id=(\d+)', r[7] or '')
        rows.append({'source':'elibrary_rinc_tsv','number':int(r[0]) if r[0].isdigit() else None,'elibrary_item_id':m.group(1) if m else None,'year':int(r[1]) if r[1].isdigit() else None,'rinc_citations':int(r[2]) if r[2].isdigit() else 0,'title':r[3],'authors_raw':r[4],'venue':r[5] or None,'pages':r[6] or None,'doi':None,'url':r[7] or None,'sources':['elibrary']})
    return rows

def indexes(records):
    return ({str(p.get('elibrary_item_id')):p for p in records if p.get('elibrary_item_id')}, {nt(p.get('title')):p for p in records if p.get('title')}, {(nt(p.get('title')),str(p.get('year') or '')):p for p in records if p.get('title')}, {nd(p.get('doi')):p for p in records if nd(p.get('doi'))})

def merge_scopus(canon, works):
    curated=read_json(DATA/'curation/scopus_elibrary_map.json', {})
    by_item, by_title, by_ty, by_doi = indexes(canon)
    added=0
    for w in works or []:
        eid=w.get('eid'); doi=nd(w.get('doi')); target=None
        if eid in curated: target=by_item.get(str(curated[eid].get('elibrary_item_id')))
        if target is None and doi: target=by_doi.get(doi)
        if target is None: target=by_title.get(nt(w.get('title')))
        if target is None: target=by_ty.get((nt(w.get('title')), str(w.get('year') or w.get('cover_date') or '')[:4]))
        if target:
            addsrc(target,'scopus'); target['scopus']=w
            if doi and not target.get('doi'): target['doi']=doi
        else:
            rec={'source':'scopus_api_auto','number':None,'elibrary_item_id':None,'year':int(str(w.get('year') or w.get('cover_date') or '')[:4]) if str(w.get('year') or w.get('cover_date') or '')[:4].isdigit() else None,'rinc_citations':0,'title':w.get('title'),'authors_raw':w.get('creator') or '','venue':w.get('journal_or_source') or w.get('source_title'),'pages':None,'doi':doi,'url':w.get('url') or (f"https://www.scopus.com/record/display.uri?eid={eid}" if eid else None),'sources':['scopus'],'scopus':w,'auto_accept_reason':'author-scoped Scopus AU-ID record'}
            canon.append(rec); added+=1
    return added

def merge_open(canon, records):
    curated=read_json(DATA/'curation/open_elibrary_map.json', {})
    by_item, by_title, by_ty, by_doi = indexes(canon)
    enriched=added=0
    for r in records or []:
        doi=nd(r.get('doi')); title=nt(r.get('title')); target=None
        if doi in curated: target=by_item.get(str(curated[doi].get('elibrary_item_id')))
        if target is None and ('title:'+title) in curated: target=by_item.get(str(curated['title:'+title].get('elibrary_item_id')))
        if target is None and doi: target=by_doi.get(doi)
        if target is None: target=by_ty.get((title, str(r.get('year') or ''))) or by_title.get(title)
        src=r.get('source') or 'open_api'
        if target:
            addsrc(target, src); target.setdefault('open_sources',[]).append(r)
            if doi and not target.get('doi'): target['doi']=doi
            if r.get('venue') and not target.get('venue'): target['venue']=r.get('venue')
            enriched+=1
        else:
            rec={'source':src+'_auto','number':None,'elibrary_item_id':None,'year':int(r.get('year')) if str(r.get('year') or '').isdigit() else None,'rinc_citations':0,'title':r.get('title'),'authors_raw':'','venue':r.get('venue'),'pages':None,'doi':doi,'url':r.get('url') or r.get('landing_page_url'),'sources':[src],'open_sources':[r],'auto_accept_reason':'author-scoped ORCID/OpenAlex/Crossref record'}
            canon.append(rec); added+=1
            if doi: by_doi[doi]=rec
            if title: by_title[title]=rec; by_ty[(title,str(rec.get('year') or ''))]=rec
    return enriched, added

def write_tsv(pubs):
    with (PUBLIC/'publications.tsv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f,delimiter='\t'); w.writerow(['number','year','rinc_citations','scopus_citations','title','authors','venue','pages','doi','url','sources'])
        for p in pubs: w.writerow([p.get('number'),p.get('year'),p.get('rinc_citations',0),(p.get('scopus') or {}).get('cited_by_count',''),p.get('title'),p.get('authors_raw'),p.get('venue'),p.get('pages',''),p.get('doi',''),p.get('url'),','.join(p.get('sources',[]))])

def empty_queue():
    q=DATA/'admin_queue'; q.mkdir(parents=True, exist_ok=True)
    (q/'publications.json').write_text('[]\n',encoding='utf-8')
    with (q/'publications.csv').open('w',encoding='utf-8-sig',newline='') as f: csv.writer(f).writerow(['id','entity_type','action','confidence','reason','title','year','doi','source'])

def main():
    prof=profile(); ids=prof.get('identifiers',{}); sid=ids.get('scopus_author_id','57220956828')
    canon=load_elib(); scopus_metrics=read_json(DATA/f'scopus/scopus_author_{sid}_metrics.json', None); scopus_works=read_json(DATA/f'scopus/scopus_author_{sid}_works.json', [])
    scopus_added=merge_scopus(canon, scopus_works)
    open_records=(read_json(DATA/'open/open_publications.json', {}) or {}).get('records', [])
    open_enriched, open_added = merge_open(canon, open_records)
    public_profile={'generated_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat(),'name_ru':prof.get('display_name_ru',''),'name_en':prof.get('display_name_en',''),'identifiers':ids,'elibrary_metrics':read_json(DATA/'elibrary/metrics.json',{}),'elibrary_profile_metrics':read_json(DATA/'elibrary/profile_metrics.json',{}),'wos_profile_metrics':read_json(DATA/'wos/profile_metrics.json',{}),'scopus_metrics':scopus_metrics,'open_sources_report':read_json(DATA/'open/harvest_report.json',{}),'canonical_publications_count':len(canon),'scopus_enriched_publications_count':sum(1 for p in canon if 'scopus' in p.get('sources',[])),'scopus_auto_added_publications_count':scopus_added,'open_sources_records_count':len(open_records),'open_sources_enriched_publications_count':open_enriched,'open_sources_auto_added_publications_count':open_added,'admin_queue_size':0}
    (PUBLIC/'profile.json').write_text(json.dumps(public_profile,ensure_ascii=False,indent=2),encoding='utf-8')
    (PUBLIC/'publications.json').write_text(json.dumps(canon,ensure_ascii=False,indent=2),encoding='utf-8')
    write_tsv(canon); empty_queue()
    print(f'Built public data: {len(canon)} canonical publications; queue disabled')
if __name__=='__main__': main()
