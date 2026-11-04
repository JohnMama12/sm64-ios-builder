import curses
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
    GitHubError,
    list_source_branches,
    list_source_releases,
    validate_repository,
)
from .roms import RomValidation, validate_rom
from .setup import SetupError, setup_theos


STATE_FILE = "state.json"
SETUP_MARKER = "setup-verified.json"

MAIN_ACTIONS = (
    "Set up iOS Compiler (Theos)",
    "Choose iOS Source",
    "Validate your US ROM",
    "Build Game",
    "Exit",
)


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


def _safe_addstr(screen, row: int, column: int, text: str, style: int = 0) -> None:
    height, width = screen.getmaxyx()
    if row < 0 or row >= height or column < 0 or column >= width:
        return
    ascii_text = str(text).encode("ascii", errors="replace").decode("ascii")
    try:
        screen.addnstr(row, column, ascii_text, width - column - 1, style)
    except curses.error:
        pass


def _curses_menu(screen, title: str, options, selected: int, status_lines=()):
    screen.keypad(True)
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    normal = curses.A_NORMAL
    heading = curses.A_BOLD
    selected_style = curses.A_REVERSE | curses.A_BOLD
    status_style = curses.A_BOLD
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLUE)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLUE)
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_WHITE)
        normal = curses.color_pair(1)
        heading = curses.color_pair(2) | curses.A_BOLD
        selected_style = curses.color_pair(4) | curses.A_BOLD
        status_style = curses.color_pair(3) | curses.A_BOLD
        screen.bkgd(" ", normal)

    selected = min(max(selected, 0), len(options) - 1)
    while True:
        screen.erase()
        height, width = screen.getmaxyx()
        if height < 12 or width < 48:
            _safe_addstr(screen, 0, 0, "Please enlarge the terminal (minimum 48x12).", heading)
            _safe_addstr(screen, max(1, height - 1), 0, "Press q to cancel.", normal)
            screen.refresh()
            key = screen.getch()
            if key in (ord("q"), ord("Q"), 27, 3):
                return None
            continue

        inner_width = width - 4
        _safe_addstr(screen, 0, 1, "+" + "-" * (width - 3), heading)
        _safe_addstr(screen, 1, 2, "SM64 iOS BUILDER by John Mama. - Compiles the game for iOS 6+", heading)
        _safe_addstr(screen, 2, 1, "+" + "-" * (width - 3), heading)
        _safe_addstr(screen, 3, 2, title[:inner_width], heading)

        row = 4
        if status_lines:
            row += 1
            _safe_addstr(screen, row, 2, "SYSTEM STATUS", status_style)
            row += 1
            for status in status_lines:
                _safe_addstr(screen, row, 2, status, normal)
                row += 1
            row += 1
            _safe_addstr(screen, row, 1, "+" + "-" * (width - 3), heading)
            row += 1

        list_start = row
        footer_row = height - 2
        visible_count = max(1, footer_row - list_start - 1)
        first_visible = max(0, min(selected - visible_count + 1, len(options) - visible_count))
        for index in range(first_visible, min(len(options), first_visible + visible_count)):
            label = "%2d. %s" % (index + 1, options[index])
            style = selected_style if index == selected else normal
            _safe_addstr(
                screen,
                list_start + index - first_visible,
                2,
                label[:inner_width],
                style,
            )

        _safe_addstr(screen, footer_row, 1, "+" + "-" * (width - 3), heading)
        _safe_addstr(
            screen,
            footer_row + 1,
            2,
            "UP/DOWN Move   ENTER Select   1-9 Jump   Q Cancel",
            normal,
        )
        screen.refresh()
        key = screen.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            return selected
        if key in (ord("q"), ord("Q"), 27, 3):
            return None
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(options)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(options)
        elif key == curses.KEY_PPAGE:
            selected = max(0, selected - visible_count)
        elif key == curses.KEY_NPAGE:
            selected = min(len(options) - 1, selected + visible_count)
        elif key == curses.KEY_HOME:
            selected = 0
        elif key == curses.KEY_END:
            selected = len(options) - 1
        elif ord("1") <= key <= ord("9"):
            option_index = key - ord("1")
            if option_index < len(options):
                return option_index
        elif key == curses.KEY_RESIZE:
            continue


