"""每日盯盘首板/二板模块的纯逻辑测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


VR_DIR = str(Path(__file__).resolve().parents[1] / "vr")
if VR_DIR not in sys.path:
    sys.path.insert(0, VR_DIR)

import watchtower as wt  # noqa: E402


@pytest.mark.unit
@pytest.mark.parametrize(("item", "expected"), [
    ({"high_days": "首板", "high_days_value": 65537}, 1),
    ({"high_days": "2天2板", "high_days_value": 131074}, 2),
    ({"high_days": "2连板"}, 2),
    ({"high_days": "3天2板", "high_days_value": 131075}, 0),
    ({"high_days": "4天3板", "high_days_value": 196612}, 0),
])
def test_ths_board_count(item, expected):
    assert wt._ths_boards(item) == expected


@pytest.mark.unit
def test_broken_boards_are_classified_from_previous_limit_pool():
    broken = [
        {"c": "000001", "n": "今日第一次触板", "lbc": 0},
        {"c": "000002", "n": "昨日首板今日炸板", "lbc": 0},
        {"c": "000003", "n": "昨日二板今日炸板", "lbc": 0},
    ]
    rows = wt._classify_broken_boards(broken, {"000002": 1, "000003": 2})
    assert {r["c"]: r["lbc"] for r in rows} == {
        "000001": 1,
        "000002": 2,
        "000003": 3,
    }


@pytest.mark.unit
def test_board_pools_merge_sealed_and_broken(monkeypatch):
    """同票若已回封，以涨停池状态为准；同时保留炸板未回封股票。"""
    wt._board_pools_cache = (0.0, "", [])

    def fake_pool(endpoint, _date, _sort):
        if endpoint == "getTopicZTPool":
            return [
                {"c": "000001", "n": "首板回封", "lbc": 1},
                {"c": "000002", "n": "二板封住", "lbc": 2},
            ]
        return [
            {"c": "000001", "n": "首板回封", "lbc": 1},
            {"c": "000003", "n": "首板炸板", "lbc": 1},
        ]

    monkeypatch.setattr(wt.astock, "em_zt_topic_pool", fake_pool)
    stocks = wt._board_pools()
    by_code = {s["code"]: s for s in stocks}

    assert len(stocks) == 3
    assert by_code["000001"]["is_limit"] is True
    assert by_code["000003"]["is_limit"] is False


@pytest.mark.unit
def test_snapshot_groups_first_and_second_boards_with_live_status():
    """板位来自触板池，封/开状态优先按 3 秒实时行情判断。"""
    board_pools = [
        {"code": "000001", "name": "首板封住", "boards": 1, "is_limit": True},
        {"code": "000002", "name": "首板开板", "boards": 1, "is_limit": True},
        {"code": "000003", "name": "二板封住", "boards": 2, "is_limit": True},
        {"code": "000004", "name": "三板封住", "boards": 3, "is_limit": True},
    ]
    quotes = {
        "000001": {"name": "首板封住", "price": 11.0, "pct": 10.0, "amount": 1, "zt_price": 11.0},
        "000002": {"name": "首板开板", "price": 10.8, "pct": 8.0, "amount": 2, "zt_price": 11.0},
        "000003": {"name": "二板封住", "price": 12.1, "pct": 10.0, "amount": 3, "zt_price": 12.1},
        "000004": {"name": "三板封住", "price": 13.31, "pct": 10.0, "amount": 4, "zt_price": 13.31},
    }

    lianban = [{"code": "000004", "name": "三板封住", "boards": 3}]
    snap = wt._build_snapshot(quotes, [], [], [], board_pools, lianban, "昨日成交前十", [], "open")

    assert snap["first_board"]["total"] == 2
    assert snap["first_board"]["sealed"] == 1
    assert snap["first_board"]["broken"] == 1
    assert snap["second_board"]["total"] == 1
    assert snap["second_board"]["sealed"] == 1
    assert [r["code"] for r in snap["lianban3"]] == ["000004"]
