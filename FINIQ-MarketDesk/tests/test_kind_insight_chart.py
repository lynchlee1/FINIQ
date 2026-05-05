from __future__ import annotations

from datetime import date

from analytics.chart import (
    apply_insight_range,
    prepare_disclosure_dataframe,
    prepare_disclosure_points,
    prepare_price_dataframe,
)


def _company_payload() -> dict[str, object]:
    return {
        "disclosures": [
            {
                "disclosed_at": "2026-04-10 09:10",
                "title": "공시 A",
                "submitter": "제출인 A",
                "acpt_no": "1",
                "doc_no": None,
            }
        ]
    }


def _price_rows() -> list[dict[str, object]]:
    return [
        {
            "date": "2026-04-10",
            "open": 100,
            "high": 120,
            "low": 90,
            "close": 110,
            "volume": 1000,
        },
        {
            "date": "2026-04-13",
            "open": 115,
            "high": 130,
            "low": 110,
            "close": 112,
            "volume": 1200,
        },
    ]


def test_prepare_price_dataframe_uses_trading_days_only_and_us_colors() -> None:
    frame = prepare_price_dataframe(_price_rows())

    assert frame["trade_day"].tolist() == ["2026-04-10", "2026-04-13"]
    assert frame["candle_color"].tolist() == ["#16a34a", "#dc2626"]
    assert frame["body_bottom"].tolist() == [100, 112]
    assert frame["body_top"].tolist() == [110, 115]


def test_apply_insight_range_expands_from_disclosure_history_for_all() -> None:
    disclosure_frame = prepare_disclosure_dataframe(_company_payload())

    start_date, end_date = apply_insight_range(
        "전체",
        base_start=date(2026, 4, 12),
        base_end=date(2026, 4, 13),
        disclosure_frame=disclosure_frame,
        ui_date_min=date(1990, 1, 1),
    )

    assert start_date == date(2026, 4, 10)
    assert end_date == date(2026, 4, 13)


def test_prepare_disclosure_points_supports_all_marker_placements() -> None:
    disclosure_frame = prepare_disclosure_dataframe(_company_payload())
    price_frame = prepare_price_dataframe(_price_rows())

    axis_below = prepare_disclosure_points(
        disclosure_frame,
        price_frame,
        placement="x_axis_below",
    )
    axis_above = prepare_disclosure_points(
        disclosure_frame,
        price_frame,
        placement="x_axis_above",
    )
    center = prepare_disclosure_points(
        disclosure_frame,
        price_frame,
        placement="candle_center",
    )
    candle_above = prepare_disclosure_points(
        disclosure_frame,
        price_frame,
        placement="candle_above",
    )
    candle_below = prepare_disclosure_points(
        disclosure_frame,
        price_frame,
        placement="candle_below",
    )

    assert axis_below.iloc[0]["trade_day"] == "2026-04-10"
    assert axis_below.iloc[0]["marker_price"] < 90
    assert axis_above.iloc[0]["marker_price"] > 90
    assert center.iloc[0]["marker_price"] == 105
    assert candle_above.iloc[0]["marker_price"] > 120
    assert candle_below.iloc[0]["marker_price"] < 90


def test_prepare_disclosure_points_moves_after_close_disclosures_to_next_trading_day() -> None:
    disclosure_frame = prepare_disclosure_dataframe(
        {
            "disclosures": [
                {
                    "disclosed_at": "2026-04-10 20:01",
                    "title": "장후 공시",
                    "submitter": "제출인 A",
                    "acpt_no": "after-close",
                    "doc_no": None,
                }
            ]
        }
    )
    price_frame = prepare_price_dataframe(_price_rows())

    result = prepare_disclosure_points(
        disclosure_frame,
        price_frame,
        placement="candle_below",
    )

    assert result.iloc[0]["trade_day"] == "2026-04-13"
