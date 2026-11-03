import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Optional

from .config import KNOWN_ROMS


_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class RomValidation:
    path: Path
    sha1: str
    region: str
    supported: bool

    @property
    def message(self) -> str:
        if self.supported:
            return "ROM Ok! US (NTSC-U) is supported by this iOS build."
        return (
            "This is a recognized %s ROM, but the selected iOS source only "
            "supports US (NTSC-U)." % self.region
        )


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_rom_path(path) -> Path:
    value = os.fspath(path).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()

    if os.name != "nt" and _WINDOWS_DRIVE_PATH.match(value):
        windows_path = PureWindowsPath(value)
        drive = windows_path.drive[0].lower()
        return Path("/mnt") / drive / Path(*windows_path.parts[1:])

    return Path(value).expanduser()


def validate_rom(path: Path) -> RomValidation:
    path = normalize_rom_path(path).resolve()
    if path.suffix.lower() != ".z64":
        raise ValueError("Choose a big-endian .z64 ROM file.")
    if not path.is_file():
        raise ValueError("ROM file does not exist: %s" % path)

    digest = sha1_file(path)
    match: Optional[tuple] = KNOWN_ROMS.get(digest)
    if match is None:
        raise ValueError(
            "Invalid or modified ROM. SHA-1 %s is not a supported authentic "
            "Super Mario 64 dump." % digest
        )
    region, supported = match
    return RomValidation(path, digest, region, supported)
