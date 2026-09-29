from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / ".codex"
    / "skills"
    / "a-share-recommendation"
    / "scripts"
    / "rank_first_boards.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("rank_first_boards", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _row(code, industry, *, price=10.0, lbc=1, days=1, ct=1, fbt=93500,
         zbc=0, fund=100_000_000, ltsz=5_000_000_000, hs=8.0,
         amount=500_000_000):
    return {
        "c": code,
        "n": code,
        "p": int(price * 1000),
        "lbc": lbc,
        "zttj": {"days": days, "ct": ct},
        "hybk": industry,
        "fbt": fbt,
        "lbt": fbt,
        "zbc": zbc,
        "fund": fund,
        "ltsz": ltsz,
        "hs": hs,
        "amount": amount,
    }


def test_true_first_board_excludes_rebound_and_price_at_or_over_40():
    m = _load_module()
    assert m.is_true_first_board(_row("000001", "通信设备"))
    assert not m.is_true_first_board(_row("000002", "通信设备", days=8, ct=4))
    assert not m.is_true_first_board(_row("000003", "通信设备", price=40.00))
    assert not m.is_true_first_board(_row("000003", "通信设备", price=40.01))
    assert not m.is_true_first_board(_row("000004", "通信设备", lbc=2))


def test_only_shanghai_and_shenzhen_main_board_codes_are_eligible():
    m = _load_module()
    allowed = ["600001", "601001", "603001", "605001", "000001", "001001", "002001", "003001"]
    excluded = ["300001", "301001", "688001", "689001", "430001", "830001", "920001"]
    assert all(m.is_true_first_board(_row(code, "测试行业")) for code in allowed)
    assert all(not m.is_true_first_board(_row(code, "测试行业")) for code in excluded)


def test_select_three_spans_at_least_two_sectors():
    m = _load_module()
    pools = [
        _row("000001", "通信设备", fbt=93100),
        _row("000002", "通信设备", fbt=93200),
        _row("000003", "通信设备", fbt=93300),
        _row("000004", "元件", fbt=93400),
        _row("000005", "消费电子", fbt=93500),
    ]
    sectors = [
        {"name": "通信设备", "pct": 4.0, "net": 100.0},
        {"name": "元件", "pct": 3.0, "net": 50.0},
        {"name": "消费电子", "pct": 2.0, "net": 20.0},
    ]
    picked = m.rank_candidates(pools, sectors, limit=3)
    assert len(picked) == 3
    assert len({row["sector"] for row in picked}) >= 2
    assert max(sum(1 for row in picked if row["sector"] == sector)
               for sector in {row["sector"] for row in picked}) <= 2
    assert all(row["slot_type"] == "综合排名席" for row in picked)


def test_three_plus_two_uses_three_purchase_slots_and_two_separate_observers():
    m = _load_module()
    pools = [
        _row("000001", "强趋势A", fbt=100100, zbc=1),
        _row("000002", "强趋势B", fbt=100200, zbc=1),
        _row("000003", "情绪A", fbt=100300, zbc=1),
        _row("000004", "情绪B", fbt=100400, zbc=1),
        _row("000005", "自由席", fbt=100500, zbc=1),
    ]
    sectors = [
        {"name": "强趋势A", "pct": 4.0, "net": 100.0},
        {"name": "强趋势B", "pct": 3.0, "net": 80.0},
        {"name": "情绪A", "pct": 1.0, "net": 10.0},
        {"name": "情绪B", "pct": 0.5, "net": 5.0},
        {"name": "自由席", "pct": -1.0, "net": -20.0},
    ]
    for row in pools:
        row["sector_limit_count"] = 5
        row["sector_max_board"] = 4
        row["sector_first_board_count"] = 2
    high_boards = [
        _row("600001", "情绪A", lbc=5, amount=800_000_000),
        _row("600002", "强趋势A", lbc=3, amount=500_000_000),
    ]
    ranked = m.rank_candidates(pools, sectors, limit=5)
    purchases, watchlist = m.build_three_plus_two(ranked, {"open": True}, high_boards)
    assert len(purchases) == 3
    assert len(watchlist) == 2
    assert [row["slot_type"] for row in purchases] == [
        "1进2优先级1", "1进2优先级2", "1进2优先级3"
    ]
    assert all(row["ranking_formula"] == "涨停潜力70% + 可买性30%" for row in purchases)
    assert [row["role"] for row in watchlist] == ["市场高度锚", "候选板块高度锚"]
    assert all(row["status"] == "高标观察" for row in watchlist)
    assert not ({row["code"] for row in purchases} & {row["code"] for row in watchlist})


