import subprocess
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional


OutputCallback = Optional[Callable[[str], None]]


class CommandError(RuntimeError):
    def __init__(self, command: Iterable[str], returncode: int):
        self.command = list(command)
        self.returncode = returncode
        super().__init__(
            "Command failed with exit code %d: %s"
            % (returncode, " ".join(self.command))
        )


def run(
    command: Iterable[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    output: OutputCallback = None,
) -> None:
    command = [str(part) for part in command]
    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        if output is not None:
            output(line.rstrip("\n"))
    returncode = process.wait()
    if returncode:
        raise CommandError(command, returncode)


def capture(
    command: Iterable[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    command = [str(part) for part in command]
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise CommandError(command, result.returncode)
    return result.stdout.strip()
