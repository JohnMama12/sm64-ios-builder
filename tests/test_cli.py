import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sm64_builder import cli


class CliTests(unittest.TestCase):
    def test_end_of_input_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(cli, "app_data_dir", return_value=Path(temp_dir)):
                with patch("builtins.input", side_effect=EOFError):
                    self.assertEqual(cli.run_cli(), 0)

    def test_select_option_uses_numbered_input_without_a_tty(self):
        terminal = Mock()
        terminal.isatty.return_value = False
        with patch.object(cli.sys, "stdin", terminal):
            with patch("builtins.input", return_value="2"):
                self.assertEqual(cli._select_option("Choose one", ["A", "B"]), 1)

    def test_select_option_uses_default_on_empty_input(self):
        terminal = Mock()
        terminal.isatty.return_value = False
        with patch.object(cli.sys, "stdin", terminal):
            with patch("builtins.input", return_value=""):
                self.assertEqual(
                    cli._select_option("Choose one", ["A", "B"], default_index=1),
                    1,
                )

    def test_select_option_rejects_out_of_range_number(self):
        terminal = Mock()
        terminal.isatty.return_value = False
        with patch.object(cli.sys, "stdin", terminal):
            with patch("builtins.input", side_effect=["3", "2"]):
                self.assertEqual(cli._select_option("Choose one", ["A", "B"]), 1)

    def test_select_option_can_be_cancelled(self):
        terminal = Mock()
        terminal.isatty.return_value = False
        with patch.object(cli.sys, "stdin", terminal):
            with patch("builtins.input", return_value="q"):
                self.assertIsNone(cli._select_option("Choose one", ["A", "B"]))


if __name__ == "__main__":
    unittest.main()
