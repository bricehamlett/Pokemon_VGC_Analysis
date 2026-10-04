"""Shared, transactional ingestion for scraped and API events.

Source payloads are retained; conflicting sheets never overwrite prior builds.
This module performs structural checks, not exhaustive regulation legality checks.
"""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from psycopg2.extras import Json


def migrate(conn):
    """Apply the additive migration once, serializing concurrent importers."""
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(74632001)")
            cur.execute("CREATE TABLE IF NOT EXISTS ingestion_migrations (version TEXT PRIMARY KEY)")
            for version in ('001_multi_source', '002_identity_reviews'):
                cur.execute('SELECT 1 FROM ingestion_migrations WHERE version=%s', (version,))
                if not cur.fetchone():
                    cur.execute((Path(__file__).parent / 'migrations' / f'{version}.sql').read_text())



try:
    from . import normalization
except ImportError:
    import normalization

slug = normalization.slug


def api_species(p):
    """Compatibility wrapper; collectors use normalization.pokemon for flags."""
    return normalization.species(p)[0]


def normalize_api(details, standings, pairings, format_name=None):
    fmt = details.get('format')
    match = re.search(r'Regulation(?: Set)?\s+([A-Z](?:-[A-Z])?)$', format_name or '')
    series = re.search(r'Series\s+(\d+)', format_name or '')
    regulation = match.group(1) if match else (f'S{series.group(1)}' if series else fmt)
    # Tera completeness is meaningful for Scarlet/Violet, not older Series
    # formats. Unrecognized mechanics remain explicit for later review.
    requires_tera = bool(match and len(match.group(1)) == 1)
    event_issues = []
    if details.get('bannedCards') or details.get('specialRules'):
        event_issues.append('error:custom_rules')
    if not match and not series:
        event_issues.append('error:unmapped_format')
    teams = []
    for entry in standings:
        pokemon = []
        sheet = entry.get('decklist')
        for p in sheet if isinstance(sheet, list) else []:
            pokemon.append(normalization.pokemon(p))
        teams.append({'external_player_id': entry['player'], 'player_name': entry.get('name') or entry['player'],
                      'placement': entry.get('placing'), 'country': entry.get('country'),
                      'record': entry.get('record'), 'drop_round': entry.get('drop'),
                      'pokemon': pokemon, 'issues': list(event_issues), 'requires_tera': requires_tera})
    return {'source': 'play_limitless', 'external_id': details['id'],
            'event_name': details['name'], 'regulation': regulation,
            'event_date': datetime.fromisoformat(details['date'].replace('Z', '+00:00')).date(),
            'event_size': details['players'],
            'metadata': {**details, 'normalization_version': normalization.VERSION, 'format_name': format_name, 'requires_tera': requires_tera}, 'teams': teams,
            'pairings': pairings, 'raw': {'details': details, 'standings': standings, 'pairings': pairings},
            'fetched_at': datetime.now(timezone.utc).isoformat()}


def normalize_scraped(raw):
    value = raw['event_date']
    if isinstance(value, str):
        value = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', value)
        try:
            value = date.fromisoformat(value)
        except ValueError:
            value = datetime.strptime(value, '%d %B %Y').date()
    teams = []
    for team in raw['teams']:
        # Scope display-name identities to the event: no cross-event identity guesses.
        teams.append({**team, 'external_player_id': team.get('external_player_id') or f"{raw['event_id']}:{team['player_name']}",
                      'requires_tera': len(raw['regulation']) == 1,
                      'issues': list(team.get('issues', [])), 'pokemon': [normalization.pokemon(p.get('source_fields') or p)
                                                 for p in team['pokemon']]})
    return {'source': 'limitless_vgc', 'external_id': str(raw['event_id']),
            'event_name': raw['event_name'], 'regulation': raw['regulation'], 'event_date': value,
            'event_size': raw['event_size'], 'metadata': {**raw.get('metadata', {}), 'normalization_version': normalization.VERSION}, 'teams': teams, 'pairings': None,
            'identity_reviews': raw.get('identity_reviews', []),
            'raw': raw, 'fetched_at': datetime.now(timezone.utc).isoformat()}


