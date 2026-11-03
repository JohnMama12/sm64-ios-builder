import subprocess
import tempfile
import unittest
from pathlib import Path

from sm64_builder.deb import create_deb


class DebianPackageTests(unittest.TestCase):
    def test_creates_valid_deb_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = root / "SM64.app"
            app.mkdir()
            (app / "Info.plist").write_text("<plist/>", encoding="utf-8")
            (app / "sm64ios").write_bytes(b"test-binary")
            package = create_deb(
                app,
                root / "sm64.deb",
                "com.sm64decomp.ios",
                "1.0+12345678",
            )
            self.assertEqual(package.read_bytes()[:8], b"!<arch>\n")
            if subprocess.call(["dpkg-deb", "--version"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0:
                result = subprocess.run(
                    ["dpkg-deb", "--info", str(package)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertIn("com.sm64decomp.ios", result.stdout + result.stderr)
                contents = subprocess.run(
                    ["dpkg-deb", "--contents", str(package)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertIn("Applications/SM64.app/Info.plist", contents.stdout)
                self.assertIn("Applications/SM64.app/sm64ios", contents.stdout)


if __name__ == "__main__":
    unittest.main()
