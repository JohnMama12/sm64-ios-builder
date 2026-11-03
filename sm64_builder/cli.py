import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from .build import build_deb
from .config import (
    DEFAULT_REPOSITORY,
    IOS_SDK_NAME,
    app_data_dir,
    theos_dir,
)
from .github import (
    Commit,
    GitHubError,
    describe_commit,
    list_branches,
    list_ios_commits,
    validate_repository,
)
from .roms import RomValidation, validate_rom
from .setup import SetupError, setup_theos


STATE_FILE = "state.json"
SETUP_MARKER = "setup-verified.json"


def _state_path() -> Path:
    return app_data_dir() / STATE_FILE


def _load_state() -> Dict:
    path = _state_path()
    if not path.is_file():
        return {"repository": DEFAULT_REPOSITORY}
    try:
        with path.open(encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Cannot read builder state at %s: %s" % (path, error)) from error
    if not isinstance(data, dict):
        raise RuntimeError("Builder state file must contain a JSON object.")
    return data


def _save_state(state: Dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _print_commit(index: int, commit: Commit) -> None:
    print(
        "%3d. %s  %s  %s"
        % (index, commit.short_sha, commit.date[:10], commit.message)
    )


def _choose_commit(state: Dict) -> None:
    repository = validate_repository(
        input("GitHub source repository [%s]: " % state.get("repository", DEFAULT_REPOSITORY))
        or state.get("repository", DEFAULT_REPOSITORY)
    )
    print("Loading branches from https://github.com/%s ..." % repository)
    branches = list_branches(repository)
    if not branches:
        raise GitHubError("The selected repository has no branches.")

    prior_branch = state.get("branch")
    default_branch = prior_branch if prior_branch in branches else branches[0]
    for index, branch in enumerate(branches, 1):
        print("%3d. %s%s" % (
            index,
            branch,
            " (saved)" if branch == prior_branch else "",
        ))
    answer = input("Choose branch number [%s]: " % default_branch).strip()
    if not answer:
        branch = default_branch
    else:
        try:
            branch = branches[int(answer) - 1]
        except (ValueError, IndexError) as error:
            raise ValueError("Choose a listed branch number.") from error

    print("Loading iOS commits for %s ..." % branch)
    commits = list_ios_commits(repository, branch)
    if not commits:
        raise GitHubError(
            "No commits touching src/ios were found on %s. Push the iOS source "
            "branch to GitHub first, or select its published repository/branch."
            % branch
        )
    for index, commit in enumerate(commits, 1):
        _print_commit(index, commit)

    answer = input("Choose the exact source commit [1]: ").strip() or "1"
    try:
        selected = commits[int(answer) - 1]
    except (ValueError, IndexError) as error:
        raise ValueError("Choose a listed commit number.") from error

    state["repository"] = repository
    state["branch"] = branch
    state["commit"] = selected.sha
    print("\n" + describe_commit(repository, selected.sha))
    _save_state(state)
    print("\nSelected %s at %s." % (selected.short_sha, branch))


def _choose_rom(state: Dict) -> Optional[RomValidation]:
    previous_path = state.get("rom_path", "")
    path = input("Path to your authentic US .z64 ROM [%s]: " % previous_path).strip()
    if not path:
        path = previous_path
    if not path:
        print("No ROM selected.")
        return None
    validation = validate_rom(Path(path))
    print(validation.message)
    print("SHA-1: %s" % validation.sha1)
    state["rom_path"] = str(validation.path)
    state["rom_sha1"] = validation.sha1
    _save_state(state)
    if not validation.supported:
        return None
    return validation


def _saved_rom(state: Dict) -> Optional[RomValidation]:
    path = state.get("rom_path")
    if not path:
        return None
    validation = validate_rom(Path(path))
    if validation.sha1 != state.get("rom_sha1"):
        print("The selected ROM changed since the last validation; validate it again.")
        return None
    return validation


def _setup(output) -> None:
    record = setup_theos(output)
    marker = app_data_dir() / SETUP_MARKER
    marker.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Setup and armv7/iOS 6.0 Theos package test succeeded.")


def _is_setup_verified() -> bool:
    marker = app_data_dir() / SETUP_MARKER
    if not marker.is_file():
        return False
    theos = theos_dir()
    return (
        (theos / "makefiles" / "common.mk").is_file()
        and (
            theos
            / "sdks"
            / IOS_SDK_NAME
            / "System"
            / "Library"
            / "Frameworks"
            / "UIKit.framework"
        ).is_dir()
        and (theos / "toolchain" / "linux" / "iphone" / "bin" / "clang").is_file()
        and (theos / "toolchain" / "linux" / "iphone" / "bin" / "ldid").is_file()
    )


def _compile(state: Dict) -> None:
    if not _is_setup_verified():
        raise SetupError("Run setup and pass the Theos smoke test before compiling.")
    if not all(state.get(key) for key in ("repository", "branch", "commit")):
        raise ValueError("Select a published iOS source commit first.")
    rom = _saved_rom(state)
    if rom is None or not rom.supported:
        raise ValueError("Select and validate a supported US .z64 ROM first.")

    print(
        "\nROM/license notice: you must own a legally obtained US Super Mario 64 ROM."
    )
    if input("Confirm that you own/use this ROM? [y/N]: ").strip().lower() != "y":
        print("Build cancelled.")
        return
    print(
        "\nLOCAL-ONLY BUILD: src/pc/gfx/LICENSE.txt allows source redistribution "
        "only and forbids binary redistribution. Do not upload or distribute "
        "the generated .deb unless that code is replaced or separately relicensed."
    )
    if input("Continue with a local-only .deb? [y/N]: ").strip().lower() != "y":
        print("Build cancelled.")
        return

    default_jobs = max(1, os.cpu_count() or 1)
    answer = input("Parallel build jobs [%d]: " % default_jobs).strip()
    try:
        jobs = int(answer) if answer else default_jobs
    except ValueError as error:
        raise ValueError("Build jobs must be a positive integer.") from error
    if jobs < 1:
        raise ValueError("Build jobs must be a positive integer.")

    result = build_deb(
        repository=state["repository"],
        branch=state["branch"],
        commit=state["commit"],
        rom=rom,
        jobs=jobs,
        output=print,
    )
    print("\nCreated local-only package: %s" % result.package_path)


def run_cli() -> int:
    app_data_dir().mkdir(parents=True, exist_ok=True)
    try:
        state = _load_state()
    except RuntimeError as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 1

    while True:
        setup_status = "passed" if _is_setup_verified() else "not run"
        selected_commit = state.get("commit")
        commit_display = selected_commit[:8] if selected_commit else "(not selected)"
        print(
            "\nSM64 iOS Builder — WSL console\n"
            "  Setup: %s | Source: %s @ %s | ROM: %s | Commit: %s\n"
            "  1. Set up Theos + iOS 6.1 SDK and run compiler test\n"
            "  2. Choose GitHub source branch and iOS commit\n"
            "  3. Validate an authentic ROM\n"
            "  4. Compile local-only .deb\n"
            "  5. Exit"
            % (
                setup_status,
                state.get("repository", "(not selected)"),
                state.get("branch", "(not selected)"),
                state.get("rom_path", "(not selected)"),
                commit_display,
            )
        )
        try:
            choice = input("Select an action: ").strip()
        except EOFError:
            return 0
        try:
            if choice == "1":
                _setup(print)
            elif choice == "2":
                _choose_commit(state)
            elif choice == "3":
                _choose_rom(state)
            elif choice == "4":
                _compile(state)
            elif choice == "5":
                return 0
            else:
                print("Choose 1, 2, 3, 4, or 5.")
        except (GitHubError, SetupError, OSError, ValueError, RuntimeError) as error:
            print("ERROR: %s" % error, file=sys.stderr)
        except EOFError:
            return 0


def validate_argument(path: str) -> int:
    try:
        rom = validate_rom(Path(path))
    except (OSError, ValueError) as error:
        print("INVALID: %s" % error)
        return 1
    print(rom.message)
    print("Region: %s | SHA-1: %s" % (rom.region, rom.sha1))
    return 0 if rom.supported else 1
