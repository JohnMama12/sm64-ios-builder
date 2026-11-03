import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from sm64_builder.deb import create_deb


class DebianPackageTests(unittest.TestCase):
    def test_creates_device_installable_gzip_deb_with_root_ownership(self):
        if not shutil.which("dpkg-deb"):
            self.skipTest("dpkg-deb is not installed.")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = root / "SM64.app"
            app.mkdir()
            (app / "Info.plist").write_text("<plist/>", encoding="utf-8")
            executable = app / "sm64ios"
            executable.write_bytes(b"test-binary")
            executable.chmod(0o755)
            package = create_deb(
                app,
                root / "sm64.deb",
                "com.sm64decomp.ios",
                "1.0+12345678",
            )
            self.assertEqual(package.read_bytes()[:8], b"!<arch>\n")
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
            self.assertIn("root/root", contents.stdout)
            self.assertIn("-rwxr-xr-x", contents.stdout)

            filesystem_tar = subprocess.run(
                ["dpkg-deb", "--fsys-tarfile", str(package)],
                capture_output=True,
                check=True,
            ).stdout
            with tempfile.NamedTemporaryFile() as tar_file:
                tar_file.write(filesystem_tar)
                tar_file.flush()
                subprocess.run(
                    ["tar", "-tf", tar_file.name],
                    capture_output=True,
                    text=True,
                    check=True,
                )


if __name__ == "__main__":
    unittest.main()
