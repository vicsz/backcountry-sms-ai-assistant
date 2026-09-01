#!/usr/bin/env python3
"""Print the next four-digit bug ID without modifying the repository."""

import argparse
import re
from pathlib import Path

BUG_FILE_PATTERN = re.compile(r"^BUG-(\d{4})-.+\.md$")


def next_bug_number(bugs_directory: Path) -> int:
    """Return one greater than the highest numbered bug file, or 1 when none exist."""
    numbers = (
        int(match.group(1))
        for path in bugs_directory.glob("BUG-*.md")
        if (match := BUG_FILE_PATTERN.match(path.name))
    )
    return max(numbers, default=0) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bugs_directory", nargs="?", type=Path, default=Path("bugs"))
    args = parser.parse_args()
    print(f"BUG-{next_bug_number(args.bugs_directory):04d}")


if __name__ == "__main__":
    main()