def test_three_plus_two_keeps_ranked_samples_but_marks_weak_quality():
    m = _load_module()
    weak = [_row(f"0000{index:02d}", f"板块{index}", fbt=145500, zbc=5)
            for index in range(1, 6)]
    sectors = [{"name": f"板块{index}", "pct": -1.0, "net": -10.0}
               for index in range(1, 6)]
    ranked = m.rank_candidates(weak, sectors, limit=5)
    purchases, watchlist = m.build_three_plus_two(ranked, {"open": True})
    assert len(purchases) == 3
    assert all(row["individual_status"] in {"仅观察", "禁止买入"} for row in purchases)
    assert len(watchlist) <= 2


def test_quality_status_can_forbid_instead_of_forcing_buy():
    m = _load_module()
    weak = _row(
        "000001", "弱板块", fbt=145500, zbc=5, fund=2_000_000,
        ltsz=10_000_000_000, amount=20_000_000,
    )
    picked = m.rank_candidates([weak], [{"name": "弱板块", "pct": -1, "net": -5}], limit=3)
    assert picked[0]["status"] in {"仅观察", "禁止买入"}


def test_concept_suffix_maps_to_sector_fund_flow_name():
    m = _load_module()
    assert m.match_sector(
        ["半导体概念", "第三代半导体", "储能概念"],
        {"半导体", "电力", "元件"},
    ) == ["半导体"]


def test_early_hard_board_has_lower_buyability_than_exchange_board():
    m = _load_module()
    hard = _row("000001", "半导体", fbt=93400, zbc=0, hs=8.0)
    exchange = _row("000002", "半导体", fbt=95100, zbc=1, hs=10.0)
    assert m.board_profile(hard) == "过强硬板"
    assert m.board_profile(exchange) == "换手首板"
    assert m._tradability(hard) < m._tradability(exchange)


def test_next_day_path_marks_early_zero_break_board_as_fast_board_risk():
    m = _load_module()
    row = _row("000001", "汽车零部件", fbt=93700, zbc=0, hs=6.0)
    profile = m.next_day_path_profile(row)
    assert profile["type"] == "秒板难买风险"
    assert profile["availability_grade"] == "C"


def test_next_day_path_marks_early_low_turnover_board_as_divergence_risk():
    m = _load_module()
    row = _row("000001", "汽车零部件", fbt=94000, zbc=1, hs=3.5)
    profile = m.next_day_path_profile(row)
    assert profile["type"] == "早盘冲板分歧风险"
    assert profile["availability_grade"] == "B-"


def test_next_day_path_marks_exchange_board_as_more_available():
    m = _load_module()
    row = _row("000001", "通用设备", fbt=101500, zbc=1, hs=10.0,
               amount=300_000_000)
    profile = m.next_day_path_profile(row)
    assert profile["type"] == "换手接力倾向"
    assert profile["availability_grade"] == "A"


