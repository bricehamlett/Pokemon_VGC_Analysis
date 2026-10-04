import unittest

from Fetch_Data import terminal_output


class TerminalOutputTests(unittest.TestCase):
    def test_clean_event_is_one_compact_line(self):
        text = terminal_output.event_summary({
            "name": "Weekly Cup", "regulation": "M-B",
            "reported_players": 79, "returned_players": 79,
            "placement_candidates": 29, "imported_sheets": 79,
        })
        self.assertEqual(
            text,
            "[OK] M-B | Weekly Cup | players 79/79 | placed 29 | new sheets +79",
        )

    def test_warnings_are_called_out_separately(self):
        text = terminal_output.event_summary({
            "name": "Odd Event", "regulation": "M-B",
            "reported_players": 41, "returned_players": 42,
            "placement_candidates": 17, "imported_sheets": 40,
            "missing": 1, "unresolved": 1,
        })
        self.assertIn("[WARN] M-B | Odd Event", text)
        self.assertIn("source count 42/41", text)
        self.assertIn("missing sheets 1", text)
        self.assertIn("unresolved refs 1", text)

    def test_wait_error_and_final_messages(self):
        self.assertEqual(
            terminal_output.wait_summary("rate_limit_reset", 261.7),
            "[WAIT] API quota exhausted; resuming in 262 seconds.",
        )
        self.assertEqual(
            terminal_output.error_summary({"event_id": "abc", "error": "timeout"}),
            "[ERROR] abc: timeout",
        )
        self.assertIn(
            "3 tournaments imported; 1 failed",
            terminal_output.final_summary(3, 1, "/tmp/report.json", True),
        )
