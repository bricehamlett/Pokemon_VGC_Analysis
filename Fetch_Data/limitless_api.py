"""API ingestion: audit by default; --write opts into PostgreSQL imports."""
import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
import psycopg2

try:
    from . import ingestion, pokemon_table, terminal_output
except ImportError:  # python Fetch_Data/limitless_api.py
    import ingestion
    import pokemon_table
    import terminal_output


BASE_URL = 'https://play.limitlesstcg.com/api'


class ApiClient:
    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent': 'PokemonVGCAnalysis/1.0'})
        self.sleep = sleep

    def pause(self, delay, reason):
        if delay >= 1:
            print(terminal_output.wait_summary(reason, delay), file=sys.stderr, flush=True)
        self.sleep(delay)

    def get(self, path, **params):
        for attempt in range(5):
            try:
                response = self.session.get(BASE_URL + path, params=params, timeout=(10, 45))
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 4:
                    raise
                self.pause(2 ** attempt, 'connection_retry')
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 4:
                    response.raise_for_status()
                wait = response.headers.get('Retry-After')
                try:
                    delay = float(wait)
                except (TypeError, ValueError):
                    try:
                        delay = (parsedate_to_datetime(wait) - datetime.now(timezone.utc)).total_seconds()
                    except (TypeError, ValueError):
                        delay = 2 ** attempt
                self.pause(max(0, delay), 'rate_limit_or_server_retry')
                continue
            response.raise_for_status()
            # Requests are sequential. Respect remaining/reset hints if supplied.
            remaining = response.headers.get('RateLimit-Remaining', response.headers.get('X-RateLimit-Remaining'))
            reset = response.headers.get('RateLimit-Reset', response.headers.get('X-RateLimit-Reset'))
            delay = 0.25
            # Current Limitless responses use a structured field, e.g.
            # RateLimit: "50-in-5min"; r=0; t=284
            quota = response.headers.get('RateLimit', '')
            quota_remaining = re.search(r'(?:^|[;,]\s*)r=(\d+)', quota)
            quota_reset = re.search(r'(?:^|[;,]\s*)t=(\d+)', quota)
            if quota_remaining and quota_reset and int(quota_remaining.group(1)) == 0:
                delay = max(delay, int(quota_reset.group(1)) + 1)
            if remaining == '0' and reset:
                try:
                    value = float(reset)
                    delay = max(delay, value - time.time() if value > 1_000_000_000 else value)
                except ValueError:
                    pass
            self.pause(delay, 'rate_limit_reset')
            return response.json()
        raise RuntimeError('Request retries exhausted')


def choose_format(games, requested):
    formats = next(g['formats'] for g in games if g['id'] == 'VGC')
    if requested in formats:
        return requested, formats[requested]
    matches = [(key, name) for key, name in formats.items()
               if name.endswith('Regulation ' + requested) or name.endswith('Regulation Set ' + requested)]
    if len(matches) != 1:
        raise ValueError(f'Unknown or ambiguous format {requested!r}; choose one of {list(formats)}')
    return matches[0]


def choose_formats(games, requested=None):
    """All API-advertised formats by default; explicit selections are repeatable."""
    if not requested or requested == ['all']:
        return list(next(g['formats'] for g in games if g['id'] == 'VGC').items())
    if 'all' in requested:
        raise ValueError('Use --regulation all alone, or specify individual regulations')
    return list(dict(choose_format(games, name) for name in requested).items())


def discover(client, fmt, limit, before, after=None, min_players=2,
             skip_ids=None, refresh_since=None, stats=None):
    seen = set()
    skip_ids = skip_ids or set()
    stats = stats if stats is not None else {}
    count = 0
    page = 1
    while limit is None or count < limit:
        events = client.get('/tournaments', game='VGC', format=fmt, limit=50, page=page)
        if not events:
            return
        new = 0
        for event in events:
            if event['id'] in seen:
                continue
            seen.add(event['id'])
            new += 1
            stats['discovered'] = stats.get('discovered', 0) + 1
            day = datetime.fromisoformat(event['date'].replace('Z', '+00:00')).date()
            if day >= before or (after and day < after) or event['players'] < min_players:
                continue
            if event['id'] in skip_ids and (refresh_since is None or day < refresh_since):
                stats['skipped_existing'] = stats.get('skipped_existing', 0) + 1
                continue
            yield event['id']
            count += 1
            if limit is not None and count >= limit:
                stats['capped'] = True
                return
        if not new:
            raise ValueError('API pagination repeated a page without new event IDs')
        page += 1


