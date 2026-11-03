import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sm64_builder.roms import (
    RomValidation,
    normalize_rom_path,
    sha1_file,
    validate_rom,
)


class RomValidationTests(unittest.TestCase):
    def test_normalizes_windows_drive_path_for_wsl(self):
        if os.name == "nt":
            self.skipTest("Windows paths are native on Windows.")
        self.assertEqual(
            normalize_rom_path(r"C:\Users\MW\Downloads\baserom.us.z64"),
            Path("/mnt/c/Users/MW/Downloads/baserom.us.z64"),
        )

    def test_normalizes_quoted_mixed_separator_path_for_wsl(self):
        if os.name == "nt":
            self.skipTest("Windows paths are native on Windows.")
        self.assertEqual(
            normalize_rom_path('"C:/Users/MW/Downloads\\baserom.us.z64"'),
            Path("/mnt/c/Users/MW/Downloads/baserom.us.z64"),
        )

    def test_hash_streams_file(self):
        content = b"rom-data"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "game.z64"
            path.write_bytes(content)
            self.assertEqual(sha1_file(path), hashlib.sha1(content).hexdigest())

    def test_rejects_non_z64_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "game.v64"
            path.write_bytes(b"not-a-rom")
            with self.assertRaisesRegex(ValueError, "big-endian .z64"):
                validate_rom(path)

    def test_rejects_unknown_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "game.z64"
            path.write_bytes(b"not-a-known-rom")
            with self.assertRaisesRegex(ValueError, "not a supported authentic"):
                validate_rom(path)

    def test_known_but_unsupported_region_is_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "game.z64"
            path.write_bytes(b"known-rom")
            with patch(
                "sm64_builder.roms.sha1_file",
                return_value="8a20a5c83d6ceb0f0506cfc9fa20d8f438cafe51",
            ):
                result = validate_rom(path)
            self.assertIsInstance(result, RomValidation)
            self.assertEqual(result.region, "JP")
            self.assertFalse(result.supported)


if __name__ == "__main__":
    unittest.main()
