import argparse

from sm64_builder.cli import run_cli, validate_argument


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the SM64 iOS app from a pinned GitHub source commit."
    )
    parser.add_argument(
        "--validate-rom",
        metavar="FILE",
        help="validate a big-endian .z64 ROM without entering the menu",
    )
    arguments = parser.parse_args()
    if arguments.validate_rom:
        return validate_argument(arguments.validate_rom)
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