def test_selection_does_not_force_exchange_board_over_higher_ranked_quality():
    m = _load_module()
    pools = [
        _row("000001", "通信设备", fbt=93100, fund=200_000_000),
        _row("000002", "通信设备", fbt=93200, fund=180_000_000),
        _row("000003", "元件", fbt=93300, fund=160_000_000),
        _row("000004", "消费电子", fbt=100100, zbc=1, hs=10.0),
    ]
    sectors = [
        {"name": "通信设备", "pct": 4.0, "net": 100.0},
        {"name": "元件", "pct": 3.0, "net": 50.0},
        {"name": "消费电子", "pct": 2.0, "net": 20.0},
    ]
    picked = m.rank_candidates(pools, sectors, limit=3)
    assert "000004" not in {row["code"] for row in picked}


def test_primary_industry_is_kept_separate_from_theme_sector():
    m = _load_module()
    row = _row("002617", "电力", fbt=95100)
    row["selected_sector"] = "半导体"
    picked = m.rank_candidates(
        [row],
        [{"name": "半导体", "pct": 4.0, "net": 100.0}],
        limit=1,
    )
    assert picked[0]["primary_industry"] == "电力"
    assert picked[0]["theme_sector"] == "半导体"


def test_score_uses_only_limit_probability_and_buyability():
    m = _load_module()
    picked = m.rank_candidates(
        [_row("000001", "半导体", fbt=100100, zbc=1, hs=10.0)],
        [{"name": "半导体", "pct": 4.0, "net": 100.0}],
        limit=1,
    )
    assert set(picked[0]["score_parts"]) == {"limit_up", "buyability"}
    assert round(sum(picked[0]["score_parts"].values()), 2) == picked[0]["score"]
    assert picked[0]["score_parts"]["limit_up"] <= 70
    assert picked[0]["score_parts"]["buyability"] <= 30


def test_high_limit_potential_cannot_hide_low_buyability():
    m = _load_module()
    hard = _row("000001", "半导体", fbt=93000, zbc=0, fund=300_000_000)
    hard["sector_limit_count"] = 5
    hard["sector_max_board"] = 4
    picked = m.rank_candidates(
        [hard],
        [{"name": "半导体", "pct": 3.9, "net": 99.0}],
        limit=1,
    )
    assert picked[0]["score_parts"]["limit_up"] >= m.MIN_LIMIT_UP
    assert picked[0]["score_parts"]["buyability"] < m.MIN_BUYABILITY
    assert picked[0]["status"].startswith("仅观察")


def test_sector_ladder_increases_continuation_potential_inside_limit_score():
    m = _load_module()
    leader = _row("000001", "半导体", fbt=100100, zbc=1, hs=10.0)
    isolated = _row("000002", "服装家纺", fbt=100100, zbc=1, hs=10.0)
    leader["sector_limit_count"] = 6
    leader["sector_max_board"] = 4
    isolated["sector_limit_count"] = 1
    isolated["sector_max_board"] = 1
    assert m._limit_up_score(leader, 20.0) > m._limit_up_score(isolated, 20.0)
    sectors = [{"name": "半导体", "pct": 2.0, "net": 10.0},
               {"name": "服装家纺", "pct": 2.0, "net": 10.0}]
    picked = m.rank_candidates([leader, isolated], sectors, limit=2)
    by_code = {row["code"]: row for row in picked}
    assert by_code["000001"]["continuation_context"] == {
        "sector_limit_count": 6,
        "sector_max_board": 4,
        "sector_first_board_count": 1,
    }


def test_single_stock_failure_cannot_veto_active_sector_ladder():
    m = _load_module()
    active = _row("000001", "医疗服务")
    active["sector_limit_count"] = 4
    active["sector_max_board"] = 3
    active["sector_first_board_count"] = 2
    active["failed_candidate_count"] = 1
    health = m._sector_health(active)
    assert health["state"] == "梯队活跃"
    assert health["single_stock_failure_can_veto"] is False
    assert health["active_signals"] == ["仍有高度板", "仍有新首板", "涨停宽度至少3只"]


