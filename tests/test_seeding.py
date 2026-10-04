import contextlib
import io
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from Fetch_Data import seed_database as seed


def pokemon(identifier, name, two_types=False):
    types = [{'slot': 1, 'type': {'name': 'grass', 'url': seed.BASE + '/type/12/'}}]
    if two_types:
        types.append({'slot': 2, 'type': {'name': 'poison', 'url': seed.BASE + '/type/4/'}})
    return {'id': identifier, 'name': name, 'species': {'url': seed.BASE + f'/pokemon-species/{identifier}/'},
            'types': types, 'stats': [{'stat': {'name': stat}, 'base_stat': 50}
                                    for stat in ['hp', 'attack', 'defense', 'special-attack', 'special-defense', 'speed']]}


class ClientTests(unittest.TestCase):
    def test_timeout_retries_then_cache_avoids_redownload(self):
        session = Mock(headers={})
        response = Mock(status_code=200)
        response.json.return_value = {'id': 1, 'name': 'bulbasaur'}
        session.get.side_effect = [requests.ReadTimeout('slow'), response]
        sleep = Mock()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            client = seed.PokeApiClient(tmp, session, sleep)
            self.assertEqual(client.get(seed.BASE + '/pokemon/1/')['id'], 1)
            self.assertEqual(client.get(seed.BASE + '/pokemon/1/')['id'], 1)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.get.call_args.kwargs['timeout'], (10, 45))
        sleep.assert_called_once_with(1)

    def test_exhausted_retries_do_not_cache_failure(self):
        session = Mock(headers={})
        session.get.side_effect = requests.ReadTimeout('offline')
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            client = seed.PokeApiClient(tmp, session, Mock())
            with self.assertRaises(requests.ReadTimeout):
                client.get(seed.BASE + '/pokemon/1/')
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertEqual(session.get.call_count, 5)

    def test_http_404_does_not_retry(self):
        session = Mock(headers={})
        response = Mock(status_code=404)
        response.raise_for_status.side_effect = requests.HTTPError('missing', response=response)
        session.get.return_value = response
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(requests.HTTPError):
                seed.PokeApiClient(tmp, session, Mock()).get(seed.BASE + '/pokemon/999999/')
        self.assertEqual(session.get.call_count, 1)

    def test_startup_cannot_skip_partial_seed(self):
        import start_app
        with patch.object(start_app.shutil, 'which', return_value='/bin/docker'), \
             patch.object(start_app.Path, 'exists', return_value=True), \
             patch.object(start_app, 'wait_for_database', return_value=True), \
             patch.object(start_app.subprocess, 'run', side_effect=[Mock(returncode=0), Mock(returncode=0), Mock(returncode=1)]) as run, \
             patch.object(start_app, 'run_ingestion') as ingest, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(start_app.main([]), 1)
        self.assertEqual(run.call_args.args[0][-1], 'seed')
        ingest.assert_not_called()


