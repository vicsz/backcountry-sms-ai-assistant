from pathlib import Path

from scripts.next_bug_id import next_bug_number


def test_empty_directory_starts_at_one(tmp_path: Path) -> None:
    assert next_bug_number(tmp_path) == 1


def test_uses_highest_number_and_ignores_template_or_invalid_names(tmp_path: Path) -> None:
    (tmp_path / "BUG-0002-example.md").touch()
    (tmp_path / "BUG-0010-later.md").touch()
    (tmp_path / "BUG-0003.md").touch()
    (tmp_path / "TEMPLATE.md").touch()
    (tmp_path / "notes.md").touch()

    assert next_bug_number(tmp_path) == 11