def test_isolated_first_board_is_not_mislabeled_as_sector_weakness():
    m = _load_module()
    isolated = _row("000001", "医疗服务")
    isolated["sector_limit_count"] = 1
    isolated["sector_max_board"] = 1
    isolated["sector_first_board_count"] = 1
    health = m._sector_health(isolated)
    assert health["state"] == "孤立首板待确认"
    assert health["single_stock_failure_can_veto"] is False


def test_ladder_strength_can_outrank_easier_but_isolated_board():
    m = _load_module()
    ladder = _row("000001", "梯队板块", fbt=100100, zbc=1, hs=10.0, amount=120_000_000)
    easy = _row("000002", "孤立板块", fbt=100100, zbc=1, hs=10.0, amount=500_000_000)
    ladder["sector_limit_count"] = 5
    ladder["sector_max_board"] = 4
    easy["sector_limit_count"] = 1
    easy["sector_max_board"] = 1
    picked = m.rank_candidates(
        [ladder, easy],
        [
            {"name": "梯队板块", "pct": 2.0, "net": 20.0},
            {"name": "孤立板块", "pct": 2.0, "net": 20.0},
        ],
        limit=2,
    )
    assert picked[0]["code"] == "000001"
    assert picked[0]["score_parts"]["limit_up"] > picked[1]["score_parts"]["limit_up"]


def test_single_day_crowding_is_visible_and_penalized():
    m = _load_module()
    row = _row("000001", "热门板块", fbt=100100, zbc=1)
    normal = m.rank_candidates(
        [row], [{"name": "热门板块", "pct": 3.9, "net": 99.0}], limit=1
    )[0]
    crowded = m.rank_candidates(
        [row], [{"name": "热门板块", "pct": 4.0, "net": 100.0}], limit=1
    )[0]
    assert crowded["crowding_risk"] is True
    assert crowded["trend_confirmation"] == "单日趋势未验证"
    assert crowded["score_evidence"]["crowding_penalty_50"] == m.CROWDING_PENALTY
    assert crowded["score_parts"]["limit_up"] < normal["score_parts"]["limit_up"]


def test_high_board_anchors_prefer_market_height_and_candidate_sector_height():
    m = _load_module()
    pool = [
        _row("600001", "无关板块", lbc=6, amount=900_000_000),
        _row("600002", "候选板块", lbc=4, amount=500_000_000),
        _row("600003", "其他板块", lbc=5, amount=800_000_000),
        _row("600004", "候选板块", lbc=1, amount=700_000_000),
    ]
    anchors = m.select_high_board_anchors(
        pool, preferred_sectors={"候选板块"}, limit=2,
    )
    assert [row["code"] for row in anchors] == ["600001", "600002"]
    assert anchors[0]["role"] == "市场高度锚"
    assert anchors[1]["role"] == "候选板块高度锚"
    assert all("禁止" in row["action"] for row in anchors)


def test_market_gate_closes_when_two_or_more_risk_signals_exist():
    m = _load_module()
    gate = m.evaluate_market_gate(
        {"sentiment": {"up": 2283, "down": 2783}},
        {"promotion_rate": 0.235, "break_rate": 0.222,
         "zt_count": 63, "yzt_count": 102},
    )
    assert gate["open"] is False
    assert gate["mode"] == "防守模式"
    assert len(gate["adverse_signals"]) == 3


def test_market_gate_opens_only_with_complete_healthy_data():
    m = _load_module()
    gate = m.evaluate_market_gate(
        {"sentiment": {"up": 3200, "down": 1800}},
        {"promotion_rate": 0.32, "break_rate": 0.18,
         "zt_count": 80, "yzt_count": 90},
    )
    assert gate["open"] is True
    assert gate["mode"] == "进攻模式"
    assert gate["missing_metrics"] == []