def write_snapshot(cache_dir, event_id, payload):
    """Immutable timestamped snapshots; never reuse stale responses silently."""
    directory = cache_dir / 'play_limitless' / event_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--regulation', action='append', help='Repeatable label/code; default: all API formats')
    parser.add_argument('--max-events', type=int, help='Optional cap per format; default: no cap')
    parser.add_argument('--refresh-days', type=int, default=14,
                        help='Revisit imported events started within this many days; 0 skips all existing events')
    parser.add_argument('--refresh-all', action='store_true', help='Re-fetch every selected event, including old imports')
    parser.add_argument('--min-players', type=int, default=2)
    parser.add_argument('--before', type=date.fromisoformat, default=datetime.now(timezone.utc).date(),
                        help='Exclusive UTC start-date cutoff; excludes today by default')
    parser.add_argument('--after', type=date.fromisoformat, help='Inclusive UTC start-date cutoff')
    parser.add_argument('--event-id', action='append', help='Specific event ID; repeat for multiple events')
    parser.add_argument('--cache-dir', type=Path, default=Path(__file__).parent / 'data/raw')
    parser.add_argument('--without-pairings', action='store_true')
    parser.add_argument('--write', action='store_true', help='Apply additive migration and import into configured database')
    parser.add_argument('--env-file', type=Path, help='Optional dotenv file for PostgreSQL connection settings')
    parser.add_argument('--report', type=Path, help='Run report path; defaults to timestamped file alongside raw cache')
    args = parser.parse_args(argv)
    if (args.max_events is not None and args.max_events < 1) or args.min_players < 1:
        parser.error('--max-events and --min-players must be positive')
    if args.refresh_days < 0:
        parser.error('--refresh-days must be nonnegative')
    if args.after and args.after >= args.before:
        parser.error('--after must precede --before')
    if args.env_file:
        from dotenv import load_dotenv
        if not args.env_file.is_file():
            parser.error('--env-file does not exist')
        load_dotenv(args.env_file, override=False)
    client = ApiClient()
    games = client.get('/games')
    formats = choose_formats(games, args.regulation)
    format_names = dict(formats)
    conn = None
    failures = 0
    processed = 0
    started = datetime.now(timezone.utc)
    run_report = {'started_at': started.isoformat(), 'status': 'running', 'mode': 'import' if args.write else 'audit',
                  'formats': {}, 'events': [], 'errors': []}
    report_path = args.report or (args.cache_dir.parent / 'runs' / (started.strftime('%Y%m%dT%H%M%S%fZ') + '.json'))
    try:
        if args.write:
            conn = pokemon_table.get_connection()
            ingestion.migrate(conn)
        known = ingestion.imported_api_ids(conn, not args.without_pairings) if conn and not args.refresh_all else set()
        refresh_since = started.date() - timedelta(days=args.refresh_days) if args.refresh_days else None
        # Explicit event IDs always fetch, for targeted repair or inspection.
        if args.event_id:
            batches = [(None, list(dict.fromkeys(args.event_id)))]
        else:
            batches = []
            for fmt, name in formats:
                stats = {'name': name, 'discovered': 0, 'skipped_existing': 0, 'processed': 0, 'failed': 0}
                run_report['formats'][fmt] = stats
                batches.append((fmt, discover(client, fmt, args.max_events, args.before, args.after,
                                               args.min_players, known, refresh_since, stats)))
        for expected_format, event_ids in batches:
            try:
                if expected_format:
                    print(
                        f"\n[FORMAT] {expected_format} | {format_names[expected_format]}",
                        flush=True,
                    )
                for event_id in event_ids:
                    fmt = expected_format
                    try:
                        if not event_id.isalnum():
                            raise ValueError('Invalid event ID')
                        details = client.get(f'/tournaments/{event_id}/details')
                        fmt = details['format']
                        if details['game'] != 'VGC' or fmt not in format_names or (expected_format and fmt != expected_format):
                            raise ValueError('Event does not match the requested game/format')
                        stats = run_report['formats'].setdefault(fmt, {'name': format_names[fmt], 'processed': 0, 'failed': 0})
                        day = datetime.fromisoformat(details['date'].replace('Z', '+00:00')).date()
                        if day >= args.before or (args.after and day < args.after):
                            raise ValueError('Event falls outside the requested date window')
                        standings = client.get(f'/tournaments/{event_id}/standings')
                        pairings = None if args.without_pairings else client.get(f'/tournaments/{event_id}/pairings')
                        format_name = format_names[fmt]
                        payload = {'details': details, 'standings': standings, 'pairings': pairings, 'format_name': format_name}
                        path = write_snapshot(args.cache_dir, event_id, payload)
                        event = ingestion.normalize_api(details, standings, pairings, format_name)
                        report = ingestion.load_event(conn, event) if conn else ingestion.audit(event)
                        report.update(mode='import' if conn else 'audit', snapshot=str(path), api_format=fmt)
                        print(terminal_output.event_summary(report), flush=True)
                        run_report['events'].append(report)
                        stats['processed'] += 1
                        for key in ('returned_players', 'complete', 'partial', 'invalid', 'missing', 'placement_candidates',
                                    'imported_sheets', 'unresolved', 'conflicts'):
                            stats[key] = stats.get(key, 0) + report.get(key, 0)
                        processed += 1
                    except (requests.RequestException, psycopg2.Error, ValueError, KeyError, TypeError) as exc:
                        if conn:
                            conn.rollback()
                        failures += 1
                        error = {'event_id': event_id, 'format': fmt, 'error': str(exc)}
                        run_report['errors'].append(error)
                        if fmt in run_report['formats']:
                            run_report['formats'][fmt]['failed'] += 1
                        print(terminal_output.error_summary(error), flush=True)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                # A discovery failure in one format must not suppress the others.
                failures += 1
                error = {'format': expected_format, 'stage': 'discovery', 'error': str(exc)}
                run_report['errors'].append(error)
                if expected_format in run_report['formats']:
                    run_report['formats'][expected_format]['failed'] += 1
                print(terminal_output.error_summary(error), flush=True)
        if conn:
            run_report['database_coverage'] = ingestion.coverage(conn)
        run_report['status'] = 'completed_with_errors' if failures else 'completed'
    finally:
        if run_report['status'] == 'running':
            run_report['status'] = 'aborted'
        run_report.update(processed=processed, failed=failures, finished_at=datetime.now(timezone.utc).isoformat())
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(run_report, indent=2, ensure_ascii=False), encoding='utf-8')
        finally:
            if conn:
                conn.close()
    print(terminal_output.final_summary(processed, failures, report_path, args.write))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
