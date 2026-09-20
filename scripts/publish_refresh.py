#!/usr/bin/env python3
"""Publish validated candidate data, recombining with newer main on a race."""
from __future__ import annotations
import argparse
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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def recombine(candidate, destination):
    from harvest_media_mentions import merge_records, merge_discovery_state, canonical as normalize_url
    from build_public_data import merge_publication_sets
    report_names = {'open': 'harvest_report.json', 'scopus': 'scopus_author_57220956828_access_report.json', 'elibrary': 'browser_fetch_report.json', 'wos': 'harvest_report.json'}
    for folder in ('open', 'scopus', 'elibrary', 'wos', 'processed', 'audit'):
        provider = 'elibrary' if folder == 'processed' else folder
        if provider in report_names:
            previous = read(destination / 'data' / provider / report_names[provider], {})
            incoming = read(candidate / 'data' / provider / report_names[provider], {})
            if (previous.get('last_success_at') or '') > (incoming.get('last_success_at') or ''):
                continue
        if (candidate / 'data' / folder).exists():
            shutil.copytree(candidate / 'data' / folder, destination / 'data' / folder, dirs_exist_ok=True)
    public_path = destination / 'data/public/publications.json'
    write(public_path, merge_publication_sets(read(public_path, []), read(candidate / 'data/public/publications.json', [])))
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

def validate(path, baseline):
    subprocess.run([sys.executable, 'scripts/validate_retention.py', '--baseline-ref', baseline], cwd=path, check=True)
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
