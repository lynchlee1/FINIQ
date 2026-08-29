from pathlib import Path

import pytest

from finiq.market_desk.web.features.disclosures import table_export


def _source_inventory(
    source_path: Path,
    page_paths: list[Path],
) -> table_export._SourceInventory:
    page_number_by_path = {
        path: index for index, path in enumerate(page_paths, start=1)
    }
    source_folders = tuple(sorted({path.parent.resolve() for path in page_paths}))
    body_paths_by_folder = {
        folder: tuple(path for path in page_paths if path.parent.resolve() == folder)
        for folder in source_folders
    }
    return table_export._SourceInventory(
        source_path=source_path,
        source_folders=source_folders,
        body_paths=tuple(page_paths),
        body_paths_by_folder=body_paths_by_folder,
        page_number_by_path=page_number_by_path,
        page_count_by_folder={
            folder: len(paths) for folder, paths in body_paths_by_folder.items()
        },
    )


def _inspection_manifest() -> dict[str, object]:
    return {
        "format": table_export.MANIFEST_FORMAT,
        "schema_version": table_export.TABLE_SCHEMA_VERSION,
        "source_type": "source_folder",
        "table_name": "disclosures",
        "content_fingerprint": "a" * 64,
        "summary": {
            "companies": 1,
            "source_rows": 2,
            "duplicate_rows": 1,
            "disclosures": 1,
            "unlinked_disclosures": 1,
            "shards": 1,
        },
        "pages": [{"relative_path": "20260101_20261231/page.body", "source_rows": 2}],
        "shards": [
            {
                "year": "2026",
                "relative_path": "2026.sqlite",
                "disclosures": 1,
                "unlinked_disclosures": 1,
            }
        ],
    }


def test_table_inspection_counts_source_without_building_row_collections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_page = tmp_path / "001_post_page_00001.body"
    second_page = tmp_path / "002_post_page_00002.body"
    records_by_page = {
        first_page: [
            {
                "acpt_no": "20250001",
                "company_key": "001",
                "disclosed_at": "2025-12-31 09:00",
            },
            {
                "acpt_no": "20260001",
                "company_key": None,
                "disclosed_at": "2026-01-01 09:00",
            },
        ],
        second_page: [
            {
                "acpt_no": "20260001",
                "company_key": None,
                "disclosed_at": "2026-01-01 09:00",
            },
        ],
    }
    monkeypatch.setattr(
        table_export,
        "_read_source_page_records",
        lambda path, **_kwargs: (
            records_by_page[path],
            {
                "current_page": table_export.result_page_number(path),
                "total_pages": 2,
                "total_items": 3,
            },
        ),
    )

    result = table_export._inspect_source_folder_counts(
        _source_inventory(tmp_path, [first_page, second_page]),
        worker_count=2,
    )

    assert result[:6] == ({"2025": (1, 0), "2026": (1, 1)}, 1, 2, 3, 1, 1)
    assert result[6] == [
        {
            "source_file": first_page.name,
            "source_page": 1,
            "source_rows": 2,
            "written_rows": 2,
            "duplicate_rows": 0,
        },
        {
            "source_file": second_page.name,
            "source_page": 2,
            "source_rows": 1,
            "written_rows": 0,
            "duplicate_rows": 1,
        },
    ]