def test_closed_gate_keeps_three_ranked_samples_without_prescribing_entry():
    m = _load_module()
    rows = []
    for code, sector in [("000001", "电力"), ("000002", "医药"), ("000003", "公用事业")]:
        row = _row(code, sector, fbt=100100, zbc=1)
        row["sector_limit_count"] = 3
        row["sector_max_board"] = 2
        row["sector_first_board_count"] = 2
        rows.append(row)
    sectors = [
        {"name": "电力", "pct": 2.0, "net": 30.0},
        {"name": "医药", "pct": 1.5, "net": 20.0},
        {"name": "公用事业", "pct": 1.0, "net": 10.0},
    ]
    ranked = m.rank_candidates(rows, sectors, limit=3)
    predictions = m.select_prediction_samples(ranked, {"open": False}, limit=3)
    assert len(predictions) == 3
    assert all(row["market_mode"] == "防守模式" for row in predictions)
    assert [row["slot_type"] for row in predictions] == [
        "1进2优先级1", "1进2优先级2", "1进2优先级3",
    ]
    assert all(row["entry_conditions"] == [] for row in predictions)
    assert all("具体买点由用户自行判断" in row["action"] for row in predictions)
    assert all("next_day_path" in row for row in predictions)
    assert all(set(row["evaluation_rule"]) == {
        "limit_up_hit", "executable_limit_up_hit", "user_executable_limit_up_hit",
        "touch_board_failure"
    } for row in predictions)


def test_prediction_order_uses_weighted_total_before_tiebreakers():
    m = _load_module()
    rows = []
    for code, max_board, seal_time in [
        ("000001", 4, 93000),
        ("000002", 2, 100100),
        ("000003", 1, 101000),
    ]:
        row = _row(code, f"行业{code[-1]}", fbt=seal_time, zbc=0)
        row["sector_limit_count"] = max_board + 1
        row["sector_max_board"] = max_board
        row["sector_first_board_count"] = 1
        rows.append(row)
    sectors = [
        {"name": f"行业{code[-1]}", "pct": 1.0, "net": 10.0}
        for code in ("000001", "000002", "000003")
    ]
    ranked = m.rank_candidates(rows, sectors, limit=3)
    predictions = m.select_prediction_samples(ranked, {"open": True}, limit=3)
    totals = [row["score"] for row in predictions]
    assert totals == sorted(totals, reverse=True)


def test_closed_market_gate_keeps_ranked_candidates_and_high_board_observers():
    m = _load_module()
    row = _row("000001", "半导体", fbt=100100, zbc=1)
    row["sector_limit_count"] = 5
    row["sector_max_board"] = 4
    row["sector_first_board_count"] = 2
    ranked = m.rank_candidates(
        [row], [{"name": "半导体", "pct": 3.0, "net": 80.0}], limit=1
    )
    high_boards = [_row("600001", "半导体", lbc=4)]
    purchases, watchlist = m.build_three_plus_two(ranked, {"open": False}, high_boards)
    assert len(purchases) == 1
    assert purchases[0]["market_mode"] == "防守模式"
    assert watchlist[0]["status"] == "高标观察"
    assert watchlist[0]["boards"] == 4


def test_risk_notice_vetoes_stock_but_not_its_sector():
    m = _load_module()
    candidate = {"status": "次日满足条件后可考虑"}
    m.apply_information_risk(candidate, {
        "news": [],
        "announcements": [{"title": "股票交易风险提示公告"}],
    })
    assert candidate["information_risk"]["blocked"] is True
    assert candidate["status"] == "仅观察（风险信息否决）"


def test_snapshot_roundtrip_is_immutable(tmp_path):
    m = _load_module()
    m.SNAPSHOT_ROOT = tmp_path
    first = {"date": "20260929", "output": {"marker": "first"}, "inputs": {}}
    second = {"date": "20260929", "output": {"marker": "second"}, "inputs": {}}
    saved = m.save_snapshot(first)
    repeated = m.save_snapshot(second)
    assert saved["output"]["marker"] == "first"
    assert repeated["output"]["marker"] == "first"
    raw = json.loads((tmp_path / "20260929.json").read_text(encoding="utf-8"))
    assert raw["output"]["marker"] == "first"


