from __future__ import annotations

from pathlib import Path

import pytest

from finiq.data.common import find_company_classification_files
from finiq.data_scraper.storage.classification_store import write_company_classification_artifact
from finiq.market_desk.data.facade import (
    load_company_classification,
    load_company_classification_company_file,
    load_company_classification_index_file,
)


def test_market_desk_finds_and_loads_sqlite_company_classification(tmp_path: Path) -> None:
    output_path = tmp_path / "kind.company_classification.sqlite"
    write_company_classification_artifact(
        output_path,
        {
            "summary": {
                "source_folders": 1,
                "body_files": 1,
                "companies": 1,
                "disclosures": 1,
            },
            "companies": [
                {
                    "company_name": "테스트회사",
                    "company_id": "T001",
                    "market": "코스닥",
                    "badges": [],
                    "disclosures": [
                        {
                            "disclosed_at": "2026-01-01 09:00",
                            "title": "주요사항보고서",
                            "acpt_no": "20260101000001",
                        }
                    ],
                }
            ],
        },
        compact=True,
    )
    assert find_company_classification_files(tmp_path) == [output_path]

    index_payload = load_company_classification_index_file(output_path)
    assert index_payload["summary"]["companies"] == 1
    assert index_payload["companies"] == [
        {
            "company_key": "T001",
            "company_name": "테스트회사",
            "company_id": "T001",
            "market": "코스닥",
            "badges": [],
            "disclosure_count": 1,
            "first_disclosed_at": "2026-01-01 09:00",
            "last_disclosed_at": "2026-01-01 09:00",
            "shard": None,
        }
    ]

    company_payload = load_company_classification_company_file(output_path, "T001")
    assert company_payload["company_name"] == "테스트회사"
    assert company_payload["disclosures"][0]["acpt_no"] == "20260101000001"


def test_market_desk_classification_loader_rejects_force_refresh(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="force_refresh is not supported"):
        load_company_classification(tmp_path, force_refresh=True)


def test_recursive_find_company_classification_files(tmp_path: Path) -> None:
    # 1. Root level classification sqlite
    root_sqlite = tmp_path / "kind.company_classification.sqlite"
    root_sqlite.touch()

    # 2. Deeply nested classification sqlite
    deep_dir = tmp_path / "subdir1" / "subdir2" / "subdir3"
    deep_dir.mkdir(parents=True)
    deep_sqlite = deep_dir / "kind.company_classification.sqlite"
    deep_sqlite.touch()

    # 3. Legacy JSON is not a classification artifact.
    all_companies = tmp_path / "subdir1" / "all_companies.json"
    all_companies.touch()

    # 4. Excluded directory: YYYYMMDD_YYYYMMDD
    date_dir = tmp_path / "20260101_20260501"
    date_dir.mkdir()
    date_sqlite = date_dir / "kind.company_classification.sqlite"
    date_sqlite.touch()

    # 5. A regular nested directory
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    viewer_sqlite = viewer_dir / "kind.company_classification.sqlite"
    viewer_sqlite.touch()

    # 6. Excluded directory: .git
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_sqlite = git_dir / "kind.company_classification.sqlite"
    git_sqlite.touch()

    # Run discovery
    found = find_company_classification_files(tmp_path)

    # Should find 1, 2, and 5.
    assert root_sqlite in found
    assert deep_sqlite in found
    assert all_companies not in found
    assert viewer_sqlite in found

    # Should NOT find 4 or 6
    assert date_sqlite not in found
    assert git_sqlite not in found
    assert len(found) == 3