def assess(team, event_size):
    issues = list(team.get('issues', []))
    pokemon = team.get('pokemon', [])
    if not pokemon:
        return 'missing', issues + ['error:missing_sheet']
    if len(pokemon) != 6:
        issues.append('error:team_size')
    names = [p['pokemon_name'] for p in pokemon]
    if len(set(names)) != len(names):
        issues.append('error:duplicate_species')
    items = [p['item'] for p in pokemon if p.get('item')]
    if len(items) != len(set(items)):
        issues.append('error:duplicate_items')
    for p in pokemon:
        issues.extend(p.get('normalization_issues', []))
        if not p.get('pokemon_name'):
            issues.append('error:missing_species')
        if not p.get('ability') or not p.get('moves') or (team.get('requires_tera', True) and not p.get('tera')):
            issues.append('warning:partial_build')
        moves = p.get('moves', [])
        if len(moves) > 4 or len(set(moves)) != len(moves):
            issues.append('error:invalid_moves')
    placement = team.get('placement')
    if placement is not None and (not isinstance(placement, int) or not 1 <= placement <= event_size):
        issues.append('error:invalid_placement')
    issues = sorted(set(issues))
    status = 'invalid' if any(i.startswith('error:') for i in issues) else ('partial' if issues else 'complete')
    return status, issues


def audit(event):
    counts = dict(complete=0, partial=0, invalid=0, missing=0)
    labeled = 0
    issues = {}
    for team in event['teams']:
        status, problems = assess(team, event['event_size'])
        counts[status] += 1
        labeled += (status in ('complete', 'partial') and team.get('placement') is not None
                    and not team.get('identity_pending'))
        for problem in problems:
            issues[problem] = issues.get(problem, 0) + 1
    return {'source': event['source'], 'external_id': event['external_id'], 'name': event['event_name'],
            'regulation': event['regulation'], 'reported_players': event['event_size'],
            'returned_players': len(event['teams']),
            'unreturned_players': max(0, event['event_size'] - len(event['teams'])),
            'coverage_scope': event.get('metadata', {}).get('coverage_scope', 'source_response'), **counts, 'placement_candidates': labeled,
            'issues': issues}


def lookup(cur, table, id_column, name_column, value):
    if value is None:
        return None
    # Table/column arguments are constants supplied only by resolve_sheet.
    cur.execute(f'SELECT {id_column} FROM {table} WHERE {name_column} = %s', (value,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f'error:unknown_{table}:{value}')
    return row[0]


def resolve_sheet(cur, pokemon):
    result = []
    pokedexes = []
    for p in pokemon:
        cur.execute('SELECT pk_id, poke_dex FROM pokemon WHERE pokemon_name = %s', (p['pokemon_name'],))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"error:unknown_pokemon:{p['pokemon_name']}")
        pk_id, dex = row
        pokedexes.append(dex)
        item = lookup(cur, 'items', 'item_id', 'item_name', p.get('item'))
        ability = lookup(cur, 'abilities', 'ability_id', 'ability_name', p.get('ability'))
        tera = p.get('tera')
        if isinstance(tera, int):
            cur.execute('SELECT type_id FROM type_lookup WHERE type_id = %s', (tera,))
            if not cur.fetchone():
                raise ValueError(f'error:unknown_tera:{tera}')
        else:
            tera = lookup(cur, 'type_lookup', 'type_id', 'type_name', tera)
        moves = [lookup(cur, 'moves', 'move_id', 'move_name', m) for m in p['moves']]
        result.append((pk_id, dex, item, tera, ability, moves))
    if len(set(pokedexes)) != len(pokedexes):
        raise ValueError('error:duplicate_species')
    return result


def canonical_sheet(rows):
    return sorted(json.dumps([*r[:5], sorted(r[5])]) for r in rows)


def save_identity_review(cur, event_id, source, key, payload):
    names = [n for n in payload.get('legacy_names', []) if n]
    externals = [t['external_player_id'] for t in payload.get('candidates', [])]
    cur.execute("""SELECT DISTINCT p.player_id FROM players p JOIN teams t USING(player_id)
        LEFT JOIN player_sources s ON s.player_id=p.player_id AND s.source=%s
        WHERE t.event_id=%s AND (p.player_name=ANY(%s) OR s.external_id=ANY(%s))""",
        (source, event_id, names, externals))
    blocked = [r[0] for r in cur.fetchall()]
    cur.execute("""INSERT INTO pending_identity_reviews(event_id,review_key,payload,blocked_player_ids)
        VALUES (%s,%s,%s,%s) ON CONFLICT(event_id,review_key) DO UPDATE SET
        payload=EXCLUDED.payload, blocked_player_ids=EXCLUDED.blocked_player_ids,
        last_seen=now(), resolved_at=NULL""", (event_id, key, Json(payload), blocked))


