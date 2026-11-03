import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sm64_builder import cli


class CliTests(unittest.TestCase):
    def test_end_of_input_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(cli, "app_data_dir", return_value=Path(temp_dir)):
                with patch("builtins.input", side_effect=EOFError):
                    self.assertEqual(cli.run_cli(), 0)


if __name__ == "__main__":
    unittest.main()
