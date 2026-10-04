"""Pipeline routing, multi-format orchestration, and failure reporting."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import start_app
from Fetch_Data import limitless_api


class PipelineTests(unittest.TestCase):
    def test_launcher_runs_both_collectors_despite_scraper_failure(self):
        with patch('start_app.subprocess.run', side_effect=[Mock(returncode=1), Mock(returncode=0)]) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(start_app.run_ingestion(), 1)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][-1], 'scraper')
        self.assertEqual(run.call_args_list[1].args[0][-2:], ['api', '--write'])

    def test_launcher_propagates_api_failure_and_optional_cap(self):
        with patch('start_app.subprocess.run', side_effect=[Mock(returncode=0), Mock(returncode=2)]) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(start_app.run_ingestion(2), 2)
        self.assertEqual(run.call_args_list[1].args[0][-4:], ['api', '--write', '--max-events', '2'])

    def test_all_formats_continue_after_one_discovery_failure(self):
        client = Mock()

        def get(path, **params):
            if path == '/games':
                return [{'id': 'VGC', 'formats': {'SVI': 'Regulation I', 'SVH': 'Regulation H'}}]
            if path == '/tournaments':
                if params['format'] == 'SVI':
                    raise requests.ConnectionError('test failure')
                return [{'id': 'abc', 'players': 2, 'date': '2025-01-01T00:00:00Z'}] if params['page'] == 1 else []
            if path.endswith('/details'):
                return {'id': 'abc', 'game': 'VGC', 'format': 'SVH', 'name': 'H event', 'players': 2,
                        'date': '2025-01-01T00:00:00Z'}
            return []

        client.get.side_effect = get
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / 'report.json'
            with patch.object(limitless_api, 'ApiClient', return_value=client), contextlib.redirect_stdout(io.StringIO()):
                result = limitless_api.main(['--before', '2025-02-01', '--cache-dir', temp, '--report', str(report)])
            saved = json.loads(report.read_text())
        self.assertEqual(result, 1)
        self.assertEqual(saved['status'], 'completed_with_errors')
        self.assertEqual(saved['processed'], 1)
        self.assertEqual(saved['formats']['SVI']['failed'], 1)
        self.assertEqual(saved['formats']['SVH']['processed'], 1)

    def test_incremental_import_skips_download_and_reports_database_coverage(self):
        client = Mock()
        client.get.side_effect = [
            [{'id': 'VGC', 'formats': {'SVI': 'Regulation I'}}],
            [{'id': 'known', 'date': '2025-01-01T00:00:00Z', 'players': 2}], []]
        conn = Mock()
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / 'report.json'
            with patch.object(limitless_api, 'ApiClient', return_value=client), \
                 patch.object(limitless_api.pokemon_table, 'get_connection', return_value=conn), \
                 patch.object(limitless_api.ingestion, 'migrate'), \
                 patch.object(limitless_api.ingestion, 'imported_api_ids', return_value={'known'}), \
                 patch.object(limitless_api.ingestion, 'coverage', return_value=[{'regulation': 'I', 'events': 1}]), \
                 patch.object(limitless_api.ingestion, 'load_event') as load, \
                 contextlib.redirect_stdout(io.StringIO()):
                result = limitless_api.main(['--write', '--refresh-days', '0', '--report', str(report)])
            saved = json.loads(report.read_text())
        self.assertEqual(result, 0)
        self.assertEqual(saved['formats']['SVI']['skipped_existing'], 1)
        self.assertEqual(saved['processed'], 0)
        self.assertEqual(saved['database_coverage'][0]['events'], 1)
        load.assert_not_called()
        conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
