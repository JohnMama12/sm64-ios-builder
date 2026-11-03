import json
import os
import shutil
import sys
from contextlib import contextmanager
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

MAIN_ACTIONS = (
    "Set up Theos + iOS 6.1 SDK",
    "Choose GitHub source branch and commit",
    "Validate your US ROM",
    "Build local-only .deb",
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


def _terminal_colors_enabled() -> bool:
    return (
        sys.stdout.isatty()
        and os.environ.get("TERM", "") != "dumb"
        and "NO_COLOR" not in os.environ
    )


def _paint(text: str, *styles: str) -> str:
    if not styles or not _terminal_colors_enabled():
        return text
    return "\033[%sm%s\033[0m" % (";".join(styles), text)


def _clip(text: str, width: int) -> str:
    text = str(text)
    if len(text) <= width:
        return text
    if width < 4:
        return text[:width]
    return text[: width - 3] + "..."


def _draw_dashboard(state: Dict, selected: int) -> None:
    width = max(58, min(shutil.get_terminal_size((80, 24)).columns, 92))
    inner = width - 4
    setup_ready = _is_setup_verified()
    setup_label = "READY" if setup_ready else "NEEDS SETUP"
    setup_style = "32" if setup_ready else "33"
    repository = _clip(state.get("repository", DEFAULT_REPOSITORY), 28)
    branch = _clip(state.get("branch") or "not selected", 28)
    rom_path = _clip(state.get("rom_path") or "not selected", inner - 15)
    commit = state.get("commit")
    commit_label = commit[:8] if commit else "not selected"

    def row(label: str) -> str:
        return "  " + label.ljust(inner - 2) + "  "

    top = "╭" + "─" * (width - 2) + "╮"
    divider = "├" + "─" * (width - 2) + "┤"
    bottom = "╰" + "─" * (width - 2) + "╯"
    print("\033[2J\033[H", end="" if _terminal_colors_enabled() else "\n")
    print(_paint(top, "36", "1"))
    print("│" + _paint(row("SM64 iOS BUILDER"), "1", "36") + "│")
    print("│" + _paint(row("WSL build workspace · armv7 · iOS 6.0+"), "2") + "│")
    print(divider)
    print(
        "│"
        + _paint(row("TOOLCHAIN  " + setup_label), "1", setup_style)
        + "│"
    )
    print("│" + row("SOURCE     " + repository + "  /  " + branch) + "│")
    print("│" + row("COMMIT     " + commit_label) + "│")
    print("│" + row("ROM        " + rom_path) + "│")
    print(divider)
    print("│" + _paint(row("ACTIONS  ·  ↑/↓ move  Enter select  1–5 shortcut"), "2") + "│")
    for index, action in enumerate(MAIN_ACTIONS):
        label = "  [%d]  %s" % (index + 1, action)
        if index == selected:
            label = "  › " + _clip(label[2:], inner - 4)
            print("│" + _paint(row(label), "30", "46", "1") + "│")
        else:
            print("│" + row(label) + "│")
    print(_paint(bottom, "36", "1"))


def _draw_choices(title: str, options, selected: int, first_visible: int) -> None:
    width = max(58, min(shutil.get_terminal_size((80, 24)).columns, 92))
    inner = width - 4
    top = "╭" + "─" * (width - 2) + "╮"
    divider = "├" + "─" * (width - 2) + "┤"
    bottom = "╰" + "─" * (width - 2) + "╯"
    visible_count = max(4, min(12, shutil.get_terminal_size((80, 24)).lines - 9))
    print("\033[2J\033[H", end="" if _terminal_colors_enabled() else "\n")
    print(_paint(top, "36", "1"))
    print("│" + _paint(("  " + _clip(title, inner - 2)).ljust(inner + 2), "1", "36") + "│")
    print(divider)
    last_visible = min(len(options), first_visible + visible_count)
    for index in range(first_visible, last_visible):
        label = "  [%d]  %s" % (index + 1, options[index])
        label = _clip(label, inner)
        if index == selected:
            label = "  › " + _clip(label[2:], inner - 4)
            print("│" + _paint(("  " + label).ljust(inner + 2), "30", "46", "1") + "│")
        else:
            print("│" + ("  " + label).ljust(inner + 2) + "│")
    for _ in range(visible_count - (last_visible - first_visible)):
        print("│" + " " * (inner + 2) + "│")
    print(divider)
    print("│" + _paint(("  ↑/↓ move  Enter select  1–9 jump  q cancel").ljust(inner + 2), "2") + "│")
    print(_paint(bottom, "36", "1"))


@contextmanager
def _terminal_keys():
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        yield
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _read_key() -> str:
    import select

    descriptor = sys.stdin.fileno()
    key = os.read(descriptor, 1).decode("ascii", errors="ignore")
    if key == "\x1b":
        if select.select([descriptor], [], [], 0.05)[0]:
            key += os.read(descriptor, 1).decode("ascii", errors="ignore")
            if key == "\x1b[" and select.select([descriptor], [], [], 0.05)[0]:
                key += os.read(descriptor, 1).decode("ascii", errors="ignore")
    return key


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

    visible_count = max(4, min(12, shutil.get_terminal_size((80, 24)).lines - 9))
    first_visible = max(0, min(selected - visible_count + 1, len(options) - visible_count))
    first_visible = max(0, first_visible)
    with _terminal_keys():
        while True:
            _draw_choices(title, options, selected, first_visible)
            key = _read_key()
            if key in ("\r", "\n"):
                return selected
            if key in ("q", "Q", "\x03", "\x1b"):
                return None
            if key in ("\x1b[A", "k"):
                selected = (selected - 1) % len(options)
            elif key in ("\x1b[B", "j"):
                selected = (selected + 1) % len(options)
            elif key.isdigit() and key != "0":
                choice = int(key) - 1
                if choice < len(options):
                    return choice
            first_visible = max(
                0, min(selected - visible_count + 1, len(options) - visible_count)
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
    branch_options = [
        branch + ("  · saved" if branch == prior_branch else "")
        for branch in branches
    ]
    branch_index = _select_option(
        "Choose a source branch", branch_options, branches.index(default_branch)
    )
    if branch_index is None:
        return
    branch = branches[branch_index]

    print("Loading iOS commits for %s ..." % branch)
    commits = list_ios_commits(repository, branch)
    if not commits:
        raise GitHubError(
            "No commits touching src/ios were found on %s. Push the iOS source "
            "branch to GitHub first, or select its published repository/branch."
            % branch
        )
    commit_options = [
        "%s  %s  %s" % (commit.short_sha, commit.date[:10], commit.message)
        for commit in commits
    ]
    commit_index = _select_option("Choose an iOS source commit", commit_options)
    if commit_index is None:
        return
    selected = commits[commit_index]

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
        selected_commit = state.get("commit")
        selected_action = 0
        if not sys.stdin.isatty():
            print(
                "\nSM64 iOS Builder — WSL console\n"
                "  Setup: %s | Source: %s @ %s | ROM: %s | Commit: %s"
                % (
                    "ready" if _is_setup_verified() else "needs setup",
                    state.get("repository", "(not selected)"),
                    state.get("branch", "(not selected)"),
                    state.get("rom_path", "(not selected)"),
                    selected_commit[:8] if selected_commit else "(not selected)",
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
            with _terminal_keys():
                while True:
                    _draw_dashboard(state, selected_action)
                    key = _read_key()
                    if key in ("\r", "\n"):
                        break
                    if key in ("q", "Q", "\x03"):
                        return 0
                    if key in ("\x1b[A", "k"):
                        selected_action = (selected_action - 1) % len(MAIN_ACTIONS)
                    elif key in ("\x1b[B", "j"):
                        selected_action = (selected_action + 1) % len(MAIN_ACTIONS)
                    elif key.isdigit() and key != "0":
                        selected_action = int(key) - 1
                        if selected_action < len(MAIN_ACTIONS):
                            break
        try:
            if selected_action == 0:
                _setup(print)
            elif selected_action == 1:
                _choose_commit(state)
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
