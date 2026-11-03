import shutil
import subprocess
import tempfile
from pathlib import Path


def create_deb(
    app_bundle: Path,
    output_path: Path,
    package: str,
    version: str,
    architecture: str = "iphoneos-arm",
    minimum_ios: str = "6.0",
) -> Path:
    app_bundle = Path(app_bundle).resolve()
    output_path = Path(output_path).resolve()
    if not app_bundle.is_dir():
        raise FileNotFoundError("Built app bundle not found: %s" % app_bundle)
    if not (app_bundle / "Info.plist").is_file():
        raise ValueError("App bundle has no Info.plist.")
    if not any(path.is_file() for path in app_bundle.iterdir()):
        raise ValueError("App bundle is empty.")
    if shutil.which("dpkg-deb") is None:
        raise RuntimeError("dpkg-deb is required to create a device-installable package.")

    control = (
        "Package: %s\n"
        "Name: SM64\n"
        "Version: %s\n"
        "Architecture: %s\n"
        "Depends: firmware (>= %s)\n"
        "Description: Super Mario 64 iOS application\n"
        "Maintainer: SM64 iOS Builder\n"
        "Section: Games\n"
        "Priority: optional\n"
        % (package, version, architecture, minimum_ios)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".sm64-deb-", dir=str(output_path.parent)
    ) as temp_dir:
        temp = Path(temp_dir)
        package_root = temp / "root"
        package_root.mkdir()
        control_dir = package_root / "DEBIAN"
        control_dir.mkdir()
        (control_dir / "control").write_text(control, encoding="utf-8")

        app_destination = package_root / "Applications" / "SM64.app"
        app_destination.parent.mkdir(parents=True)
        shutil.copytree(app_bundle, app_destination, copy_function=shutil.copy2)

        temporary_package = temp / output_path.name
        result = subprocess.run(
            [
                "dpkg-deb",
                "--build",
                "--root-owner-group",
                "--deb-format=2.0",
                "--compression=gzip",
                "--compression-level=9",
                str(package_root),
                str(temporary_package),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            details = (result.stdout + result.stderr).strip()
            raise RuntimeError(
                "dpkg-deb failed to create the iOS package: %s" % details
            )
        temporary_package.replace(output_path)
    return output_path
