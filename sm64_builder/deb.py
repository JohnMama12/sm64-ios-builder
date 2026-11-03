import gzip
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Iterable, Tuple


def _tar_gzip(output: Path, members: Iterable[Tuple[Path, str]]) -> None:
    with output.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as archive:
                for source, archive_name in members:
                    archive.add(str(source), arcname=archive_name, recursive=True)


def _write_ar_member(output, name: str, content_path: Path) -> None:
    size = content_path.stat().st_size
    header = (
        "%-16s%-12d%-6d%-6d%-8o%-10d`\n"
        % (name, 0, 0, 0, 0o100644, size)
    ).encode("ascii")
    if len(header) != 60:
        raise ValueError("Invalid ar member header for %s." % name)
    output.write(header)
    with content_path.open("rb") as content:
        while True:
            chunk = content.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    if size % 2:
        output.write(b"\n")


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
    with tempfile.TemporaryDirectory(prefix="sm64-deb-") as temp_dir:
        temp = Path(temp_dir)
        debian_binary = temp / "debian-binary"
        debian_binary.write_text("2.0\n", encoding="ascii")

        control_dir = temp / "control"
        control_dir.mkdir()
        (control_dir / "control").write_text(control, encoding="utf-8")
        control_tar = temp / "control.tar.gz"
        _tar_gzip(control_tar, [(control_dir / "control", "./control")])

        data_tar = temp / "data.tar.gz"
        _tar_gzip(data_tar, [(app_bundle, "Applications/SM64.app")])

        with output_path.open("wb") as output:
            output.write(b"!<arch>\n")
            for name, member in (
                ("debian-binary", debian_binary),
                ("control.tar.gz", control_tar),
                ("data.tar.gz", data_tar),
            ):
                _write_ar_member(output, name + "/", member)
    return output_path
