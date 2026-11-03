import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Optional

from .config import (
    IOS_MIN_VERSION,
    IOS_SDK_NAME,
    IOS_SDK_VERSION,
    SDK_DIRECTORY,
    SDK_REPOSITORY,
    SDK_REPOSITORY_REF,
    THEOS_REPOSITORY,
    TOOLCHAIN_RELEASE_API,
    app_data_dir,
    theos_dir,
)
from .process import capture, run


class SetupError(RuntimeError):
    pass


def _request_json(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "sm64-ios-builder",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        raise SetupError("GitHub request failed for %s: %s" % (url, error)) from error


def _download(url: str, target: Path, expected_size: Optional[int], output):
    request = urllib.request.Request(
        url, headers={"User-Agent": "sm64-ios-builder"}
    )
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        raise SetupError("Download failed from %s: %s" % (url, error)) from error

    total = 0
    with response, target.open("wb") as destination:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            destination.write(chunk)
            total += len(chunk)
            if total % (10 * 1024 * 1024) < len(chunk):
                output("  downloaded %d / %s MB" % (
                    total // (1024 * 1024),
                    str(expected_size // (1024 * 1024))
                    if expected_size is not None
                    else "unknown",
                ))
    if expected_size is not None and total != expected_size:
        target.unlink(missing_ok=True)
        raise SetupError(
            "Download size mismatch for %s: expected %d bytes, received %d."
            % (target.name, expected_size, total)
        )


def _download_sdk_parts(output) -> Path:
    query = urllib.parse.urlencode({"ref": SDK_REPOSITORY_REF})
    folder_url = "https://api.github.com/repos/%s/contents/%s?%s" % (
        SDK_REPOSITORY,
        SDK_DIRECTORY,
        query,
    )
    entries = _request_json(folder_url)
    parts = [
        entry
        for entry in entries
        if entry.get("name", "").startswith(IOS_SDK_NAME + ".zip.")
    ]
    parts.sort(key=lambda item: item["name"])
    if not parts or [part["name"] for part in parts] != [
        IOS_SDK_NAME + ".zip.001",
        IOS_SDK_NAME + ".zip.002",
        IOS_SDK_NAME + ".zip.003",
    ]:
        raise SetupError(
            "The linked SDK repository no longer has the expected iPhoneOS 6.1 "
            "archive parts."
        )

    downloads = app_data_dir() / "downloads" / IOS_SDK_NAME
    downloads.mkdir(parents=True, exist_ok=True)
    archive_path = downloads / (IOS_SDK_NAME + ".zip")
    temporary_parts = []
    try:
        for part in parts:
            part_path = downloads / part["name"]
            if not part_path.is_file() or part_path.stat().st_size != part["size"]:
                output("Downloading %s (%d MB)" % (
                    part["name"],
                    part["size"] // (1024 * 1024),
                ))
                _download(part["download_url"], part_path, part["size"], output)
            digest = hashlib.sha1()
            digest.update(("blob %d\0" % part["size"]).encode("ascii"))
            with part_path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != part["sha"]:
                part_path.unlink(missing_ok=True)
                raise SetupError("GitHub blob hash mismatch for %s." % part["name"])
            temporary_parts.append(part_path)

        with archive_path.open("wb") as combined:
            for part_path in temporary_parts:
                with part_path.open("rb") as source:
                    shutil.copyfileobj(source, combined, length=1024 * 1024)
        with zipfile.ZipFile(archive_path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise SetupError("SDK archive failed ZIP integrity check: %s" % bad_member)
            for info in archive.infolist():
                member = PurePosixPath(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    raise SetupError("Unsafe path in SDK archive: %s" % info.filename)
        return archive_path
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise


def _extract_sdk(archive_path: Path, destination: Path, output) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    extraction_root = Path(
        tempfile.mkdtemp(prefix="sdk-extract-", dir=str(destination.parent))
    )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            root = extraction_root.resolve()
            for info in archive.infolist():
                relative = PurePosixPath(info.filename)
                target = extraction_root.joinpath(*relative.parts)
                resolved = target.resolve()
                if resolved != root and root not in resolved.parents:
                    raise SetupError("SDK archive path escapes extraction directory.")
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    link_target = archive.read(info).decode("utf-8")
                    link_path = (target.parent / link_target).resolve()
                    if root not in link_path.parents:
                        raise SetupError("SDK archive contains an unsafe symlink.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(link_target)
                elif info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as output_file:
                        shutil.copyfileobj(source, output_file, length=1024 * 1024)
        candidates = [
            path
            for path in extraction_root.rglob(SDK_DIRECTORY)
            if path.is_dir()
            and (path / "System" / "Library" / "Frameworks" / "UIKit.framework").is_dir()
        ]
        if len(candidates) != 1:
            raise SetupError(
                "Could not identify one complete %s in the downloaded archive."
                % SDK_DIRECTORY
            )
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(candidates[0]), str(destination))
        output("Installed SDK at %s" % destination)
        return destination
    finally:
        shutil.rmtree(extraction_root, ignore_errors=True)


def _install_system_dependencies(output) -> None:
    required = (
        "build-essential",
        "ca-certificates",
        "curl",
        "fakeroot",
        "git",
        "gettext",
        "gettext-base",
        "libtinfo6",
        "libxml2",
        "make",
        "perl",
        "python3",
        "rsync",
        "unzip",
        "xz-utils",
        "zip",
        "dpkg-dev",
    )
    missing = [
        package
        for package in (
            "git",
            "make",
            "curl",
            "fakeroot",
            "dpkg-deb",
            "unzip",
            "xz",
            "gettext",
            "envsubst",
            "clang",
            "python3",
        )
        if shutil.which(package) is None
    ]
    if not missing:
        output("WSL build prerequisites are already installed.")
        return
    if os.geteuid() == 0:
        prefix = []
    elif shutil.which("sudo"):
        prefix = ["sudo"]
    else:
        raise SetupError(
            "Missing build tools (%s). Install the Debian packages with root "
            "access, then run setup again." % ", ".join(missing)
        )
    output("Installing WSL build prerequisites with apt.")
    run(prefix + ["apt-get", "update"], output=output)
    run(prefix + ["apt-get", "install", "-y", *required], output=output)


def _install_theos(output) -> str:
    target = theos_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not (target / ".git").is_dir():
        if target.exists() and any(target.iterdir()):
            raise SetupError(
                "The Theos destination exists but is not a Git checkout: %s" % target
            )
        output("Cloning Theos and its submodules.")
        run(
            ["git", "clone", "--recursive", THEOS_REPOSITORY, str(target)],
            output=output,
        )
    else:
        output("Using the already installed Theos checkout (no automatic update).")
    revision = capture(["git", "rev-parse", "HEAD"], cwd=target)
    if not (target / "makefiles" / "common.mk").is_file():
        raise SetupError("The Theos checkout is incomplete.")
    return revision


def _install_toolchain(output) -> Dict[str, str]:
    theos = theos_dir()
    clang = theos / "toolchain" / "linux" / "iphone" / "bin" / "clang"
    release_marker = theos / "toolchain" / ".sm64-ios-builder-release"
    if clang.is_file() and os.access(clang, os.X_OK):
        output("Using the installed Theos Linux iOS toolchain.")
        if release_marker.is_file():
            release_name = release_marker.read_text(encoding="utf-8").strip()
        else:
            release_name = "preinstalled-unknown"
        return {"release": release_name, "clang": str(clang)}

    release = _request_json(TOOLCHAIN_RELEASE_API)
    asset = next(
        (
            item
            for item in release.get("assets", [])
            if item.get("name") == "iOSToolchain-x86_64.tar.xz"
        ),
        None,
    )
    if asset is None:
        raise SetupError("Latest Theos Linux toolchain release has no x86_64 asset.")
    downloads = app_data_dir() / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / asset["name"]
    if not archive.is_file() or (
        asset.get("size") and archive.stat().st_size != asset["size"]
    ):
        output("Downloading Theos toolchain release %s." % release["tag_name"])
        _download(asset["browser_download_url"], archive, asset.get("size"), output)
    digest = asset.get("digest")
    if digest and digest.startswith("sha256:"):
        sha256 = hashlib.sha256()
        with archive.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                sha256.update(chunk)
        if sha256.hexdigest() != digest.split(":", 1)[1]:
            archive.unlink(missing_ok=True)
            raise SetupError("Theos toolchain SHA-256 does not match GitHub metadata.")

    toolchain_dir = theos / "toolchain"
    toolchain_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="theos-toolchain-") as temp_dir:
        temp = Path(temp_dir)
        with tarfile.open(str(archive), mode="r:xz") as toolchain:
            root = temp.resolve()
            for member in toolchain.getmembers():
                member_path = Path(member.name)
                target = temp / member_path
                resolved = target.resolve()
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or (resolved != root and root not in resolved.parents)
                ):
                    raise SetupError("Unsafe path in Theos toolchain archive.")
                if member.issym():
                    link_target = (target.parent / member.linkname).resolve()
                    if root not in link_target.parents:
                        raise SetupError("Unsafe symlink in Theos toolchain archive.")
                elif member.islnk():
                    link_target = (temp / member.linkname).resolve()
                    if link_target != root and root not in link_target.parents:
                        raise SetupError("Unsafe hard link in Theos toolchain archive.")
                elif not (member.isfile() or member.isdir()):
                    raise SetupError("Unsupported file in Theos toolchain archive.")
                toolchain.extract(member, temp)
        extracted = temp / "linux" / "iphone" / "bin" / "clang"
        if not extracted.is_file():
            raise SetupError("Downloaded archive does not contain the Linux iOS clang.")
        for item in temp.iterdir():
            destination = toolchain_dir / item.name
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            shutil.move(str(item), str(destination))
    clang = toolchain_dir / "linux" / "iphone" / "bin" / "clang"
    clang.chmod(clang.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    release_marker.write_text(release["tag_name"] + "\n", encoding="utf-8")
    return {"release": release["tag_name"], "clang": str(clang)}


def run_smoke_test(output) -> None:
    theos = theos_dir()
    sdk = theos / "sdks" / IOS_SDK_NAME
    clang = theos / "toolchain" / "linux" / "iphone" / "bin" / "clang"
    if not sdk.is_dir() or not clang.is_file():
        raise SetupError("Theos toolchain or iOS SDK is missing.")
    with tempfile.TemporaryDirectory(
        prefix="sm64-theos-smoke-", dir=str(app_data_dir())
    ) as temp_dir:
        project = Path(temp_dir)
        makefile = (
            "TARGET = iphone:clang:%s:%s\n"
            "ARCHS = armv7\n"
            "include $(THEOS)/makefiles/common.mk\n"
            "APPLICATION_NAME = BuilderSmokeTest\n"
            "BuilderSmokeTest_FILES = main.m\n"
            "BuilderSmokeTest_FRAMEWORKS = UIKit\n"
            "include $(THEOS_MAKE_PATH)/application.mk\n"
            % (IOS_SDK_VERSION, IOS_MIN_VERSION)
        )
        (project / "Makefile").write_text(makefile, encoding="utf-8")
        (project / "main.m").write_text(
            "#import <UIKit/UIKit.h>\nint main(void) { return 0; }\n",
            encoding="utf-8",
        )
        (project / "control").write_text(
            "Package: com.sm64decomp.builder-smoke\n"
            "Name: Theos Builder Smoke Test\n"
            "Version: 1.0\n"
            "Architecture: iphoneos-arm\n"
            "Description: Local Theos armv7 compiler preflight\n"
            "Maintainer: SM64 iOS Builder\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["THEOS"] = str(theos)
        env["PATH"] = str(clang.parent) + os.pathsep + env.get("PATH", "")
        output("Running a clean Theos armv7/iOS 6.0 application package test.")
        run(["make", "package"], cwd=project, env=env, output=output)
        packages = list((project / "packages").glob("*.deb"))
        if len(packages) != 1:
            raise SetupError("The Theos smoke test did not produce exactly one .deb.")
        run(["dpkg-deb", "--info", str(packages[0])], output=output)
        output("Theos smoke test passed: %s" % packages[0].name)


def setup_theos(output) -> Dict[str, str]:
    if os.geteuid() == 0:
        raise SetupError(
            "Theos must be installed as a normal WSL user. Start this CLI with "
            "your non-root WSL account (not `wsl --user root`)."
        )
    app_data_dir().mkdir(parents=True, exist_ok=True)
    _install_system_dependencies(output)
    revision = _install_theos(output)
    toolchain = _install_toolchain(output)

    sdk = theos_dir() / "sdks" / IOS_SDK_NAME
    if not (sdk / "System" / "Library" / "Frameworks" / "UIKit.framework").is_dir():
        output("Downloading the iPhoneOS 6.1 SDK from %s." % SDK_REPOSITORY)
        archive = _download_sdk_parts(output)
        _extract_sdk(archive, theos_dir() / "sdks" / IOS_SDK_NAME, output)
    else:
        output("Using the installed iPhoneOS 6.1 SDK.")

    record = {
        "theos_commit": revision,
        "toolchain_release": toolchain["release"],
        "sdk": IOS_SDK_NAME,
        "target_minimum": IOS_MIN_VERSION,
    }
    record_path = app_data_dir() / "toolchain.json"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    run_smoke_test(output)
    return record
