import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sm64_builder.roms import RomValidation, sha1_file, validate_rom


class RomValidationTests(unittest.TestCase):
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
