import copy
import json
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

from Fetch_Data import ingestion
from Fetch_Data.limitless_api import ApiClient, choose_format, choose_formats, discover


def fixture():
    details = {'id': 'abc123', 'name': 'Weekly', 'format': 'SVI', 'game': 'VGC',
               'date': '2025-05-01T12:00:00Z', 'players': 2, 'decklists': True}
    sheet = [{'id': f'pokemon-{i}', 'name': f'Pokemon {i}', 'item': f'Item {i}',
              'ability': 'Ability', 'attacks': ['Move'], 'tera': 'Fire'} for i in range(6)]
    standings = [{'player': 'alice', 'name': 'Alice', 'placing': 1, 'decklist': sheet,
                  'record': {'wins': 1, 'losses': 0, 'ties': 0}, 'drop': None},
                 {'player': 'bob', 'name': 'Bob', 'placing': None, 'decklist': copy.deepcopy(sheet),
                  'record': {'wins': 0, 'losses': 1, 'ties': 0}, 'drop': 1}]
    return ingestion.normalize_api(details, standings, [], 'Scarlet & Violet - Regulation I')


class NormalizationTests(unittest.TestCase):
    def test_forms_and_abilities(self):
        event = fixture()
        raw = event['raw']
        raw['standings'][0]['decklist'][0].update(id='calyrex-ice-rider', ability='As One ')
        team = ingestion.normalize_api(**raw, format_name='Scarlet & Violet - Regulation I')['teams'][0]
        self.assertEqual(team['pokemon'][0]['pokemon_name'], 'calyrex-ice')
        self.assertEqual(team['pokemon'][0]['ability'], 'as-one-glastrier')
        self.assertEqual(ingestion.api_species({'id': 'landorus'}), 'landorus-incarnate')
        self.assertEqual(ingestion.api_species({'id': 'zamazenta', 'item': 'Rusted Shield'}), 'zamazenta-crowned')
        self.assertEqual(ingestion.api_species({'id': 'indeedee'}), 'indeedee-male')
        self.assertEqual(ingestion.api_species({'id': 'meowstic'}), 'meowstic-male')
        self.assertEqual(ingestion.api_species({'id': 'necrozma-dusk-mane'}), 'necrozma-dusk')
        self.assertEqual(ingestion.api_species({'id': 'tauros-paldea-aqua'}), 'tauros-paldea-aqua-breed')
        self.assertEqual(ingestion.api_species({'id': 'pyroar'}), 'pyroar-male')
        self.assertEqual(ingestion.api_species({'id': 'squawkabilly'}), 'squawkabilly-green-plumage')

    def test_null_placement_and_missing_tera_remain_missing(self):
        event = fixture()
        event['teams'][0]['pokemon'][0]['tera'] = None
        result = ingestion.audit(event)
        self.assertEqual(result['partial'], 1)
        self.assertEqual(result['placement_candidates'], 1)
        self.assertIsNone(event['teams'][1]['placement'])

    def test_invalid_and_missing_sheets(self):
        event = fixture()
        event['teams'][0]['pokemon'][1]['item'] = 'item-0'
        event['teams'][1]['pokemon'] = []
        result = ingestion.audit(event)
        self.assertEqual(result['invalid'], 1)
        self.assertEqual(result['missing'], 1)
        self.assertEqual(result['placement_candidates'], 0)

    def test_custom_rules_excluded(self):
        raw = fixture()['raw']
        raw['details']['specialRules'] = ['custom']
        result = ingestion.audit(ingestion.normalize_api(**raw, format_name='Regulation I'))
        self.assertEqual(result['invalid'], 2)

    def test_one_move_is_valid(self):
        self.assertEqual(ingestion.audit(fixture())['complete'], 2)

    def test_format_resolution(self):
        games = [{'id': 'VGC', 'formats': {'SVI': 'Scarlet & Violet - Regulation I', 'M-C': 'Regulation Set M-C'}}]
        self.assertEqual(choose_format(games, 'I')[0], 'SVI')
        self.assertEqual(choose_format(games, 'M-C')[0], 'M-C')
        with self.assertRaises(ValueError):
            choose_format(games, 'UNKNOWN')
        self.assertEqual(len(choose_formats(games)), 2)
        self.assertEqual(choose_formats(games, ['I', 'SVI']), [('SVI', 'Scarlet & Violet - Regulation I')])

    def test_series_without_tera_is_not_partial(self):
        raw = fixture()['raw']
        raw['details']['format'] = 'VGC22'
        for entry in raw['standings']:
            for pokemon in entry['decklist']:
                pokemon['tera'] = None
        event = ingestion.normalize_api(**raw, format_name='VGC 2022 (Series 12)')
        self.assertEqual(event['regulation'], 'S12')
        self.assertEqual(ingestion.audit(event)['complete'], 2)
        self.assertEqual(ingestion.audit(event)['invalid'], 0)

    def test_unrecognized_format_stays_out_of_training(self):
        raw = fixture()['raw']
        raw['details']['format'] = 'CUSTOM'
        event = ingestion.normalize_api(**raw, format_name='Unknown future game')
        self.assertEqual(event['regulation'], 'CUSTOM')
        self.assertEqual(ingestion.audit(event)['invalid'], 2)

    def test_pagination_and_date_filters(self):
        client = Mock()
        def entry(key, day):
            return {'id': key, 'date': day + 'T12:00:00Z', 'players': 10}
        client.get.side_effect = [[entry('today', '2025-05-03'), entry('a', '2025-05-02')],
                                  [entry('a', '2025-05-02'), entry('b', '2025-05-01')], []]
        from datetime import date
        self.assertEqual(list(discover(client, 'SVI', 2, date(2025, 5, 3))), ['a', 'b'])
        self.assertEqual(client.get.call_args.kwargs['page'], 2)

    def test_retry_after(self):
        session = Mock()
        session.headers = {}
        retry = Mock(status_code=429, headers={'Retry-After': '2'})
        success = Mock(status_code=200, headers={})
        success.json.return_value = ['ok']
        session.get.side_effect = [retry, success]
        sleep = Mock()
        self.assertEqual(ApiClient(session, sleep).get('/games'), ['ok'])
        self.assertEqual(sleep.call_args_list[0].args[0], 2)

    def test_uncapped_discovery_resumes_and_refreshes_recent(self):
        from datetime import date
        client = Mock()
        client.get.side_effect = [[
            {'id': 'old', 'date': '2025-01-01T12:00:00Z', 'players': 10},
            {'id': 'recent', 'date': '2025-05-01T12:00:00Z', 'players': 10},
            {'id': 'new', 'date': '2025-01-02T12:00:00Z', 'players': 10}], []]
        stats = {}
        events = list(discover(client, 'SVI', None, date(2025, 5, 3),
                               skip_ids={'old', 'recent'}, refresh_since=date(2025, 4, 20), stats=stats))
        self.assertEqual(events, ['recent', 'new'])
        self.assertEqual(stats['skipped_existing'], 1)
        self.assertEqual(client.get.call_count, 2)

    def test_structured_rate_limit_header(self):
        session = Mock()
        session.headers = {}
        success = Mock(status_code=200, headers={'RateLimit': '"50-in-5min"; r=0; t=284'})
        success.json.return_value = []
        session.get.return_value = success
        sleep = Mock()
        ApiClient(session, sleep).get('/games')
        sleep.assert_called_once_with(285)


