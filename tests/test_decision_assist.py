from __future__ import annotations

from duanxian import decision_assist as da


def _review(strong: bool = True) -> dict:
    return {
        "emotion_metrics": {
            "money_effect": {"median": 3.0 if strong else -4.0,
                             "positive_rate": 0.70 if strong else 0.25},
            "promotion": {"overall": {"rate": 0.42 if strong else 0.08}},
            "cycle": {"trend": "连续两日走强" if strong else "今日转弱"},
        },
        "market_facts": {
            "seal_quality": {"broken_rate": 0.12 if strong else 0.48},
            "breadth": {"up": 3500 if strong else 900, "down": 1000 if strong else 3800},
            "theme_structure": {"themes": [
                {"sector": "机器人", "limit_up": 6, "consec_boards": 2,
                 "highest": 4, "broken_rate": 0.10},
                {"sector": "孤立行业", "limit_up": 1, "consec_boards": 0,
                 "highest": 1, "broken_rate": 0.50},
            ]},
            "theme_tree": {"themes": [
                {"tag": "人形机器人", "limit_up": 4, "highest": 3,
                 "continuation_rate": 0.5,
                 "members": [{"code": "000001"}, {"code": "000002"}]},
            ]},
        },
    }


def _backtest(sample: int = 80) -> dict:
    stats = {"sample": sample, "win_rate": 0.64, "avg": 2.1,
             "median": 1.2, "limit_up_rate": 0.18}
    return {
        "days_used": 60, "date_from": "2026-05-01", "date_to": "2026-08-01",
        "strategies": {
            "首板·早封": {"overall": stats},
            "首板打板": {"overall": stats},
            "首板·尾盘封": {"overall": stats},
            "连板接力": {"overall": stats},
            "高标接力": {"overall": stats},
        },
    }


def test_market_environment_distinguishes_strong_and_weak():
    strong = da._market_environment(_review(True))
    weak = da._market_environment(_review(False))
    assert strong["score"] > weak["score"]
    assert strong["level"] == "进攻窗口"
    assert weak["level"] in ("防守窗口", "回避窗口")
    assert strong["signals"]


def test_build_sorts_candidates_and_applies_hard_veto(monkeypatch):
    rows = [
        {"code": "000001", "name": "强协同", "sector": "机器人", "boards": 2,
         "amount": 1_500_000_000, "turnover": 12, "first_seal": "093200",
         "last_seal": "093500", "broken_times": 0},
        {"code": "000002", "name": "尾盘回封", "sector": "机器人", "boards": 1,
         "amount": 800_000_000, "turnover": 18, "first_seal": "103000",
         "last_seal": "145000", "broken_times": 2},
        {"code": "000003", "name": "孤立首板", "sector": "孤立行业", "boards": 1,
         "amount": 300_000_000, "turnover": 8, "first_seal": "101000",
         "last_seal": "101000", "broken_times": 0},
    ]
    monkeypatch.setattr(da.market_facts, "pools", lambda _d: {"zt": rows})
    monkeypatch.setattr(da, "_load_backtest", lambda: _backtest())

    result = da.build("2026-08-01", _review(True))
    assert result["available"] is True
    assert result["candidates"][0]["code"] == "000001"
    assert result["candidates"][0]["history"]["win_rate"] == 0.64
    rejected = {x["code"]: x for x in result["rejected"]}
    assert "14:30 后才最终封板" in rejected["000002"]["vetoes"]
    assert "板块孤立，缺少协同" in rejected["000003"]["vetoes"]
    assert result["counts"] == {"source": 3, "active": 1, "rejected": 2}


def test_history_probability_hidden_until_sample_is_large_enough():
    row = {"boards": 1, "last_seal": "095000"}
    small = da._history_prior(row, _backtest(sample=29))
    enough = da._history_prior(row, _backtest(sample=30))
    assert small["win_rate"] is None
    assert small["enough_samples"] is False
    assert enough["win_rate"] == 0.64
    assert enough["enough_samples"] is True


def test_integer_market_time_is_zero_padded_before_comparison():
    row = {"first_seal": 93200, "last_seal": 93500, "broken_times": 0}
    score, reasons = da._quality_score(row)
    assert score == 20
    assert "早盘快速封板" in reasons
    assert da._vetoes(row, sector_size=3, has_theme_cluster=True) == []


def test_unavailable_when_source_pool_is_missing(monkeypatch):
    monkeypatch.setattr(da.market_facts, "pools", lambda _d: None)
    result = da.build("2026-08-01", _review())
    assert result["available"] is False
    assert "涨停池" in result["reason"]
