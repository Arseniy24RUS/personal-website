#!/usr/bin/env python3
"""Isolated refresh, mandatory validation and explicit provider health.

Collectors never write into the checkout that will be published. Public data
is promoted only after successful schema/content/retention checks.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from report_safety import sanitize, sanitize_public_tree

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ('open', 'harvest_open_sources.py', 'data/open/harvest_report.json', 360),
    ('media', 'harvest_media_mentions.py', 'data/media/harvest_report.json', 1200),
    ('elibrary', 'harvest_elibrary_browser.py', 'data/elibrary/browser_fetch_report.json', 900),
    ('wos', 'harvest_wos_authenticated.py', 'data/wos/harvest_report.json', 900),
    ('scopus', 'harvest_scopus.py', 'data/scopus/scopus_author_57220956828_access_report.json', 360),
]
DERIVED = [
    ('build_public_data.py', 120),
    ('merge_wos_records_into_public_data.py', 120),
    ('translate_publication_titles.py', 600),
    ('enrich_publication_metadata.py', 600),
    ('sanitize_publication_references.py', 120),
]

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize(value), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def prepare(destination: Path):
    if destination.exists():
        raise RuntimeError('Staging destination must be a new directory.')
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    destination.mkdir(parents=True)
    for name in filter(None, tracked):
        source = ROOT / name
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    write(destination / 'data/audit/refresh_run.json', {'attempted_at': now(), 'base_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'state': 'collecting'})
    print('Isolated source and content snapshot prepared.')

def run(script, cwd, timeout, args=()):
    try:
        # Subprocess output is intentionally not copied to public reports. Older
        # parsers can include HTML, response headers or a session URL in errors.
        result = subprocess.run([sys.executable, str(cwd / 'scripts' / script), *args], cwd=cwd,
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        return result.returncode, 'completed' if result.returncode == 0 else 'nonzero_exit'
    except subprocess.TimeoutExpired:
        return 124, 'timeout'

def current_observation(report, previous, attempted):
    """A process exit code is not evidence of a new provider observation."""
    if not isinstance(report, dict) or report == previous:
        return False
    try:
        started = datetime.fromisoformat(attempted.replace('Z', '+00:00'))
        observed = datetime.fromisoformat(report['attempted_at'].replace('Z', '+00:00'))
        if observed < started:
            return False
        if report.get('status') == 'success':
            succeeded = datetime.fromisoformat(report['last_success_at'].replace('Z', '+00:00'))
            return (succeeded >= started and report.get('origin') == 'live'
                    and report.get('complete') is True)
        return report.get('status') in ('partial', 'blocked', 'error')
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


def collect(stage: Path, only: str):
    if os.environ.get('HOME_VPN_REQUIRED') != '1':
        raise RuntimeError('Production collection requires the verified home tunnel.')
    steps = []
    known = {s[0] for s in SOURCES}
    wanted = {name.strip() for name in only.split(',') if name.strip()} if only else known
    if not wanted or wanted - known:
        raise RuntimeError('Select only known collection sources.')
    state = read(stage / 'data/audit/refresh_run.json', {})
    state.update(state='collecting', selected_sources=sorted(wanted))
    write(stage / 'data/audit/refresh_run.json', state)
    for source, script, report_path, timeout in SOURCES:
        if source not in wanted:
            continue
        attempted = now()
        before = read(stage / report_path, {})
        code, reason = run(script, stage, timeout)
        report = read(stage / report_path, {})
        current = current_observation(report, before, attempted)
        if not current or (code and report.get('status') == 'success'):
            reason = reason if code else 'missing_current_source_report'
            report.update(status='error', attempted_at=attempted,
                          last_success_at=before.get('last_success_at'), origin='snapshot',
                          complete=False, reason=reason, record_count=before.get('record_count'))
        stale_providers = False
        for key, provider in report.get('providers', {}).items() if isinstance(report.get('providers'), dict) else []:
            previous = (before.get('providers') or {}).get(key, {})
            if not current_observation(provider, previous, attempted):
                stale_providers = True
                provider.update(status='error', attempted_at=attempted,
                                last_success_at=previous.get('last_success_at'), origin='snapshot',
                                complete=False, reason='missing_current_source_report')
        if stale_providers and report.get('status') == 'success':
            any_success = any(p.get('status') == 'success' for p in report['providers'].values())
            report.update(status='partial' if any_success else 'error', complete=False,
                          origin='snapshot', last_success_at=before.get('last_success_at'),
                          reason='one_or_more_providers_not_current')
        write(stage / report_path, report)
        steps.append({'source': source, 'exit_code': code, 'reason': reason, 'attempted_at': attempted})
        print(f'{source}: {report.get("status", "error")} (exit {code})', flush=True)
    write(stage / 'data/audit/collector_steps.json', {'attempted_at': now(), 'steps': steps})
    for script, timeout in DERIVED:
        code, reason = run(script, stage, timeout)
        if code:
            raise RuntimeError(f'Mandatory derived-data step failed: {script} ({reason}).')
    sanitize_public_tree(stage)
    code, _ = run('audit_refresh_pipeline.py', stage, 120)
    if code not in (0, 2):
        raise RuntimeError('Refreshed data failed structural audit.')
    state = read(stage / 'data/audit/refresh_run.json', {})
    state.update(state='ready', completed_at=now(), selected_sources=sorted(wanted))
    write(stage / 'data/audit/refresh_run.json', state)
    print('Candidate data prepared; publication still requires retention and UI checks.')

def promote(stage: Path, destination: Path = ROOT):
    if read(stage / 'data/audit/refresh_run.json', {}).get('state') != 'ready':
        raise RuntimeError('Only a completely built candidate can be promoted.')
    for name in ('data', 'assets/media/mentions', 'assets/craftum'):
        source = stage / name
        if source.exists():
            shutil.copytree(source, destination / name, dirs_exist_ok=True)
    sanitize_public_tree(destination)
    print('Candidate copied; previous files were retained.')

def health(root: Path = ROOT):
    profile = read(root / 'data/public/profile.json', {})
    sources = profile.get('source_health', {})
    run_state = read(root / 'data/audit/refresh_run.json', {})
    selected = set(run_state.get('selected_sources') or (s[0] for s in SOURCES))
    results = {}
    for key in ('elibrary', 'wos', 'scopus'):
        if key in selected:
            state = sources.get(key, {})
            results[key] = (state.get('status') == 'success' and state.get('origin') == 'live'
                            and state.get('complete') is True and bool(state.get('last_success_at')))
    if 'media' in selected:
        media = read(root / 'data/media/harvest_report.json', {})
        results['media'] = (media.get('status') in ('success', 'partial') and media.get('origin') == 'live'
                            and bool(media.get('last_success_at'))
                            and media.get('required_sources_ok', media.get('status') == 'success') is True)
    if 'open' in selected:
        opening = read(root / 'data/open/harvest_report.json', {})
        results['open'] = (opening.get('status') == 'success' and opening.get('origin') == 'live'
                           and opening.get('complete') is True and bool(opening.get('last_success_at')))
    if run_state.get('state') not in (None, 'ready'):
        results['pipeline_completed'] = False
    report = {'checked_at': now(), 'healthy': all(results.values()), 'checks': results}
    write(root / 'data/audit/source_health_check.json', report)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    lines = ['### Source collection', '', '| Source | Fresh collection |', '|---|---|']
    lines += [f'| {key} | {"PASS" if ok else "NEEDS ATTENTION — previous data preserved"} |' for key, ok in results.items()]
    print('\n'.join(lines))
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    return 0 if report['healthy'] else 2

def diagnostics(stage: Path, destination: Path):
    paths = [item[2] for item in SOURCES] + ['data/audit/refresh_run.json', 'data/audit/collector_steps.json', 'data/audit/refresh_pipeline_audit.json', 'data/audit/retention_report.json']
    for name in paths:
        path = stage / name
        if path.exists():
            write(destination / name, read(path, {}))
    print('Only sanitized diagnostic JSON exported; sessions and raw responses excluded.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'collect', 'promote', 'health', 'diagnostics'])
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--only', default='')
    args = parser.parse_args()
    if args.command == 'prepare': prepare(args.stage.resolve())
    elif args.command == 'collect': collect(args.stage.resolve(), args.only)
    elif args.command == 'promote': promote(args.stage.resolve())
    elif args.command == 'diagnostics': diagnostics(args.stage.resolve(), args.output.resolve())
    else: return health(args.stage.resolve() if args.stage else ROOT)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        # Exceptions here are generated internally, never raw provider errors.
        print(f'Refresh stopped: {type(exc).__name__}: {sanitize(str(exc))}', file=sys.stderr)
        sys.exit(1)
