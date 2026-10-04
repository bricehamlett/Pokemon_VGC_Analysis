import unittest
from Fetch_Data import normalization as n, ingestion, scraping_limitless as scraper


class SharedNormalizationTests(unittest.TestCase):
    def test_source_spellings_converge(self):
        variants = [({'id': 'indeedee-f', 'name': 'Female Indeedee'}, 'indeedee-female'),
                    ({'name': 'Female Indeedee'}, 'indeedee-female'),
                    ({'id': 'landorus-therian', 'name': 'Therian Landorus'}, 'landorus-therian'),
                    ({'id': 'landorus', 'name': 'Landorus Therian'}, 'landorus-therian'),
                    ({'name': 'Ice Rider Calyrex'}, 'calyrex-ice'),
                    ({'id': 'calyrex-ice-rider', 'name': 'Ice Rider Calyrex'}, 'calyrex-ice'),
                    ({'name': 'Hisuian Arcanine'}, 'arcanine-hisui')]
        for raw, expected in variants:
            with self.subTest(raw=raw):
                got = n.pokemon(raw)
                self.assertEqual(got['pokemon_name'], expected)
                self.assertEqual(got['normalization_issues'], [])

    def test_explicit_forms_never_collapsed(self):
        for form in ('lycanroc-dusk', 'lycanroc-midnight', 'palafin-hero', 'palafin-zero',
                     'maushold-family-of-three', 'maushold-family-of-four',
                     'indeedee-male', 'indeedee-female', 'landorus-therian', 'landorus-incarnate'):
            with self.subTest(form=form):
                self.assertEqual(n.pokemon({'id': form})['pokemon_name'], form)
                self.assertEqual(scraper.edge_case_names(form), form)

    def test_api_display_form_order_matches_identifier(self):
        for identifier, display in [('dialga-origin', 'Origin Forme Dialga'),
                                    ('toxtricity-low-key', 'Low Key Toxtricity'),
                                    ('kyurem-white', 'White Kyurem'),
                                    ('charizard-mega-x', 'Mega Charizard X'),
                                    ('lapras-gmax', 'Gigantamax Lapras')]:
            with self.subTest(identifier=identifier):
                p = n.pokemon({'id': identifier, 'name': display})
                self.assertEqual(p['pokemon_name'], identifier)
                self.assertEqual(p['normalization_issues'], [])

    def test_ambiguous_and_contradictory_forms_excluded_from_training(self):
        for raw in ({'name': 'Indeedee'}, {'name': 'Maushold'},
                    {'id': 'indeedee-f', 'name': 'Male Indeedee'}):
            p = n.pokemon(raw)
            self.assertTrue(any(x.startswith('error:') for x in p['normalization_issues']))
            status, issues = ingestion.assess({'pokemon': [p], 'requires_tera': False}, 10)
            self.assertEqual(status, 'invalid')
            self.assertIn(p['normalization_issues'][0], issues)

    def test_abilities_items_and_source_evidence(self):
        raw = {'id': 'calyrex-ice-rider', 'ability': 'As One', 'item': 'Held Item:',
               'attacks': ['Protect', '-'], 'tera': 'Ice'}
        p = n.pokemon(raw)
        self.assertEqual(p['ability'], 'as-one-glastrier')
        self.assertIsNone(p['item'])
        self.assertEqual(p['moves'], ['protect'])
        self.assertEqual(p['source_fields'], raw)
        self.assertEqual(n.pokemon({'id': 'ursaluna-bloodmoon', 'ability': 'Mind'})['ability'], 'minds-eye')

    def test_api_uses_same_build_normalization_as_html_and_standings(self):
        raw = {'id': 'indeedee-f', 'name': 'Female Indeedee', 'ability': 'Psychic Surge',
               'item': 'Psychic Seed', 'moves': ['Protect'], 'tera': 'Fairy'}
        details = {'id': 'example', 'format': 'SVI', 'name': 'Example',
                   'date': '2025-01-01', 'players': 2}
        event = ingestion.normalize_api(details, [{'player': 'one', 'decklist': [raw]}], None, 'Regulation I')
        self.assertEqual(event['teams'][0]['pokemon'][0], n.pokemon(raw))