def load_event(conn, event):
    """One transaction per event. Call migrate once before loading a batch."""
    summary = audit(event)
    summary.update(imported_sheets=0, conflicts=0, unresolved=0, imported_entrants=0,
                   pending_identity_entrants=0)
    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(74632001)')
            cur.execute('''INSERT INTO events(source, external_id, event_name, regulation, event_date, event_size, source_metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(source, external_id) DO UPDATE SET event_name=EXCLUDED.event_name,
                regulation=EXCLUDED.regulation, event_date=EXCLUDED.event_date,
                event_size=EXCLUDED.event_size, source_metadata=EXCLUDED.source_metadata RETURNING event_id''',
                (event['source'], event['external_id'], event['event_name'], event['regulation'],
                 event['event_date'], event['event_size'], Json(event['metadata'])))
            event_id = cur.fetchone()[0]
            raw = json.loads(json.dumps(event['raw'], default=str))
            digest = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
            cur.execute('''INSERT INTO ingestion_snapshots(event_id,payload_hash,payload,fetched_at)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING''', (event_id, digest, Json(raw), event['fetched_at']))
            for review in event.get('identity_reviews', []):
                candidates = [t for t in event['teams']
                              if str(t.get('standings_row', {}).get('tp_id')) in review['candidate_ids']]
                names = review['legacy_names'] + [t['legacy_player_name'] for t in candidates
                                                   if t.get('legacy_player_name')]
                save_identity_review(cur, event_id, event['source'], review['review_key'],
                                     {**review, 'legacy_names': names, 'candidates': candidates})
            seen = set()
            for team in event['teams']:
                external = team['external_player_id']
                if external in seen:
                    raise ValueError(f'Duplicate participant ID: {external}')
                seen.add(external)
                if team.get('identity_pending'):
                    summary['pending_identity_entrants'] += 1
                    continue
                cur.execute('SELECT player_id FROM player_sources WHERE source=%s AND external_id=%s', (event['source'], external))
                row = cur.fetchone()
                # Adopt legacy rows only within this exact scraped event.
                if (row is None and event['source'] == 'limitless_vgc'
                        and (':standings:' not in external or team.get('legacy_player_name'))):
                    cur.execute('''SELECT p.player_id FROM players p JOIN teams t USING(player_id)
                        WHERE t.event_id=%s AND p.player_name = ANY(%s)''',
                        (event_id, [team['player_name'], team.get('legacy_player_name')]))
                    matches = cur.fetchall()
                    if len(matches) > 1:
                        save_identity_review(cur, event_id, event['source'], 'participant:' + external,
                                             {'reason': 'ambiguous_database_identity',
                                              'legacy_names': [team['player_name'], team.get('legacy_player_name')],
                                              'candidates': [team]})
                        summary['pending_identity_entrants'] += 1
                        continue
                    row = matches[0] if matches else None
                if row is None:
                    cur.execute('INSERT INTO players(player_name) VALUES (%s) RETURNING player_id', (team['player_name'],))
                    row = cur.fetchone()
                player_id = row[0]
                summary['imported_entrants'] += 1
                # Resolve only reviews tied to an identity successfully reconciled
                # in this transaction. Disappearing source entries stay pending.
                cur.execute("""UPDATE pending_identity_reviews SET resolved_at=now()
                    WHERE event_id=%s AND resolved_at IS NULL AND
                    (review_key=%s OR (review_key LIKE 'results:%%' AND payload->'legacy_names' ? %s))""",
                    (event_id, 'participant:' + external, team.get('legacy_player_name') or ''))
                cur.execute('INSERT INTO player_sources VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (event['source'], external, player_id))
                cur.execute('UPDATE players SET player_name=%s WHERE player_id=%s', (team['player_name'], player_id))
                status, issues = assess(team, event['event_size'])
                cur.execute('''INSERT INTO teams(event_id,player_id,placement,record,drop_round,country)
                    VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(player_id,event_id) DO UPDATE SET
                    placement=EXCLUDED.placement, record=EXCLUDED.record, drop_round=EXCLUDED.drop_round,
                    country=EXCLUDED.country RETURNING team_id''',
                    (event_id, player_id, team.get('placement'), Json(team.get('record')), team.get('drop_round'), team.get('country')))
                team_id = cur.fetchone()[0]
                resolved = None
                if status in ('complete', 'partial'):
                    try:
                        resolved = resolve_sheet(cur, team['pokemon'])
                    except ValueError as exc:
                        status = 'invalid'
                        issues.append(str(exc))
                        summary['unresolved'] += 1
                if resolved is not None:
                    cur.execute('''SELECT p.pk_id,p.poke_dex,p.item_id,p.tera_type,p.ability_id,
                        COALESCE(array_agg(m.move_id ORDER BY m.move_slot) FILTER (WHERE m.move_id IS NOT NULL), '{}')
                        FROM team_pokemon p LEFT JOIN team_pokemon_moves m USING(team_pokemon_id)
                        WHERE p.team_id=%s GROUP BY p.team_pokemon_id ORDER BY p.slot''', (team_id,))
                    existing = cur.fetchall()
                    if existing and canonical_sheet(existing) != canonical_sheet(resolved):
                        status = 'conflict'
                        issues.append('error:sheet_changed_review_snapshot')
                        summary['conflicts'] += 1
                    elif not existing:
                        for slot, (pk, dex, item, tera, ability, moves) in enumerate(resolved, 1):
                            cur.execute('''INSERT INTO team_pokemon(team_id,slot,pk_id,poke_dex,item_id,tera_type,ability_id)
                                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING team_pokemon_id''',
                                (team_id, slot, pk, dex, item, tera, ability))
                            team_pokemon_id = cur.fetchone()[0]
                            for move_slot, move in enumerate(moves, 1):
                                cur.execute('INSERT INTO team_pokemon_moves VALUES (%s,%s,%s)', (team_pokemon_id, move, move_slot))
                        summary['imported_sheets'] += 1
                cur.execute('UPDATE teams SET sheet_status=%s, quality_issues=%s WHERE team_id=%s', (status, Json(sorted(set(issues))), team_id))
            cur.execute("SELECT review_key,payload FROM pending_identity_reviews WHERE event_id=%s AND resolved_at IS NULL",
                        (event_id,))
            pending = cur.fetchall()
            summary['identity_review_count'] = len(pending)
            summary['identity_review_names'] = sorted({name for _, payload in pending
                                                       for name in payload.get('legacy_names', []) if name})
            summary['import_status'] = 'imported_with_unresolved_identities' if pending else 'imported'
            cur.execute("UPDATE events SET source_metadata=source_metadata || %s::jsonb WHERE event_id=%s",
                        (Json({'identity_review_count': len(pending), 'import_status': summary['import_status']}), event_id))
            if event['pairings'] is not None:
                # The latest complete response replaces only this source event's pairings.
                cur.execute('DELETE FROM event_pairings WHERE event_id=%s', (event_id,))
                for pairing in event['pairings']:
                    key = hashlib.sha256(json.dumps(pairing, sort_keys=True).encode()).hexdigest()
                    cur.execute('INSERT INTO event_pairings VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (event_id, key, Json(pairing)))
    return summary


def imported_api_ids(conn, require_pairings=True):
    """Resume from committed imports, never from merely downloaded cache files."""
    with conn.cursor() as cur:
        cur.execute('''SELECT e.external_id FROM events e
            WHERE e.source='play_limitless' AND EXISTS (
                SELECT 1 FROM ingestion_snapshots s WHERE s.event_id=e.event_id
                AND (NOT %s OR (s.payload->'pairings' IS NOT NULL
                                AND s.payload->'pairings' <> 'null'::jsonb)))''', (require_pairings,))
        return {row[0] for row in cur.fetchall()}


def coverage(conn):
    """Database-wide counts by source and regulation after an import run."""
    with conn.cursor() as cur:
        cur.execute('''SELECT e.source,e.regulation,count(DISTINCT e.event_id),count(t.team_id),
            count(t.team_id) FILTER (WHERE t.sheet_status='missing'),
            count(t.team_id) FILTER (WHERE t.sheet_status IN ('invalid','conflict')),
            count(v.team_id)
            FROM events e LEFT JOIN teams t USING(event_id)
            LEFT JOIN training_team_entries v ON v.team_id=t.team_id
            GROUP BY e.source,e.regulation ORDER BY e.source,e.regulation''')
        keys = ['source', 'regulation', 'events', 'entrants', 'missing_sheets', 'flagged_sheets', 'placement_teams']
        return [dict(zip(keys, row)) for row in cur.fetchall()]
