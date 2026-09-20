#!/usr/bin/env python3
"""Publish validated candidate data, recombining with newer main on a race."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()

def read(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default

def records(value):
    return value if isinstance(value, list) else value.get('records', [])

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (TypeError, ValueError):
        return float('-inf')


def merge_source_report(previous, incoming, record_count=None):
    """Attempt diagnostics and successful observations have separate clocks."""
    reports = [report for report in (previous, incoming) if report]
    if not reports:
        return {}
    # Reports have second resolution. On a tie, retain failure rather than claim
    # that an indistinguishable success superseded it.
    latest = max(reports, key=lambda report: (
        timestamp(report.get('attempted_at') or report.get('generated_at')),
        report.get('status') != 'success' or report.get('complete') is not True,
    ))
    merged = dict(latest)
    successes = [report.get('last_success_at') for report in reports if report.get('last_success_at')]
    merged['last_success_at'] = max(successes, key=timestamp) if successes else None
    if record_count is not None:
        merged['record_count'] = record_count
    return merged


def copy_snapshot(source, destination, incoming_is_newer, excluded=()):
    if not source.exists():
        return
    for path in source.rglob('*'):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_file() and relative.as_posix() not in excluded and (incoming_is_newer or not target.exists()):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def merge_open_sources(candidate, destination):
    from harvest_open_sources import (
        normalize_orcid_works, normalize_openalex_works, normalize_crossref_works,
        dedupe_records, doi_norm, normalize_title,
    )
    output = destination / 'data/open'
    previous = read(output / 'harvest_report.json', {})
    incoming = read(candidate / 'data/open/harvest_report.json', {})
    if not previous and not incoming and not (candidate / 'data/open').exists():
        return
    prior_aggregate = read(output / 'open_publications.json', {})
    incoming_aggregate = read(candidate / 'data/open/open_publications.json', {})
    providers, observed = {}, []
    files = {'orcid': 'orcid_works.json', 'openalex_author': 'openalex_author.json',
             'openalex_works': 'openalex_works.json', 'crossref': 'crossref_works.json'}
    for provider, filename in files.items():
        old = (previous.get('providers') or {}).get(provider, {})
        new = (incoming.get('providers') or {}).get(provider, {})
        target = output / filename
        source = candidate / 'data/open' / filename
        if source.exists() and (not target.exists() or timestamp(new.get('last_success_at')) > timestamp(old.get('last_success_at'))):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        payload = read(target, None)
        rows = None
        if payload is not None:
            if provider == 'orcid':
                identifier = str(payload.get('path', '')).strip('/').split('/')[0] or None
                rows = normalize_orcid_works(payload, identifier)
            elif provider == 'openalex_works':
                rows = normalize_openalex_works(payload)
            elif provider == 'crossref':
                rows = normalize_crossref_works(payload)
            else:
                rows = []  # Author metadata is not an additional publication.
            observed.extend(rows)
        state = merge_source_report(old, new, len(rows) if rows is not None else None)
        if state:
            providers[provider] = state
    aggregate = dedupe_records(observed)
    def identity(row):
        return doi_norm(row.get('doi')) or (normalize_title(row.get('title')).lower(), row.get('year'))
    seen = {identity(row) for row in aggregate}
    for row in records(prior_aggregate) + records(incoming_aggregate):
        if identity(row) not in seen:
            aggregate.append(row)
            seen.add(identity(row))
    report = merge_source_report(previous, incoming, len(aggregate))
    report['providers'] = providers
    report['records_total_after_dedupe'] = len(aggregate)
    report['records_total_before_dedupe'] = len(observed)
    if providers and any(p.get('status') != 'success' or p.get('complete') is not True for p in providers.values()):
        report['complete'] = False
        if report.get('status') == 'success':
            report.update(status='partial', origin='snapshot', reason='concurrent_provider_failure')
    write(output / 'harvest_report.json', report)
    write(output / 'open_publications.json', {'generated_at': report.get('attempted_at') or report.get('generated_at'), 'records': aggregate})


def seed_newer_metric_baseline(destination, source_reports):
    """Adopt verified newer values while leaving the newer failure report intact.

    The public builder normally retains previous values on a failed attempt. A
    race can bring in an intermediate successful snapshot that was absent from
    main, so advance that previous-value baseline before the ordinary rebuild.
    """
    from build_public_data import build_scientometrics
    path = destination / 'data/public/profile.json'
    profile = read(path, {})
    old_metrics = profile.get('scientometrics') or {}
    states = {}
    names = {'elibrary': 'rinc', 'scopus': 'scopus', 'wos': 'wos'}
    for provider, state in source_reports.items():
        old = (old_metrics.get('sources') or {}).get(names[provider], {})
        if timestamp(state.get('last_success_at')) > timestamp(old.get('last_success_at')):
            states[provider] = {**state, 'status': 'success', 'origin': 'live', 'complete': True}
    if not states:
        return
    calculated = build_scientometrics(
        [], read(destination / 'data/elibrary/profile_metrics.json', {}),
        read(destination / 'data/scopus/scopus_author_57220956828_metrics.json', {}),
        read(destination / 'data/wos/profile_metrics.json', {}), health=states, previous=old_metrics,
    )
    baseline = dict(old_metrics)
    baseline['sources'] = dict(old_metrics.get('sources') or {})
    for provider in states:
        baseline['sources'][names[provider]] = calculated['sources'][names[provider]]
    profile['scientometrics'] = baseline
    write(path, profile)


def apply_newer_citation_observations(publications, destination, source_reports):
    """Use only verified snapshot epochs, independent of later attempt failure."""
    import build_public_data as builder
    profile = read(destination / 'data/public/profile.json', {})
    previous_data = builder.DATA
    try:
        builder.DATA = destination / 'data'
        for provider, report in source_reports.items():
            column = 'rinc' if provider == 'elibrary' else provider
            prior = ((profile.get('source_health') or {}).get(provider) or
                     ((profile.get('scientometrics') or {}).get('sources') or {}).get(column) or {})
            if timestamp(report.get('last_success_at')) <= timestamp(prior.get('last_success_at')):
                continue
            if provider == 'elibrary':
                observations = {str(row.get('elibrary_item_id')): row.get('rinc_citations')
                                for row in read(destination / 'data/processed/elibrary_publications.json', [])
                                if row.get('elibrary_item_id') and row.get('rinc_citations') is not None}
                for row in publications:
                    key = str(row.get('elibrary_item_id'))
                    if key in observations:
                        row['rinc_citations'] = observations[key]
            elif provider == 'scopus':
                works = read(destination / 'data/scopus/scopus_author_57220956828_works.json', [])
                builder.merge_scopus(publications, works.get('works', []) if isinstance(works, dict) else works, fresh=True)
            else:
                payload = read(destination / 'data/wos/profile_metrics.json', {})
                builder.merge_wos(publications, payload.get('records', []), fresh=True)
    finally:
        builder.DATA = previous_data
    return publications

def recombine(candidate, destination):
    from harvest_media_mentions import merge_records, merge_discovery_state, canonical as normalize_url
    from build_public_data import merge_publication_sets
    report_names = {'scopus': 'scopus_author_57220956828_access_report.json', 'elibrary': 'browser_fetch_report.json', 'wos': 'harvest_report.json'}
    merged_reports = {}
    for provider, filename in report_names.items():
        previous = read(destination / 'data' / provider / filename, {})
        incoming = read(candidate / 'data' / provider / filename, {})
        incoming_is_newer = timestamp(incoming.get('last_success_at')) > timestamp(previous.get('last_success_at'))
        copy_snapshot(candidate / 'data' / provider, destination / 'data' / provider, incoming_is_newer, (filename,))
        if provider == 'elibrary':
            copy_snapshot(candidate / 'data/processed', destination / 'data/processed', incoming_is_newer)
            payload = read(destination / 'data/processed/elibrary_publications.json', None)
        elif provider == 'scopus':
            payload = read(destination / 'data/scopus/scopus_author_57220956828_works.json', None)
            if isinstance(payload, dict):
                payload = payload.get('works', [])
        else:
            payload = read(destination / 'data/wos/profile_metrics.json', None)
            if isinstance(payload, dict):
                payload = payload.get('records', [])
        report = merge_source_report(previous, incoming, len(payload) if isinstance(payload, list) else None)
        if report:
            write(destination / 'data' / provider / filename, report)
            merged_reports[provider] = report
    merge_open_sources(candidate, destination)
    if (candidate / 'data/audit').exists():
        shutil.copytree(candidate / 'data/audit', destination / 'data/audit', dirs_exist_ok=True)
    public_path = destination / 'data/public/publications.json'
    merged_publications = merge_publication_sets(read(public_path, []), read(candidate / 'data/public/publications.json', []))
    write(public_path, apply_newer_citation_observations(merged_publications, destination, merged_reports))
    seed_newer_metric_baseline(destination, merged_reports)
    for name in ('published.json', 'news_mentions.json', 'published-fallback.json'):
        path = destination / 'data/media' / name
        previous = read(path, {})
        incoming = read(candidate / 'data/media' / name, {})
        merged = merge_records(records(previous), records(incoming))
        if isinstance(incoming, list):
            payload = merged
        else:
            payload = dict(incoming, records=merged)
        write(path, payload)
    current_state = read(destination / 'data/media/discovery_state.json', {})
    incoming_state = read(candidate / 'data/media/discovery_state.json', {})
    combined_state = merge_discovery_state(current_state, incoming_state)
    write(destination / 'data/media/discovery_state.json', combined_state)
    for name in ('harvest_report.json', 'live_discovery_smoke.json'):
        incoming = read(candidate / 'data/media' / name, {})
        existing = read(destination / 'data/media' / name, {})
        if incoming and (incoming.get('attempted_at') or '') >= (existing.get('attempted_at') or ''):
            write(destination / 'data/media' / name, incoming)
    for name in ('media_mentions.json', 'publications.json'):
        path = destination / 'data/admin_queue' / name
        old = read(path, [])
        new = read(candidate / 'data/admin_queue' / name, [])
        by_key = {str(row.get('url') or row.get('doi') or row.get('id') or json.dumps(row, sort_keys=True)): row for row in new}
        by_key.update({str(row.get('url') or row.get('doi') or row.get('id') or json.dumps(row, sort_keys=True)): row for row in old})
        write(path, list(by_key.values()))
    published = records(read(destination / 'data/media/published.json', {}))
    published_urls = {normalize_url(row.get('url', '')) for row in published}
    queue = merge_records(
        read(destination / 'data/admin_queue/media_mentions.json', []),
        records(read(destination / 'data/media/rejected_or_low_confidence.json', {})),
    )
    queue = [row for row in queue if normalize_url(row.get('url', '')) not in published_urls]
    write(destination / 'data/admin_queue/media_mentions.json', queue)
    write(destination / 'data/media/rejected_or_low_confidence.json', {'records': queue})
    report_path = destination / 'data/media/harvest_report.json'
    report = read(report_path, {})
    report.update(record_count=len(published), published=len(published), pending=len(combined_state.get('pending', {})))
    if report['pending']:
        report['complete'] = False
        if report.get('status') == 'success':
            report.update(status='partial', reason='concurrent_pending_backlog')
    write(report_path, report)
    for name in ('assets/media/mentions', 'assets/craftum'):
        if (candidate / name).exists():
            for source in (candidate / name).rglob('*'):
                target = destination / name / source.relative_to(candidate / name)
                if source.is_file() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    # Current curated bibliographic fields and gallery/RISS content are kept.
    for script in ('build_public_data.py', 'merge_wos_records_into_public_data.py', 'sanitize_publication_references.py', 'report_safety.py'):
        subprocess.run([sys.executable, str(destination / 'scripts' / script)], cwd=destination, check=True)
    audit = subprocess.run([sys.executable, str(destination / 'scripts/audit_refresh_pipeline.py')], cwd=destination)
    if audit.returncode not in (0, 2):
        raise RuntimeError('Recombined data failed structural audit.')

def validate(path, baseline):
    subprocess.run([sys.executable, 'scripts/validate_retention.py', '--baseline-ref', baseline,
                    '--report', 'data/audit/retention_report.json'], cwd=path, check=True)
    subprocess.run([sys.executable, 'scripts/check_seo.py'], cwd=path, check=True)
    git('diff', '--check', cwd=path)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    args = parser.parse_args()
    baseline = git('rev-parse', args.baseline_ref)
    validate(ROOT, baseline)
    result_sha, changed = baseline, False
    for attempt in range(3):
        git('fetch', 'origin', 'main')
        latest = git('rev-parse', 'origin/main')
        changed_code = git('diff', '--name-only', baseline, latest, '--', 'scripts', 'config', '.github', '*.html', 'assets/*.js')
        if changed_code:
            raise RuntimeError('Code/configuration changed during collection. Rerun against latest main; candidate retained.')
        with tempfile.TemporaryDirectory(prefix='portfolio-publish-') as directory:
            target = Path(directory) / 'checkout'
            git('worktree', 'add', '--detach', str(target), latest)
            try:
                if latest == baseline:
                    for name in ('data', 'assets/media/mentions', 'assets/craftum'):
                        if (ROOT / name).exists():
                            shutil.copytree(ROOT / name, target / name, dirs_exist_ok=True)
                else:
                    recombine(ROOT, target)
                validate(target, latest)
                git('config', 'user.name', 'github-actions[bot]', cwd=target)
                git('config', 'user.email', 'github-actions[bot]@users.noreply.github.com', cwd=target)
                git('add', 'data/', 'assets/media/mentions/', 'assets/craftum/', cwd=target)
                if not git('diff', '--cached', '--name-only', cwd=target):
                    result_sha = latest
                    break
                git('commit', '-m', 'chore: refresh validated portfolio data', cwd=target)
                result_sha = git('rev-parse', 'HEAD', cwd=target)
                push = subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=target, capture_output=True, text=True)
                if push.returncode == 0:
                    # Verification must compare the data actually pushed after any remerge.
                    for name in ('data', 'assets/media/mentions', 'assets/craftum'):
                        if (target / name).exists():
                            shutil.copytree(target / name, ROOT / name, dirs_exist_ok=True)
                    changed = True
                    break
                if attempt == 2:
                    raise RuntimeError('Main kept changing; safe publication aborted without a forced push.')
            finally:
                git('worktree', 'remove', '--force', str(target))
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a', encoding='utf-8') as f:
            f.write(f'changed={str(changed).lower()}\nsha={result_sha}\n')
    print(f'Validated data publication: {result_sha}; changed={changed}')

if __name__ == '__main__':
    main()