def _select_option(title: str, options, default_index: int = 0) -> Optional[int]:
    if not options:
        return None
    selected = min(max(default_index, 0), len(options) - 1)
    if not sys.stdin.isatty():
        print("\n%s" % title)
        for index, option in enumerate(options, 1):
            print("%3d. %s" % (index, option))
        while True:
            try:
                answer = input(
                    "Choose a number [%d], or q to cancel: " % (selected + 1)
                ).strip().lower()
            except EOFError:
                return None
            if answer == "q":
                return None
            if not answer:
                return selected
            try:
                choice = int(answer) - 1
            except ValueError:
                print("Enter a listed number or q to cancel.")
                continue
            if 0 <= choice < len(options):
                return choice
            print("Choose a listed number or q to cancel.")

    try:
        return curses.wrapper(_curses_menu, title, options, selected)
    except curses.error:
        print("Interactive terminal menu unavailable; using numbered choices.")
        return _select_option_fallback(title, options, selected)


def _select_option_fallback(title: str, options, selected: int) -> Optional[int]:
    print("\n%s" % title)
    for index, option in enumerate(options, 1):
        print("%3d. %s" % (index, option))
    while True:
        try:
            answer = input("Choose a number [%d], or q to cancel: " % (selected + 1)).strip().lower()
        except EOFError:
            return None
        if answer == "q":
            return None
        if not answer:
            return selected
        try:
            choice = int(answer) - 1
        except ValueError:
            print("Enter a listed number or q to cancel.")
            continue
        if 0 <= choice < len(options):
            return choice
        print("Choose a listed number or q to cancel.")


def _choose_source(state: Dict) -> None:
    repository = validate_repository(
        input(
            "[OPTIONAL] GitHub source repository [%s]: "
            % state.get("repository", DEFAULT_REPOSITORY)
        )
        or state.get("repository", DEFAULT_REPOSITORY)
    )
    source_modes = (
        "Published releases (recommended; latest release first)",
        "Branches (moving targets; commit is pinned when building)",
    )
    mode_index = _select_option("Choose a source type", source_modes)
    if mode_index is None:
        return

    state["repository"] = repository
    if mode_index == 0:
        print(
            "Loading published source versions from https://github.com/%s ..."
            % repository
        )
        releases = list_source_releases(repository)
        if not releases:
            raise GitHubError(
                "No published releases were found for %s. "
                "The source repository must publish versioned GitHub releases."
                % repository
            )
        release_options = [
            "%s  %s  %s"
            % (release.tag, release.published_at[:10], release.title)
            for release in releases
        ]
        release_index = _select_option(
            "Choose a published iOS version", release_options
        )
        if release_index is None:
            return
        selected = releases[release_index]
        state["source_kind"] = "release"
        state["source_ref"] = selected.tag
        state["source_version"] = selected.tag
        print("\n%s" % selected.title)
        print("Version tag: %s" % selected.tag)
        if selected.body:
            print(selected.body[:4000])
        if selected.url:
            print("\nRelease notes: %s" % selected.url)
        selection_label = "release %s" % selected.tag
    else:
        print("Loading branches from https://github.com/%s ..." % repository)
        branches = list_source_branches(repository)
        if not branches:
            raise GitHubError("No branches were found for %s." % repository)
        branch_options = [
            "%s [%s]  (%s)"
            % (
                branch.name,
                "STABLE" if branch.name == "master" else "DEVELOPMENT",
                branch.commit[:8],
            )
            for branch in branches
        ]
        branch_index = _select_option("Choose a source branch", branch_options)
        if branch_index is None:
            return
        selected = branches[branch_index]
        state["source_kind"] = "branch"
        state["source_ref"] = selected.name
        state.pop("source_version", None)
        state.pop("source_commit", None)
        selection_label = "branch %s at %s" % (
            selected.name,
            selected.commit[:8],
        )
        print(
            "\nSelected branch %s at commit %s."
            % (selected.name, selected.commit)
        )
    _save_state(state)
    print("\nSelected source %s." % selection_label)


