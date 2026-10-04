import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
import requests
from Fetch_Data import official_standings as official, ingestion


def page(resource, payload):
    body = json.dumps({'status': 200, 'body': json.dumps({'ok': True, 'message': payload})})
    return f'<script type="application/json" data-sveltekit-fetched data-url="https://mew.limitlesstcg.com/labs/data/vgc/{resource}?id=1">{body}</script>'


def event():
    return {'event_id': 443, 'event_name': 'Example', 'event_date': '2026-09-26',
            'event_size': 2, 'regulation': 'M-C'}


def rows():
    return [{'tp_id': 10, 'name': 'Alice Smith', 'placement': 1, 'country': 'US',
             'wins': 2, 'losses': 0, 'teamlist': 1},
            {'tp_id': 11, 'name': 'Bob Jones', 'placement': 2, 'country': 'UK',
             'wins': 0, 'losses': 2, 'teamlist': 0, 'drop_round': 2}]


class OfficialTests(unittest.TestCase):
    def collect(self, data=None, legacy='', info=None):
        data = rows() if data is None else data
        client = Mock()
        client.get.side_effect = [page('tournament', info or {'completed': 1, 'players': 2}) + page('standings', data),
                                  page('teamlist', [{'id': 'landorus', 'ability': 'Sand Force',
                                                   'item': None, 'moves': ['Protect'], 'tera': None}])]
        result = official.collect(event(), BeautifulSoup(legacy, 'html.parser'),
                                  'https://standings.limitlessvgc.com/0039/standings', client)
        return result, client

    def test_unfiltered_payload_and_missing_sheet_retained(self):
        result, client = self.collect()
        self.assertEqual(len(result['teams']), 2)
        self.assertEqual(result['teams'][1]['pokemon'], [])
        self.assertEqual(result['teams'][1]['record']['losses'], 2)
        self.assertEqual(result['teams'][0]['pokemon'][0]['pokemon_name'], 'landorus-incarnate')
        self.assertEqual(client.get.call_count, 2)
        normalized = ingestion.normalize_scraped(result)
        self.assertEqual(normalized['teams'][0]['external_player_id'], '443:standings:10')
        self.assertEqual(ingestion.audit(normalized)['missing'], 1)
        self.assertEqual(ingestion.audit(normalized)['unreturned_players'], 0)

    def test_shortened_name_alias_and_changed_placement(self):
        legacy = '<tr data-rank="1" data-name="Alice Marie Smith" data-country="US"></tr>'
        result, _ = self.collect(legacy=legacy)
        self.assertEqual(result['teams'][0]['legacy_player_name'], 'Alice Marie Smith')
        result, _ = self.collect(legacy='<tr data-rank="2" data-name="ALÍCE SMITH"></tr>')
        self.assertEqual(result['teams'][0]['legacy_player_name'], 'ALÍCE SMITH')

    def test_reordered_name_requires_same_placement_country_and_unique_match(self):
        legacy = BeautifulSoup('<tr data-rank="80" data-name="Huang Jianzheng" '
                               'data-country="CN"></tr>', 'html.parser')
        row = {'tp_id': 84, 'name': 'Jianzheng Huang', 'placement': 80, 'country': 'CN'}
        self.assertEqual(official.match_results_players(legacy, [row]), ({'84': 'Huang Jianzheng'}, [], set()))
        for candidates in ([{**row, 'placement': 81}], [{**row, 'country': 'US'}],
                           [row, {**row, 'tp_id': 85}], [{**row, 'name': 'Other Huang'}]):
            with self.subTest(candidates=candidates):
                aliases, reviews, blocked = official.match_results_players(legacy, candidates)
                self.assertEqual(aliases, {})
                self.assertEqual(len(reviews), 1)

    def test_incomplete_duplicate_live_and_ambiguous_standings_fail(self):
        for data, info, legacy in [
            (rows()[:1], None, ''),
            ([rows()[0], rows()[0]], None, ''),
            (rows(), {'completed': 0, 'players': 2}, ''),
        ]:
            with self.subTest(data=data, info=info), self.assertRaises(ValueError):
                self.collect(data, legacy, info)

    def test_unmatched_player_is_queued_without_blocking_other_entrants(self):
        result, _ = self.collect(legacy='<tr data-rank="1" data-name="Different Person"></tr>')
        self.assertEqual(len(result['teams']), 2)
        self.assertTrue(result['teams'][0]['identity_pending'])
        self.assertFalse(result['teams'][1]['identity_pending'])
        review = ingestion.normalize_scraped(result)['identity_reviews'][0]
        self.assertEqual(review['legacy_names'], ['Different Person'])
        self.assertEqual(review['candidate_ids'], ['10'])

    def test_colliding_claims_quarantine_both_instead_of_first_match_winning(self):
        legacy = BeautifulSoup('<tr data-rank="1" data-name="Alice Smith"></tr>'
                               '<tr data-rank="1" data-name="ALICE SMITH"></tr>', 'html.parser')
        aliases, reviews, blocked = official.match_results_players(legacy, rows())
        self.assertEqual(aliases, {})
        self.assertEqual(len(reviews), 2)
        self.assertEqual(blocked, {'10'})

    def test_changed_markup_fails_instead_of_top256_fallback(self):
        with self.assertRaises(ValueError):
            official.embedded('<table><tr><td>Only visible players</td></tr></table>', 'standings')

    def test_page_cache_retry_and_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            client = official.PageClient(directory)
            response = Mock(text=page('teamlist', []))
            client.session.get = Mock(side_effect=[requests.Timeout(), response])
            with patch.object(official.time, 'sleep'):
                first = client.get('https://standings.limitlessvgc.com/1/player/2/teamlist', cache=True)
                self.assertEqual(first, client.get('https://standings.limitlessvgc.com/1/player/2/teamlist', cache=True))
            self.assertEqual(client.session.get.call_count, 2)
            client.refresh = True
            client.session.get = Mock(return_value=response)
            with patch.object(official.time, 'sleep'):
                client.get('https://standings.limitlessvgc.com/1/player/2/teamlist', cache=True)
            self.assertEqual(client.session.get.call_count, 1)

    def test_scraper_routes_to_full_standings_and_retains_missing_fallback(self):
        from Fetch_Data import scraping_limitless as scraper
        html = ('<div class="infobox-heading">Example</div>'
                '<div class="infobox-line">26th September 2026 • 2 Players • '
                '<a>Regulation Set M-C</a></div>'
                '<tr data-rank="1" data-name="Alice" data-country="US"></tr>')
        response = Mock(text=html)
        with patch.object(scraper.requests, 'get', return_value=response):
            result = scraper.get_event_details(443)
        self.assertEqual(result['teams'][0]['pokemon'], [])
        self.assertEqual(result['metadata']['coverage_scope'], 'results_page')
        response.text += '<a href="https://standings.limitlessvgc.com/0039/standings">Standings</a>'
        with patch.object(scraper.requests, 'get', return_value=response), \
             patch.object(official, 'collect', return_value={'full': True}) as collect:
            self.assertEqual(scraper.get_event_details(443), {'full': True})
        self.assertEqual(collect.call_args.args[2], 'https://standings.limitlessvgc.com/0039/standings')

    def test_report_distinguishes_absent_entrants_from_missing_sheets(self):
        raw = event()
        raw['teams'] = []
        report = ingestion.audit(ingestion.normalize_scraped(raw))
        self.assertEqual(report['unreturned_players'], 2)
        self.assertEqual(report['missing'], 0)
