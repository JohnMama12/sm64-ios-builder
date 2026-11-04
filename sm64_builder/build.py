import re
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Tuple

from .config import (
    IOS_MIN_VERSION,
    IOS_SDK_NAME,
    IOS_SDK_VERSION,
    PACKAGE_ARCHITECTURE,
    PACKAGE_MIN_IOS,
    PACKAGE_NAME,
    app_data_dir,
    theos_dir,
)
from .deb import create_deb
from .github import validate_repository
from .process import capture, run
from .roms import RomValidation


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildResult:
    source_version: str
    source_commit: str
    rom_sha1: str
    package_path: Path


def _build_directory(repository: str, source_ref: str, rom_sha1: str) -> Path:
    slug = repository.replace("/", "-").lower()
    ref_slug = re.sub(r"[^A-Za-z0-9.+~-]+", "-", source_ref).strip("-")
    return app_data_dir() / "builds" / (
        "%s-%s-%s" % (slug, ref_slug, rom_sha1[:12])
    )


def _clone_at_ref(
    repository: str,
    source_ref: str,
    source_kind: str,
    rom_sha1: str,
    output: Callable[[str], None],
) -> Tuple[Path, str]:
    repository = validate_repository(repository)
    if source_kind == "release":
        if not re.fullmatch(
            r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
            source_ref,
        ):
            raise ValueError("Selected source release must use a semantic version tag.")
    elif source_kind == "branch":
        if (
            not source_ref
            or source_ref.startswith("-")
            or source_ref.startswith("/")
            or source_ref.endswith("/")
            or ".." in source_ref
            or not re.fullmatch(r"[A-Za-z0-9._/-]+", source_ref)
        ):
            raise ValueError("Selected source branch name is invalid.")
    else:
        raise ValueError("Source kind must be 'release' or 'branch'.")
    source_url = "https://github.com/%s.git" % repository
    target = _build_directory(repository, source_ref, rom_sha1)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        output("Removing the previous build workspace for this version/ROM pair.")
        shutil.rmtree(target)

    output("Cloning %s, source %s %s." % (repository, source_kind, source_ref))
    run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--branch",
            source_ref,
            source_url,
            str(target),
        ],
        output=output,
    )
    resolved = capture(["git", "rev-parse", "HEAD"], cwd=target)
    if not re.fullmatch(r"[0-9a-f]{40}", resolved.lower()):
        raise BuildError("Git returned an invalid source commit for %s." % source_ref)
    output(
        "Pinned source %s %s to commit %s."
        % (source_kind, source_ref, resolved.lower())
    )
    return target, resolved.lower()


def build_deb(
    repository: str,
    source_ref: str,
    source_kind: str,
    rom: RomValidation,
    jobs: int,
    output: Callable[[str], None],
) -> BuildResult:
    if not rom.supported or rom.region != "US":
        raise BuildError("Only a verified US (NTSC-U) ROM can be built.")
    if jobs < 1:
        raise ValueError("Build job count must be at least one.")

    theos = theos_dir()
    sdk = theos / "sdks" / IOS_SDK_NAME
    clang = theos / "toolchain" / "linux" / "iphone" / "bin" / "clang"
    if not sdk.is_dir() or not clang.is_file():
        raise BuildError("Run the Theos setup and smoke test before compiling.")

    root, commit = _clone_at_ref(
        repository, source_ref, source_kind, rom.sha1, output
    )
    if not (root / "src" / "ios" / "Makefile.ios").is_file():
        raise BuildError("Selected commit does not contain src/ios/Makefile.ios.")
    if not (root / "extract_assets.py").is_file() or not (root / "assets.json").is_file():
        raise BuildError("Selected commit does not contain the asset extraction pipeline.")

    rom_target = root / "baserom.us.z64"
    shutil.copy2(rom.path, rom_target)

    output("Extracting game data for US ROM with `make assets`.")
    output("This creates generated C/data only; it does not build the Windows game executable.")
    try:
        run(["make", "-j%d" % jobs, "assets", "VERSION=us"], cwd=root, output=output)
    finally:
        rom_target.unlink(missing_ok=True)

    ios_dir = root / "src" / "ios"
    env = os.environ.copy()
    env["THEOS"] = str(theos)
    toolchain_bin = clang.parent
    env["PATH"] = os.pathsep.join(
        (str(toolchain_bin), str(theos / "bin"), env.get("PATH", ""))
    )
    output("Compiling the armv7 iOS app against %s." % IOS_SDK_NAME)
    run(
        [
            "make",
            "-f",
            "Makefile.ios",
            "game",
            "GAME_OPT=-O0",
            "SYSROOT=%s" % sdk,
            "CC=%s" % clang,
            "GAME_CC=%s" % clang,
        ],
        cwd=ios_dir,
        env=env,
        output=output,
    )

    app_bundle = ios_dir / "build" / "SM64.app"
    package_dir = app_data_dir() / "packages"
    if source_kind == "release":
        package_version = (
            source_ref.removeprefix("v").replace("-", "~")
            + "+"
            + commit[:8]
        )
    else:
        branch_slug = re.sub(r"[^A-Za-z0-9.+~-]+", "-", source_ref).strip("-")
        package_version = "0~branch-%s+%s" % (branch_slug.lower(), commit[:8])
    output_path = package_dir / (
        "sm64_%s_%s.deb" % (package_version, PACKAGE_ARCHITECTURE)
    )
    output("Creating local package %s." % output_path)
    package = create_deb(
        app_bundle=app_bundle,
        output_path=output_path,
        package=PACKAGE_NAME,
        version=package_version,
        architecture=PACKAGE_ARCHITECTURE,
        minimum_ios=PACKAGE_MIN_IOS,
    )
    run(["dpkg-deb", "--info", str(package)], output=output)
    output("Build complete: %s" % package)
    return BuildResult(
        "%s:%s" % (source_kind, source_ref), commit, rom.sha1, package
    )
