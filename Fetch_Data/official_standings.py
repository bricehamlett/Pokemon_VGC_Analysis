"""Scrape public Standings pages, including their unfiltered embedded JSON.

This is a website adapter, not the documented Play Limitless API. Fail closed
if the site's payload contract changes; never import the visible top-256 table.
"""
import hashlib
import json
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from . import ingestion
except ImportError:
    import ingestion

VERSION = 1
HOST = 'standings.limitlessvgc.com'


def embedded(html, resource):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.select('script[data-sveltekit-fetched]'):
        url = urlparse(script.get('data-url', ''))
        if url.hostname != 'mew.limitlesstcg.com' or url.path != f'/labs/data/vgc/{resource}':
            continue
        wrapper = json.loads(script.string or script.get_text())
        payload = json.loads(wrapper['body'])
        if wrapper['status'] != 200 or payload.get('ok') is not True:
            raise ValueError(f'Standings {resource} returned an error')
        return payload['message']
    raise ValueError(f'Standings page missing embedded {resource}; website may have changed')


class PageClient:
    def __init__(self, cache_dir=None, refresh=False):
        self.cache_dir = Path(cache_dir or Path(__file__).parent / 'data' / 'official_standings')
        self.refresh = refresh
        self.session = requests.Session()

    def get(self, url, cache=False):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != HOST:
            raise ValueError(f'Unexpected standings URL: {url}')
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + '.html')
        if cache and not self.refresh and path.exists():
            return path.read_text()
        for attempt in range(5):
            try:
                response = self.session.get(url, timeout=(10, 45))
                response.raise_for_status()
                response.encoding = "utf-8"
                html = response.text
                # Do not persist an error page or a changed markup contract.
                if cache:
                    embedded(html, 'teamlist')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix('.tmp')
                    temporary.write_text(html)
                    temporary.replace(path)
                time.sleep(0.2)
                return html
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                response = getattr(exc, 'response', None)
                if response is not None and response.status_code != 429 and response.status_code < 500:
                    raise
                if attempt == 4:
                    raise
                retry = response.headers.get('Retry-After', '') if response is not None else ''
                time.sleep(float(retry) if retry.isdigit() else 2 ** attempt)


def name_key(name):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', name.casefold())
                           if not unicodedata.combining(c)).split())


def match_results_players(results_soup, rows):
    # Exact names must be unique. Reordered or shortened names additionally
    # require matching placement and country; never match on surname alone.
    proposals = []
    for player in results_soup.select('[data-rank][data-name]'):
        name = name_key(player['data-name'])
        candidates = [r for r in rows if name_key(r['name']) == name]
        if not candidates:
            def compatible_name(row):
                left, right = name.split(), name_key(row['name']).split()
                short, long = sorted((left, right), key=len)
                iterator = iter(long)
                same_tokens = sorted(left) == sorted(right)
                shortened = all(any(t == token for t in iterator) for token in short)
                return (len(short) >= 2 and (same_tokens or shortened)
                        and bool(player.get('data-country'))
                        and row.get('placement') == int(player['data-rank'])
                        and row.get('country') == player.get('data-country'))
            candidates = [r for r in rows if compatible_name(r)]
        proposals.append((player, candidates))
    claims = {}
    for _, candidates in proposals:
        for row in candidates:
            key = str(row['tp_id'])
            claims[key] = claims.get(key, 0) + 1
    aliases, reviews, blocked = {}, [], set()
    for player, candidates in proposals:
        if len(candidates) == 1 and claims[str(candidates[0]['tp_id'])] == 1:
            aliases[str(candidates[0]['tp_id'])] = player['data-name']
            continue
        # Placement is evidence for quarantine only, never an identity match.
        possible = candidates or [r for r in rows if r.get('placement') == int(player['data-rank'])]
        if not possible:
            # With no way to locate the legacy entrant, only positively matched
            # rows are safe; retain the remaining candidates for later review.
            possible = [r for r in rows if str(r['tp_id']) not in claims]
        ids = [str(r['tp_id']) for r in possible]
        blocked.update(ids)
        name = player['data-name']
        reviews.append({'review_key': 'results:' + hashlib.sha256(name.encode()).hexdigest(),
                        'reason': 'ambiguous_or_unmatched_results_identity',
                        'legacy_names': [name], 'result_row': dict(player.attrs),
                        'candidate_ids': ids})
    return aliases, reviews, blocked


def collect(event, results_soup, standings_url, client=None):
    client = client or PageClient()
    html = client.get(standings_url)
    info = embedded(html, 'tournament')
    rows = embedded(html, 'standings')
    if not info.get('completed'):
        raise ValueError('Standings are not final; retry after the tournament completes')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Empty or malformed full standings')
    ids = [str(row['tp_id']) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate standings participant IDs')
    if len(rows) != int(info['players']) or int(info['players']) != event['event_size']:
        raise ValueError('Standings count disagrees with reported attendance; refusing partial import')
    aliases, reviews, blocked = match_results_players(results_soup, rows)
    teams = []
    base = standings_url.rsplit('/standings', 1)[0]
    for index, row in enumerate(rows, 1):
        old_name = aliases.get(str(row['tp_id']))
        sheet = []
        if row.get('teamlist'):
            sheet_url = base + '/player/' + str(row['tp_id']) + '/teamlist'
            sheet = embedded(client.get(sheet_url, cache=True), 'teamlist')
            if not isinstance(sheet, list):
                raise ValueError('Malformed team sheet')
        pokemon = []
        for p in sheet:
            pokemon.append(ingestion.normalization.pokemon(p))
        teams.append({'identity_pending': str(row['tp_id']) in blocked,
                      'player_name': row['name'], 'legacy_player_name': old_name,
                      'external_player_id': f"{event['event_id']}:standings:{row['tp_id']}",
                      'placement': row.get('placement'), 'country': row.get('country'),
                      'record': {k: row[k] for k in ('wins', 'losses', 'ties') if k in row},
                      'drop_round': row.get('drop_round'), 'pokemon': pokemon,
                      'issues': ['error:disqualified'] if row.get('dqed') else [],
                      'standings_row': row, 'raw_sheet': sheet})
        if index % 100 == 0:
            print(f"Event {event['event_id']}: {index}/{len(rows)} entrants collected", flush=True)
    event['teams'] = teams
    event['identity_reviews'] = reviews
    event['metadata'] = {'official_adapter_version': VERSION, 'standings_url': standings_url,
                         'coverage_scope': 'full_standings', 'standings_tournament': info}
    return event