def _choose_rom(state: Dict) -> Optional[RomValidation]:
    previous_path = state.get("rom_path", "")
    path = input("Path to your authentic .z64 ROM. [%s]: " % previous_path).strip()
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
    source_kind = state.get("source_kind", "release")
    source_ref = state.get("source_ref") or state.get("source_version")
    if source_kind not in ("release", "branch") or not source_ref:
        raise ValueError("Select a published release or source branch first.")
    rom = _saved_rom(state)
    if rom is None or not rom.supported:
        raise ValueError("Select and validate a supported US .z64 ROM first.")

    print(
        "\nROM/license notice: you must own a legally obtained US Super Mario 64 ROM."
    )
    if input("Confirm that you own this ROM? [y/N]: ").strip().lower() != "y":
        print("Build cancelled.")
        return
    print(
        "\n SM64-iOS forbids binary redistribution due to upstream licensing. You are forbidden to upload or redistribute "
        "the generated .deb."
    )
    if input("Enter y to agree with this policy.").strip().lower() != "y":
        print("Sorry :(, Build cancelled!")
        return

    default_jobs = max(1, os.cpu_count() or 1)
    answer = input("[OPTIONAL] Parallel build jobs [%d]: " % default_jobs).strip()
    try:
        jobs = int(answer) if answer else default_jobs
    except ValueError as error:
        raise ValueError("Build jobs must be a positive integer.") from error
    if jobs < 1:
        raise ValueError("Build jobs must be a positive integer.")

    result = build_deb(
        repository=state["repository"],
        source_ref=source_ref,
        source_kind=source_kind,
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
        selected_version = state.get("source_ref") or state.get("source_version")
        selected_kind = state.get("source_kind", "release")
        selected_action = 0
        if not sys.stdin.isatty():
            print(
                "\nSM64 iOS Builder — WSL console\n"
                "  Setup: %s | Source: %s | ROM: %s | Version: %s"
                % (
                    "ready" if _is_setup_verified() else "needs setup",
                    state.get("repository", "(not selected)"),
                    state.get("rom_path", "(not selected)"),
                    (
                        "%s: %s" % (selected_kind, selected_version)
                        if selected_version
                        else "(not selected)"
                    ),
                )
            )
            try:
                choice = input("Select 1–5 (or q to exit): ").strip().lower()
            except EOFError:
                return 0
            if choice in ("q", "quit", "exit"):
                return 0
            if not choice.isdigit() or not 1 <= int(choice) <= len(MAIN_ACTIONS):
                print("Choose a listed action.")
                continue
            selected_action = int(choice) - 1
        else:
            status_lines = (
                "Theos / iOS SDK: %s"
                % ("Already Installed" if _is_setup_verified() else "NEEDS SETUP"),
                "Source: %s" % state.get("repository", DEFAULT_REPOSITORY),
                "iOS source: %s"
                % (
                    "%s: %s" % (selected_kind, selected_version)
                    if selected_version
                    else "not selected"
                ),
                "ROM: %s" % (state.get("rom_path") or "not selected"),
            )
            selected_action = curses.wrapper(
                _curses_menu,
                "Select an action",
                MAIN_ACTIONS,
                selected_action,
                status_lines,
            )
            if selected_action is None:
                return 0
        try:
            if selected_action == 0:
                _setup(print)
            elif selected_action == 1:
                _choose_source(state)
            elif selected_action == 2:
                _choose_rom(state)
            elif selected_action == 3:
                _compile(state)
            elif selected_action == 4:
                return 0
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
