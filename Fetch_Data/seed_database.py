"""Resumable PokeAPI reference seeding with cached responses and explicit progress."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import requests

try:
    from . import pokemon_table
except ImportError:
    import pokemon_table

BASE = 'https://pokeapi.co/api/v2'
STAGES = {'pokemon': 'pokemon', 'moves': 'move', 'abilities': 'ability', 'items': 'item'}
CACHE = Path(__file__).parent / 'data/pokeapi'


class PokeApiClient:
    def __init__(self, cache_dir=CACHE, session=None, sleep=time.sleep, refresh=False):
        self.cache_dir = Path(cache_dir)
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent': 'PokemonVGCAnalysis/1.0'})
        self.sleep = sleep
        self.refresh = refresh

    def get(self, url, max_age=None):
        if urlparse(url).hostname != 'pokeapi.co':
            raise ValueError(f'Unexpected PokeAPI host: {url}')
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if not self.refresh and path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
            try:
                return json.loads(path.read_text())
            except (ValueError, OSError):
                pass  # An incomplete cache file is re-fetched.
        for attempt in range(5):
            try:
                response = self.session.get(url, timeout=(10, 45))
                response.raise_for_status()
                payload = response.json()
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(payload), encoding='utf-8')
                temporary.replace(path)
                return payload
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                retryable = not isinstance(exc, requests.HTTPError) or exc.response.status_code == 429 or exc.response.status_code >= 500
                if not retryable or attempt == 4:
                    raise
                delay = 2 ** attempt
                if isinstance(exc, requests.HTTPError):
                    try:
                        delay = max(delay, float(exc.response.headers.get('Retry-After', 0)))
                    except ValueError:
                        pass
                print(f'PokeAPI retry {attempt + 1}/4 in {delay:g}s: {url} ({type(exc).__name__})', flush=True)
                self.sleep(delay)
        raise RuntimeError('PokeAPI retry limit reached')

    def resources(self, endpoint):
        url = f'{BASE}/{endpoint}?limit=100000'
        seen_pages = set()
        resources = {}
        while url:
            if url in seen_pages:
                raise ValueError('PokeAPI returned a repeated pagination URL')
            seen_pages.add(url)
            page = self.get(url, max_age=86400)
            for entry in page['results']:
                resources[entry['url']] = entry
            url = page.get('next')
        return list(resources.values())


def ensure_progress(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS reference_seed_progress (
                stage TEXT NOT NULL, resource_id INTEGER NOT NULL, name TEXT NOT NULL,
                type_count INTEGER, completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY(stage, resource_id))''')
            cur.execute('''CREATE TABLE IF NOT EXISTS reference_seed_stages (
                stage TEXT PRIMARY KEY, expected_count INTEGER NOT NULL,
                completed_count INTEGER NOT NULL DEFAULT 0,
                completed_at TIMESTAMPTZ, last_error TEXT)''')


def resource_id(url):
    return int(url.rstrip('/').split('/')[-1])


def completed_resources(conn, stage):
    """Check underlying rows too, so stale checkpoints cannot hide deleted data."""
    with conn.cursor() as cur:
        if stage == 'pokemon':
            cur.execute('''SELECT s.resource_id,s.name FROM reference_seed_progress s
                JOIN pokemon p ON p.pokemon_name=s.name WHERE s.stage='pokemon'
                AND s.type_count > 0 AND s.type_count=(SELECT count(*) FROM pokemon_types t WHERE t.pk_id=p.pk_id)''')
        elif stage == 'moves':
            cur.execute('''SELECT s.resource_id,s.name FROM reference_seed_progress s
                JOIN moves m ON m.move_id=s.resource_id AND m.move_name=s.name
                WHERE s.stage='moves' AND m.type_id IS NOT NULL AND m.priority IS NOT NULL''')
        elif stage == 'abilities':
            cur.execute('''SELECT s.resource_id,s.name FROM reference_seed_progress s
                JOIN abilities a ON a.ability_id=s.resource_id AND a.ability_name=s.name WHERE s.stage='abilities' ''')
        elif stage == 'items':
            cur.execute('''SELECT s.resource_id,s.name FROM reference_seed_progress s
                JOIN items i ON i.item_id=s.resource_id AND i.item_name=s.name WHERE s.stage='items' ''')
        else:
            raise ValueError(f'Unknown seed stage: {stage}')
        return set(cur.fetchall())


def type_id(cur, info):
    name = info['name']
    cur.execute('SELECT type_id FROM type_lookup WHERE type_name=%s', (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    try:
        identifier = pokemon_table.get_type_id(name)
    except ValueError:
        # PokeAPI also contains non-VGC move types such as shadow. Keep them in
        # a separate ID range instead of silently dropping those reference rows.
        identifier = 100000 + resource_id(info['url'])
    cur.execute('INSERT INTO type_lookup(type_id,type_name) VALUES (%s,%s)', (identifier, name))
    return identifier


def save_resource(cur, stage, data, client):
    if stage == 'pokemon':
        stats = pokemon_table.get_stats(data)
        dex = resource_id(data['species']['url'])
        try:
            generation = pokemon_table.get_generation(dex)
        except ValueError:
            generation = resource_id(client.get(data['species']['url'])['generation']['url'])
        types = data['types']
        if not 1 <= len(types) <= 2:
            raise ValueError(f"Invalid type list for {data['name']}")
        cur.execute('''INSERT INTO pokemon(poke_dex,pokemon_name,generation,hp,atk,def,spa,spd,spe)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(pokemon_name) DO UPDATE SET
            poke_dex=EXCLUDED.poke_dex,generation=EXCLUDED.generation,hp=EXCLUDED.hp,atk=EXCLUDED.atk,
            def=EXCLUDED.def,spa=EXCLUDED.spa,spd=EXCLUDED.spd,spe=EXCLUDED.spe RETURNING pk_id''',
            (dex, data['name'], generation, stats['hp'], stats['atk'], stats['def'], stats['spa'], stats['spd'], stats['spe']))
        pk = cur.fetchone()[0]
        # Replacing just this Pokémon's type rows is atomic with its checkpoint.
        cur.execute('DELETE FROM pokemon_types WHERE pk_id=%s', (pk,))
        for entry in types:
            cur.execute('INSERT INTO pokemon_types VALUES (%s,%s,%s)', (pk, type_id(cur, entry['type']), entry['slot']))
        return len(types)
    if stage == 'moves':
        if data.get('priority') is None:
            raise ValueError(f"Missing priority for move {data['name']}")
        cur.execute('''INSERT INTO moves(move_id,move_name,type_id,accuracy,power,priority) VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT(move_id) DO UPDATE SET move_name=EXCLUDED.move_name,type_id=EXCLUDED.type_id,
            accuracy=EXCLUDED.accuracy,power=EXCLUDED.power,priority=EXCLUDED.priority''',
            (data['id'], data['name'], type_id(cur, data['type']), data['accuracy'], data['power'], data['priority']))
    elif stage == 'abilities':
        cur.execute('INSERT INTO abilities VALUES (%s,%s) ON CONFLICT(ability_id) DO UPDATE SET ability_name=EXCLUDED.ability_name',
                    (data['id'], data['name']))
    elif stage == 'items':
        cur.execute('INSERT INTO items(item_id,item_name) VALUES (%s,%s) ON CONFLICT(item_id) DO UPDATE SET item_name=EXCLUDED.item_name',
                    (data['id'], data['name']))
    else:
        raise ValueError(f'Unknown seed stage: {stage}')
    return None


def seed_stage(conn, stage, client=None):
    if stage not in STAGES:
        raise ValueError(f'Unknown seed stage: {stage}')
    client = client or PokeApiClient()
    ensure_progress(conn)
    entries = client.resources(STAGES[stage])
    if not entries:
        raise ValueError(f'PokeAPI returned an empty {stage} catalog; not marking it complete')
    completed = set() if client.refresh else completed_resources(conn, stage)
    expected = {(resource_id(entry['url']), entry['name']) for entry in entries}
    if len(expected) != len(entries):
        raise ValueError(f'Duplicate resources in {stage} catalog')
    done = len(expected & completed)
    with conn:
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO reference_seed_stages(stage,expected_count,completed_count)
                VALUES (%s,%s,%s) ON CONFLICT(stage) DO UPDATE SET expected_count=EXCLUDED.expected_count,
                completed_count=EXCLUDED.completed_count,completed_at=NULL,last_error=NULL''', (stage, len(entries), done))
    print(f'{stage}: {done}/{len(entries)} verified; {len(entries)-done} remaining.', flush=True)
    for entry in entries:
        identifier = resource_id(entry['url'])
        if (identifier, entry['name']) in completed:
            continue
        try:
            # Item IDs and names are both present in the listing: no detail fetch needed.
            data = {'id': identifier, 'name': entry['name']} if stage == 'items' else client.get(entry['url'])
            if data['id'] != identifier or data['name'] != entry['name']:
                raise ValueError(f"Catalog/detail mismatch for {entry['name']}")
            with conn:
                with conn.cursor() as cur:
                    count = save_resource(cur, stage, data, client)
                    cur.execute('''INSERT INTO reference_seed_progress(stage,resource_id,name,type_count)
                        VALUES (%s,%s,%s,%s) ON CONFLICT(stage,resource_id) DO UPDATE SET
                        name=EXCLUDED.name,type_count=EXCLUDED.type_count,completed_at=now()''',
                        (stage, identifier, entry['name'], count))
                    cur.execute('UPDATE reference_seed_stages SET completed_count=completed_count+1 WHERE stage=%s', (stage,))
            done += 1
            if done % 25 == 0 or done == len(entries):
                print(f'{stage}: {done}/{len(entries)} committed.', flush=True)
        except Exception as exc:
            conn.rollback()
            with conn:
                with conn.cursor() as cur:
                    cur.execute('UPDATE reference_seed_stages SET last_error=%s WHERE stage=%s',
                                (f"{entry['name']}: {type(exc).__name__}: {exc}", stage))
            raise RuntimeError(f"{stage} paused at {entry['name']} after {done}/{len(entries)} records. "
                               'Committed progress is saved; rerun to resume.') from exc
    with conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE reference_seed_stages SET completed_at=now(),last_error=NULL WHERE stage=%s', (stage,))
    return {'stage': stage, 'expected': len(entries), 'completed': done}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=CACHE)
    parser.add_argument('--refresh', action='store_true', help='Re-fetch and verify all reference data, including completed records')
    args = parser.parse_args(argv)
    conn = pokemon_table.get_connection()
    client = PokeApiClient(args.cache_dir, refresh=args.refresh)
    try:
        # Serialize seed jobs without holding a transaction across the full download.
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_lock(74632002)')
        conn.commit()
        for stage in STAGES:
            seed_stage(conn, stage, client)
        print('All reference catalogs verified. Tournament ingestion can proceed.', flush=True)
        return 0
    except (requests.RequestException, psycopg2.Error, RuntimeError, ValueError, KeyError) as exc:
        print(f'Seeding incomplete: {exc}', file=sys.stderr, flush=True)
        return 1
    finally:
        conn.close()  # Also releases the session advisory lock.


if __name__ == '__main__':
    raise SystemExit(main())