def test_missing_historical_snapshot_is_rejected(tmp_path):
    m = _load_module()
    m.SNAPSHOT_ROOT = tmp_path
    try:
        m._historical_snapshot_or_raise("20260928", today=date(2026, 9, 29))
    except RuntimeError as exc:
        assert "拒绝使用当前板块资金重算" in str(exc)
    else:
        raise AssertionError("历史日期缺快照时必须拒绝回填")


def test_matching_historical_snapshot_can_be_loaded(tmp_path):
    m = _load_module()
    m.SNAPSHOT_ROOT = tmp_path
    m.save_snapshot({"date": "20260928", "output": {"date": "20260928"}, "inputs": {}})
    loaded = m._historical_snapshot_or_raise("20260928", today=date(2026, 9, 29))
    assert loaded["output"]["date"] == "20260928"


def test_canonical_snapshot_attaches_skill_and_candidate_fingerprints(tmp_path):
    m = _load_module()
    m.SNAPSHOT_ROOT = tmp_path
    candidates = [
        {"code": "000001", "name": "候选一", "score": 80.5},
        {"code": "000002", "name": "候选二", "score": 78.0},
        {"code": "600001", "name": "候选三", "score": 76.5},
    ]
    m.save_snapshot({
        "date": "20260929",
        "output": {"date": "20260929", "prediction_candidates": candidates},
        "inputs": {},
    })

    output = m.load_canonical("20260929")

    assert output["prediction_candidates"] == candidates
    assert output["canonical_source"] == "a-share-recommendation-skill-snapshot"
    assert output["candidate_fingerprint"] == m.candidate_fingerprint(candidates)
    assert output["strategy_contract"]["skill"] == "a-share-recommendation"
    assert len(output["strategy_contract"]["rules_fingerprint"]) == 64


def test_official_snapshot_time_is_1535():
    m = _load_module()
    assert m.OFFICIAL_SNAPSHOT_HHMM == "15:35"


def test_sector_phase_separates_mature_ladder_from_fermentation_seed():
    m = _load_module()
    ladder = _row("000001", "成熟板块")
    ladder.update(sector_limit_count=5, sector_max_board=4, sector_first_board_count=1)
    seed = _row("000002", "发酵板块", fbt=101500, zbc=1)
    seed.update(sector_limit_count=1, sector_max_board=1, sector_first_board_count=1)
    expansion = _row("000003", "扩散板块", fbt=101500, zbc=1)
    expansion.update(sector_limit_count=2, sector_max_board=1, sector_first_board_count=2)
    assert m.sector_phase(ladder) == "成熟梯队延续"
    assert m.sector_phase(seed) == "低位发酵种子"
    assert m._fermentation_score(seed) == 0
    assert m._fermentation_score(expansion) > 0


def test_fermentation_watchlist_surfaces_new_sector_without_expanding_buy_list():
    m = _load_module()
    rows = []
    for code, sector, max_board, count in [
        ("000001", "成熟A", 4, 5),
        ("000002", "成熟B", 3, 4),
        ("000003", "成熟C", 2, 3),
        ("000004", "新方向", 1, 1),
    ]:
        row = _row(code, sector, fbt=101500, zbc=1)
        row.update(
            sector_limit_count=count,
            sector_max_board=max_board,
            sector_first_board_count=1,
        )
        rows.append(row)
    sectors = [
        {"name": row["hybk"], "pct": 2.0, "net": 20.0}
        for row in rows
    ]
    ranked = m.rank_candidates(rows, sectors, limit=4)
    predictions = m.select_prediction_samples(ranked, {"open": True}, limit=3)
    radar = m.select_fermentation_watchlist(
        ranked, {row["code"] for row in predictions}, limit=3,
    )
    assert len(predictions) == 3
    assert any(row["sector"] == "新方向" for row in radar)
    assert all(row["status"] == "发酵观察" for row in radar)