def test_table_inspection_rejects_missing_source_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "01-list"
    source_folder = source_path / "20260101_20261231"
    source_folder.mkdir(parents=True)
    (source_folder / "kind_workflow.input.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (source_folder / "001_post_page_00001.body").write_text("page 1")
    (source_folder / "003_post_page_00003.body").write_text("page 3")
    monkeypatch.setattr(
        table_export,
        "validate_kind_workflow_input_snapshot",
        lambda _metadata: None,
    )

    result = table_export.inspect_disclosure_table_payload(
        {
            "root_directory": str(source_path),
            "output_path": str(tmp_path / "02-table"),
            "table_workers": 2,
        }
    )

    assert result["confirmed"] is False
    assert "페이지 번호가 1부터 연속적이지 않습니다" in result["reason"]


def test_table_inspection_confirms_source_manifest_and_shards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "01-list"
    source_path.mkdir()
    page_path = source_path / "20260101_20261231" / "page.body"
    pages = [{"relative_path": "20260101_20261231/page.body", "source_rows": 2}]

    inventory = _source_inventory(source_path, [page_path])
    monkeypatch.setattr(
        table_export, "_build_source_inventory", lambda *_args, **_kwargs: inventory
    )
    monkeypatch.setattr(
        table_export, "_validate_source_inventory", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(table_export, "_load_sqlite_manifest", lambda _path: _inspection_manifest())
    monkeypatch.setattr(table_export, "_validate_sqlite_manifest_counts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        table_export,
        "_sqlite_manifest_content_fingerprints",
        lambda *_args, **_kwargs: ("a" * 64, None),
    )
    monkeypatch.setattr(
        table_export,
        "_inspect_source_folder_counts",
        lambda *_args, **_kwargs: ({"2026": (1, 1)}, 1, 1, 2, 1, 1, pages),
    )

    result = table_export.inspect_disclosure_table_payload(
        {
            "root_directory": str(source_path),
            "output_path": str(tmp_path / "02-table"),
            "table_workers": 1,
        }
    )

    assert result["confirmed"] is True
    assert result["summary"] == _inspection_manifest()["summary"]
    assert result["reason"] == "다운로드한 원본 데이터와 변환 기록, 연도별 SQLite 파일의 내용이 모두 일치합니다."


def test_table_inspection_rejects_stale_manifest_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "01-list"
    source_path.mkdir()
    stale_manifest = _inspection_manifest()
    stale_manifest["summary"] = {**stale_manifest["summary"], "disclosures": 2}  # type: ignore[arg-type]

    page_path = source_path / "page.body"
    inventory = _source_inventory(source_path, [page_path])
    monkeypatch.setattr(
        table_export, "_build_source_inventory", lambda *_args, **_kwargs: inventory
    )
    monkeypatch.setattr(
        table_export, "_validate_source_inventory", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(table_export, "_load_sqlite_manifest", lambda _path: stale_manifest)
    monkeypatch.setattr(table_export, "_validate_sqlite_manifest_counts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        table_export,
        "_sqlite_manifest_content_fingerprints",
        lambda *_args, **_kwargs: ("a" * 64, None),
    )
    monkeypatch.setattr(
        table_export,
        "_inspect_source_folder_counts",
        lambda *_args, **_kwargs: (
            {"2026": (1, 1)},
            1,
            1,
            2,
            1,
            1,
            [{"relative_path": "20260101_20261231/page.body", "source_rows": 2}],
        ),
    )

    result = table_export.inspect_disclosure_table_payload(
        {
            "root_directory": str(source_path),
            "output_path": str(tmp_path / "02-table"),
            "table_workers": 1,
        }
    )

    assert result["confirmed"] is False
    assert result["reason"] == "다운로드한 원본 데이터의 건수와 변환 기록의 요약이 다릅니다."


def test_table_inspection_uses_yearly_sqlite_file_term_for_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "01-list"
    source_path.mkdir()
    inventory = _source_inventory(source_path, [source_path / "page.body"])
    monkeypatch.setattr(
        table_export, "_build_source_inventory", lambda *_args, **_kwargs: inventory
    )
    monkeypatch.setattr(
        table_export,
        "_validate_source_inventory",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        table_export,
        "_load_sqlite_manifest",
        lambda _path: _inspection_manifest(),
    )

    result = table_export.inspect_disclosure_table_payload(
        {
            "root_directory": str(source_path),
            "output_path": str(tmp_path / "02-table"),
            "table_workers": 1,
        }
    )

    assert result["confirmed"] is False
    assert "연도별 SQLite 파일을 찾을 수 없습니다" in result["reason"]
    assert "SQLite shard" not in result["reason"]