@unittest.skipUnless(os.getenv('VGC_TEST_DATABASE') == '1', 'Requires isolated-schema PostgreSQL tests')
class SeedDatabaseTests(unittest.TestCase):
    def setUp(self):
        from dotenv import load_dotenv
        from psycopg2 import sql
        load_dotenv(Path(__file__).parents[1] / 'Fetch_Data/.env')
        self.conn = seed.pokemon_table.get_connection()
        self.schema = 'seed_test_' + uuid.uuid4().hex
        with self.conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
            cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))
            cur.execute((Path(__file__).parents[1] / 'Fetch_Data/01_schema.sql').read_text())
        self.conn.commit()
        self.client = Mock(refresh=False)
        self.client.resources.return_value = [
            {'name': 'bulbasaur', 'url': seed.BASE + '/pokemon/1/'},
            {'name': 'ivysaur', 'url': seed.BASE + '/pokemon/2/'}]

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

    def test_timeout_preserves_first_record_and_resume_repairs_legacy_partial_table(self):
        self.client.get.side_effect = [pokemon(1, 'bulbasaur', True), requests.ReadTimeout('simulated')]
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            seed.seed_stage(self.conn, 'pokemon', self.client)
        self.assertEqual(self.scalar('SELECT count(*) FROM pokemon'), 1)
        self.assertEqual(self.scalar('SELECT count(*) FROM pokemon_types'), 2)
        self.assertIsNone(self.scalar("SELECT completed_at FROM reference_seed_stages WHERE stage='pokemon'"))
        self.client.get.reset_mock()
        self.client.get.side_effect = [pokemon(2, 'ivysaur', True)]
        with contextlib.redirect_stdout(io.StringIO()):
            result = seed.seed_stage(self.conn, 'pokemon', self.client)
        self.assertEqual(result['completed'], 2)
        self.client.get.assert_called_once_with(seed.BASE + '/pokemon/2/')
        self.assertEqual(self.scalar('SELECT count(*) FROM pokemon'), 2)
        self.assertEqual(self.scalar('SELECT count(*) FROM pokemon_types'), 4)
        self.client.get.reset_mock()
        with contextlib.redirect_stdout(io.StringIO()):
            seed.seed_stage(self.conn, 'pokemon', self.client)
        self.client.get.assert_not_called()

    def test_existing_rows_without_checkpoints_are_verified_and_keep_ids(self):
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO pokemon(poke_dex,pokemon_name,generation,hp,atk,def,spa,spd,spe) VALUES (1,'bulbasaur',1,1,1,1,1,1,1) RETURNING pk_id")
            original_id = cur.fetchone()[0]
        self.conn.commit()
        self.client.resources.return_value = self.client.resources.return_value[:1]
        self.client.get.return_value = pokemon(1, 'bulbasaur', True)
        with contextlib.redirect_stdout(io.StringIO()):
            seed.seed_stage(self.conn, 'pokemon', self.client)
        self.assertEqual(self.scalar('SELECT pk_id FROM pokemon'), original_id)
        self.assertEqual(self.scalar('SELECT hp FROM pokemon'), 50)
        self.assertEqual(self.scalar('SELECT count(*) FROM pokemon_types'), 2)

    def test_corrupt_type_rows_are_repaired_despite_checkpoint(self):
        self.client.resources.return_value = self.client.resources.return_value[:1]
        self.client.get.return_value = pokemon(1, 'bulbasaur', True)
        with contextlib.redirect_stdout(io.StringIO()):
            seed.seed_stage(self.conn, 'pokemon', self.client)
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM pokemon_types WHERE slot=2')
        self.conn.commit()
        self.client.get.reset_mock()
        with contextlib.redirect_stdout(io.StringIO()):
            seed.seed_stage(self.conn, 'pokemon', self.client)
        self.client.get.assert_called_once()
        self.assertEqual(self.scalar('SELECT count(*) FROM pokemon_types'), 2)

    def test_failed_resource_rolls_back_its_pokemon_and_checkpoint(self):
        self.client.resources.return_value = self.client.resources.return_value[:1]
        data = pokemon(1, 'bulbasaur', True)
        data['types'][1]['slot'] = 3  # Violates the schema after Pokémon insertion.
        self.client.get.return_value = data
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            seed.seed_stage(self.conn, 'pokemon', self.client)
        self.assertEqual(self.scalar('SELECT count(*) FROM pokemon'), 0)
        self.assertEqual(self.scalar('SELECT count(*) FROM reference_seed_progress'), 0)

    def test_items_use_catalog_and_moves_keep_special_types(self):
        self.client.resources.return_value = [{'name': 'sitrus-berry', 'url': seed.BASE + '/item/158/'}]
        with contextlib.redirect_stdout(io.StringIO()):
            seed.seed_stage(self.conn, 'items', self.client)
        self.client.get.assert_not_called()
        self.client.resources.return_value = [{'name': 'shadow-rush', 'url': seed.BASE + '/move/10001/'}]
        self.client.get.return_value = {'id': 10001, 'name': 'shadow-rush', 'type': {'name': 'shadow', 'url': seed.BASE + '/type/10002/'},
                                        'accuracy': 100, 'power': 55, 'priority': 0}
        with contextlib.redirect_stdout(io.StringIO()):
            seed.seed_stage(self.conn, 'moves', self.client)
        self.assertEqual(self.scalar("SELECT type_name FROM type_lookup"), 'shadow')
        self.assertEqual(self.scalar('SELECT count(*) FROM moves'), 1)


if __name__ == '__main__':
    unittest.main()
