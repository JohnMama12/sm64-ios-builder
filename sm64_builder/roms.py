import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import KNOWN_ROMS


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


def validate_rom(path: Path) -> RomValidation:
    path = Path(path).expanduser().resolve()
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
