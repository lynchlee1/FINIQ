from __future__ import annotations

from pathlib import Path

import pytest

from finiq.market_desk.web.features.storage.partition import run_partition_storage_payload


def test_partition_storage_splits_flat_files_by_filename_year(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    (source / "20240101000001.html").write_text("a", encoding="utf-8")
    (source / "20250101000002.json").write_text("b", encoding="utf-8")
    (source / "manifest.json").write_text("ignored", encoding="utf-8")

    result = run_partition_storage_payload(
        {
            "mode": "split",
            "source_directory": str(source),
            "output_directory": str(output),
        }
    )

    assert (output / "2024" / "20240101000001.html").read_text(encoding="utf-8") == "a"
    assert (output / "2025" / "20250101000002.json").read_text(encoding="utf-8") == "b"
    assert output.is_dir()
    assert result["copied_files"] == 2
    assert result["skipped_invalid_year_files"] == 1
    assert result["years"] == ["2024", "2025"]


def test_partition_storage_flattens_year_directories(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    (source / "2024").mkdir(parents=True)
    (source / "2025").mkdir()
    (source / "misc").mkdir()
    (source / "2024" / "20240101000001.html").write_text("a", encoding="utf-8")
    (source / "2025" / "20250101000002.html").write_text("b", encoding="utf-8")
    (source / "misc" / "20260101000003.html").write_text("ignored", encoding="utf-8")

    result = run_partition_storage_payload(
        {
            "mode": "flatten",
            "source_directory": str(source),
            "output_directory": str(output),
        }
    )

    assert (output / "20240101000001.html").read_text(encoding="utf-8") == "a"
    assert (output / "20250101000002.html").read_text(encoding="utf-8") == "b"
    assert not (output / "20260101000003.html").exists()
    assert result["copied_files"] == 2
    assert result["years"] == ["2024", "2025"]


def test_partition_storage_skips_existing_files_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    (output / "2024").mkdir(parents=True)
    (source / "20240101000001.html").write_text("new", encoding="utf-8")
    (output / "2024" / "20240101000001.html").write_text("old", encoding="utf-8")

    result = run_partition_storage_payload(
        {
            "mode": "split",
            "source_directory": str(source),
            "output_directory": str(output),
        }
    )

    assert (output / "2024" / "20240101000001.html").read_text(encoding="utf-8") == "old"
    assert result["copied_files"] == 0
    assert result["skipped_existing_files"] == 1


def test_partition_storage_moves_flat_files_into_year_directories(tmp_path: Path) -> None:
    source = tmp_path / "viewer_html"
    source.mkdir()
    source_file = source / "20250101000001.html"
    source_file.write_text("html", encoding="utf-8")

    result = run_partition_storage_payload(
        {
            "mode": "split",
            "source_directory": str(source),
            "output_directory": str(source),
            "move": True,
        }
    )

    assert not source_file.exists()
    assert (source / "2025" / "20250101000001.html").read_text(encoding="utf-8") == "html"
    assert result["copied_files"] == 0
    assert result["moved_files"] == 1


def test_partition_storage_moves_year_directories_to_flat_folder(tmp_path: Path) -> None:
    source = tmp_path / "viewer_html"
    source_file = source / "2025" / "20250101000001.html"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("html", encoding="utf-8")

    result = run_partition_storage_payload(
        {
            "mode": "flatten",
            "source_directory": str(source),
            "output_directory": str(source),
            "move": True,
        }
    )

    assert not source_file.exists()
    assert not (source / "2025").exists()
    assert (source / "20250101000001.html").read_text(encoding="utf-8") == "html"
    assert result["copied_files"] == 0
    assert result["moved_files"] == 1


def test_partition_storage_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mode must be one of"):
        run_partition_storage_payload(
            {
                "mode": "unknown",
                "source_directory": str(tmp_path),
                "output_directory": str(tmp_path / "output"),
            }
        )


def test_partition_storage_rejects_split_when_input_is_already_split(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    (source / "2025").mkdir(parents=True)
    (source / "2025" / "20250101000001.html").write_text("html", encoding="utf-8")

    with pytest.raises(ValueError, match="이미 연도별 폴더 구조"):
        run_partition_storage_payload(
            {
                "mode": "split",
                "source_directory": str(source),
                "output_directory": str(output),
            }
        )

    assert not output.exists()