@unittest.skipUnless(os.getenv('VGC_TEST_DATABASE') == '1', 'Set VGC_TEST_DATABASE=1 for isolated-schema PostgreSQL tests')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        from dotenv import load_dotenv
        from psycopg2 import sql
        from Fetch_Data import pokemon_table
        load_dotenv(Path(__file__).parents[1] / 'Fetch_Data/.env')
        self.conn = pokemon_table.get_connection()
        self.schema = 'ingestion_test_' + uuid.uuid4().hex
        with self.conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
            # Deliberately exclude public: bootstrap DROP statements cannot touch real tables.
            cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
            cur.execute((Path(__file__).parents[1] / 'Fetch_Data/01_schema.sql').read_text())
            cur.execute("INSERT INTO events VALUES (437, 'Existing official event', 'I', '2025-05-01', 20)")
            cur.execute("INSERT INTO players(player_name) VALUES ('Legacy Alice')")
            cur.execute('INSERT INTO teams(event_id,player_id,placement) VALUES (437,1,1)')
            for i in range(6):
                cur.execute('INSERT INTO pokemon(poke_dex,pokemon_name,generation,hp,atk,def,spa,spd,spe) VALUES (%s,%s,9,1,1,1,1,1,1)', (i+1, f'pokemon-{i}'))
                cur.execute('INSERT INTO items(item_name) VALUES (%s)', (f'item-{i}',))
            cur.execute("INSERT INTO abilities VALUES (1, 'ability')")
            cur.execute("INSERT INTO moves(move_id,move_name) VALUES (1,'move'), (2,'other-move')")
            cur.execute("INSERT INTO type_lookup VALUES (1,'fire')")
        self.conn.commit()
        ingestion.migrate(self.conn)

    def tearDown(self):
        from psycopg2 import sql
        self.conn.rollback()
        with self.conn.cursor() as cur:
            cur.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.conn.commit()
        self.conn.close()

    def scalar(self, query):
        with self.conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchone()[0]

    def test_repeat_import_and_training_view(self):
        event = fixture()
        self.assertEqual(ingestion.load_event(self.conn, event)['imported_sheets'], 2)
        ingestion.migrate(self.conn)
        self.assertEqual(ingestion.load_event(self.conn, event)['imported_sheets'], 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM team_pokemon'), 12)
        self.assertEqual(self.scalar('SELECT count(*) FROM ingestion_snapshots'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM training_team_entries'), 1)
        self.assertGreater(self.scalar("SELECT event_id FROM events WHERE source='play_limitless'"), 437)
        self.assertEqual(ingestion.imported_api_ids(self.conn), {'abc123'})
        self.assertEqual(next(row for row in ingestion.coverage(self.conn) if row['source']=='play_limitless')['placement_teams'], 1)

    def test_conflicting_refresh_preserves_sheet(self):
        event = fixture()
        ingestion.load_event(self.conn, event)
        event['teams'][0]['pokemon'][0]['moves'] = ['other-move']
        event['raw']['standings'][0]['decklist'][0]['attacks'] = ['Other Move']
        self.assertEqual(ingestion.load_event(self.conn, event)['conflicts'], 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM team_pokemon_moves WHERE move_id=2'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM ingestion_snapshots'), 2)
        self.assertEqual(self.scalar('SELECT count(*) FROM training_team_entries'), 0)

    def test_unknown_reference_quarantines_only_affected_team(self):
        event = fixture()
        event['teams'][0]['pokemon'][0]['item'] = 'unknown-item'
        result = ingestion.load_event(self.conn, event)
        self.assertEqual(result['unresolved'], 1)
        self.assertEqual(result['imported_sheets'], 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM team_pokemon'), 6)

    def test_duplicate_participant_rolls_back_whole_event(self):
        event = fixture()
        event['teams'].append(copy.deepcopy(event['teams'][0]))
        with self.assertRaises(ValueError):
            ingestion.load_event(self.conn, event)
        self.assertEqual(self.scalar("SELECT count(*) FROM events WHERE source='play_limitless'"), 0)

    def test_legacy_event_backfill_and_source_collision(self):
        template = fixture()['teams'][0]
        raw = {'event_id': 437, 'event_name': 'Existing official event', 'regulation': 'I',
               'event_date': '1st May 2025', 'event_size': 20,
               'teams': [{**template, 'player_name': 'Legacy Alice'}]}
        event = ingestion.normalize_scraped(raw)
        ingestion.load_event(self.conn, event)
        ingestion.load_event(self.conn, event)
        self.assertEqual(self.scalar('SELECT count(*) FROM players'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM teams'), 1)
        api = fixture()
        api['external_id'] = '437'
        api['event_name'] = 'Existing official event'
        ingestion.load_event(self.conn, api)
        self.assertEqual(self.scalar('SELECT count(*) FROM events'), 2)

    def test_official_coverage_upgrade_preserves_ids_and_is_repeatable(self):
        raw = {'event_id': 437, 'event_name': 'Existing official event', 'regulation': 'I',
               'event_date': '1st May 2025', 'event_size': 20,
               'teams': [{**fixture()['teams'][0], 'external_player_id': None,
                          'player_name': 'Legacy Alice'}]}
        ingestion.load_event(self.conn, ingestion.normalize_scraped(raw))
        old_team_id = self.scalar('SELECT team_id FROM teams')
        raw['teams'][0].update(external_player_id='437:standings:10',
                               legacy_player_name='Legacy Alice', player_name='Alice')
        # Same display name belongs to another distinct participant, without a sheet.
        raw['teams'].append({'player_name': 'Alice', 'external_player_id': '437:standings:11',
                             'placement': 20, 'pokemon': []})
        ingestion.load_event(self.conn, ingestion.normalize_scraped(raw))
        ingestion.load_event(self.conn, ingestion.normalize_scraped(raw))
        self.assertEqual(self.scalar('SELECT count(*) FROM players'), 2)
        self.assertEqual(self.scalar('SELECT count(*) FROM teams'), 2)
        self.assertEqual(self.scalar('SELECT team_id FROM teams WHERE placement=1'), old_team_id)
        self.assertEqual(self.scalar('SELECT count(*) FROM team_pokemon'), 6)
        self.assertEqual(self.scalar("SELECT count(*) FROM teams WHERE sheet_status='missing'"), 1)

    def test_identity_queue_preserves_old_team_retries_and_resolves(self):
        raw = {'event_id': 437, 'event_name': 'Existing official event', 'regulation': 'I',
               'event_date': '1st May 2025', 'event_size': 20,
               'teams': [{**fixture()['teams'][0], 'external_player_id': None,
                          'player_name': 'Legacy Alice'}]}
        ingestion.load_event(self.conn, ingestion.normalize_scraped(raw))
        old_team = self.scalar('SELECT team_id FROM teams')
        pending = {**raw['teams'][0], 'player_name': 'Unmatched Alias',
                   'external_player_id': '437:standings:10', 'identity_pending': True,
                   'standings_row': {'tp_id': 10}}
        good = {**fixture()['teams'][0], 'player_name': 'Bob',
                'external_player_id': '437:standings:11', 'placement': 20}
        raw['teams'] = [pending, good]
        raw['identity_reviews'] = [{'review_key': 'results:alice', 'legacy_names': ['Legacy Alice'],
                                    'candidate_ids': ['10'], 'reason': 'unmatched'}]
        for _ in range(2):
            report = ingestion.load_event(self.conn, ingestion.normalize_scraped(raw))
            self.assertEqual(report['imported_entrants'], 1)
            self.assertEqual(report['pending_identity_entrants'], 1)
            self.assertEqual(report['identity_review_count'], 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM teams'), 2)
        self.assertEqual(self.scalar('SELECT count(*) FROM team_pokemon'), 12)
        self.assertEqual(self.scalar('SELECT count(*) FROM training_team_entries'), 1)
        self.assertEqual(self.scalar("SELECT count(*) FROM pending_identity_reviews WHERE payload->'candidates'->0->'pokemon' IS NOT NULL"), 1)
        self.assertEqual(self.scalar("SELECT count(*) FROM players WHERE player_name='Legacy Alice'"), 1)
        pending.update(identity_pending=False, legacy_player_name='Legacy Alice')
        raw['identity_reviews'] = []
        report = ingestion.load_event(self.conn, ingestion.normalize_scraped(raw))
        self.assertEqual(report['identity_review_count'], 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM teams'), 2)
        self.assertEqual(self.scalar('SELECT team_id FROM teams WHERE placement=1'), old_team)
        self.assertEqual(self.scalar('SELECT count(*) FROM training_team_entries'), 2)
        self.assertEqual(self.scalar('SELECT count(*) FROM pending_identity_reviews WHERE resolved_at IS NOT NULL'), 1)

    def test_database_identity_ambiguity_queues_only_that_participant(self):
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute("INSERT INTO players(player_name) VALUES ('Legacy Alice') RETURNING player_id")
                cur.execute('INSERT INTO teams(event_id,player_id,placement) VALUES (437,%s,2)', (cur.fetchone()[0],))
        raw = {'event_id': 437, 'event_name': 'Existing official event', 'regulation': 'I',
               'event_date': '1st May 2025', 'event_size': 20,
               'teams': [{**fixture()['teams'][0], 'external_player_id': '437:standings:10',
                          'legacy_player_name': 'Legacy Alice', 'player_name': 'New Alice'},
                         {**fixture()['teams'][0], 'external_player_id': '437:standings:11',
                          'player_name': 'Bob'}]}
        report = ingestion.load_event(self.conn, ingestion.normalize_scraped(raw))
        self.assertEqual(report['identity_review_count'], 1)
        self.assertEqual(report['imported_entrants'], 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM teams'), 3)

    def test_missing_sheet_backfill_and_no_item(self):
        event = fixture()
        original = event['teams'][0]['pokemon']
        event['teams'][0]['pokemon'] = []
        ingestion.load_event(self.conn, event)
        self.assertEqual(self.scalar('SELECT count(*) FROM training_team_entries'), 0)
        event['teams'][0]['pokemon'] = original
        event['teams'][0]['pokemon'][0]['item'] = None
        ingestion.load_event(self.conn, event)
        self.assertEqual(self.scalar('SELECT count(*) FROM training_team_entries'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM team_pokemon WHERE item_id IS NULL'), 1)

    def test_pairing_special_results_preserved_and_optional_refresh(self):
        event = fixture()
        event['pairings'] = [{'round': 1, 'phase': 1, 'player1': 'alice', 'winner': -1},
                             {'round': 2, 'phase': 1, 'player1': 'alice', 'player2': 'bob', 'winner': 0}]
        ingestion.load_event(self.conn, event)
        ingestion.load_event(self.conn, event)
        self.assertEqual(self.scalar('SELECT count(*) FROM event_pairings'), 2)
        event['pairings'] = None
        ingestion.load_event(self.conn, event)
        self.assertEqual(self.scalar('SELECT count(*) FROM event_pairings'), 2)

    def test_missing_pairings_does_not_skip_later_full_import(self):
        event = fixture()
        event['pairings'] = None
        event['raw']['pairings'] = None
        ingestion.load_event(self.conn, event)
        self.assertEqual(ingestion.imported_api_ids(self.conn), set())
        self.assertEqual(ingestion.imported_api_ids(self.conn, require_pairings=False), {'abc123'})

    @unittest.skipUnless(os.getenv('VGC_TEST_SNAPSHOTS') == '1', 'Optional cached-data pilot')
    def test_cached_events_against_existing_references(self):
        from collections import Counter
        from psycopg2 import sql
        cache = Path(__file__).parents[1] / 'Fetch_Data/data/raw/play_limitless'
        if not cache.exists():
            self.skipTest('Run an API audit to populate raw snapshots first')
        paths = [sorted(d.glob('*.json'))[-1] for d in cache.iterdir() if d.is_dir() and list(d.glob('*.json'))]
        if not paths:
            self.skipTest('Run an API audit to populate raw snapshots first')
        with self.conn.cursor() as cur:
            cur.execute('SELECT (SELECT count(*) FROM public.events), (SELECT count(*) FROM public.teams)')
            production_counts = cur.fetchone()
            # Only this test's temporary schema is modified; public is read-only.
            for table in ['pokemon', 'type_lookup', 'abilities', 'items', 'moves']:
                cur.execute(sql.SQL('DELETE FROM {}').format(sql.Identifier(table)))
                cur.execute(sql.SQL('INSERT INTO {} SELECT * FROM public.{}').format(sql.Identifier(table), sql.Identifier(table)))
        self.conn.commit()
        totals = Counter()
        events = []
        for path in paths:
            event = ingestion.normalize_api(**json.loads(path.read_text()))
            events.append(event)
            report = ingestion.load_event(self.conn, event)
            totals.update({k: report[k] for k in ['returned_players', 'complete', 'partial', 'invalid', 'missing',
                                                 'placement_candidates', 'imported_sheets', 'conflicts', 'unresolved']})
        count_before = self.scalar('SELECT count(*) FROM team_pokemon')
        for event in events:
            ingestion.load_event(self.conn, event)
        self.assertEqual(self.scalar('SELECT count(*) FROM team_pokemon'), count_before)
        with self.conn.cursor() as cur:
            cur.execute('SELECT (SELECT count(*) FROM public.events), (SELECT count(*) FROM public.teams)')
            self.assertEqual(cur.fetchone(), production_counts)
            cur.execute('SELECT issue, count(*) FROM teams, jsonb_array_elements_text(quality_issues) q(issue) GROUP BY issue ORDER BY issue')
            issues = cur.fetchall()
        result = {'events': len(events), 'totals': dict(totals),
                  'eligible_placement_teams': self.scalar('SELECT count(*) FROM training_team_entries'),
                  'issues': issues, 'repeat_import_passed': True, 'production_unchanged': True,
                  'coverage': ingestion.coverage(self.conn)}
        (cache.parent.parent / 'pilot_report.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    unittest.main()
