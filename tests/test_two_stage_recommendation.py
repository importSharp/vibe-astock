from __future__ import annotations

import json

from duanxian import recommendation as rec


def _post() -> dict:
    return {
        "available": True,
        "date": "2026-09-29",
        "candidates": [
            {"code": "000001", "name": "确认股", "sector": "元件", "primary_industry": "元件", "score": 80},
            {"code": "000002", "name": "高开股", "sector": "电池", "primary_industry": "电池", "score": 78},
            {"code": "000003", "name": "弱势股", "sector": "电力", "primary_industry": "电力", "score": 76},
        ],
    }


def _auction(coverage: float = 0.95) -> dict:
    return {
        "available": True,
        "date": "2026-09-30",
        "prev_date": "2026-09-29",
        "captured_at": "2026-09-30 09:25:30 CST",
        "coverage_rate": coverage,
        "overall": {"median": 0.2},
        "stocks": [
            {"code": "000001", "sector": "元件", "pct": 2.5},
            {"code": "600001", "sector": "元件", "pct": 1.0},
            {"code": "000002", "sector": "电池", "pct": 8.0},
            {"code": "000003", "sector": "电力", "pct": -3.0},
            {"code": "000099", "sector": "其他", "pct": 9.9},
        ],
    }


def test_auction_only_reorders_locked_post_market_candidates():
    result = rec.build_auction_result(_post(), _auction())
    rows = result["candidates"]
    assert {row["code"] for row in rows} == {"000001", "000002", "000003"}
    assert "000099" not in {row["code"] for row in rows}
    assert [row["status"] for row in rows] == ["竞价确认", "等待换手", "竞价淘汰"]
    assert [row["auction_rank"] for row in rows] == [1, 2, 3]
    assert result["locked_candidates"] is True


def test_low_coverage_marks_all_candidates_as_data_insufficient():
    result = rec.build_auction_result(_post(), _auction(0.5))
    assert len(result["candidates"]) == 3
    assert all(row["status"] == "数据不足" for row in result["candidates"])


def test_auction_snapshot_is_write_once(tmp_path, monkeypatch):
    monkeypatch.setattr(rec, "_AUCTION_ROOT", tmp_path)
    path = tmp_path / "20260930.json"
    first = rec._write_once(path, {"marker": "first"})
    second = rec._write_once(path, {"marker": "second"})
    assert first["marker"] == "first"
    assert second["marker"] == "first"
    assert json.loads(path.read_text(encoding="utf-8"))["marker"] == "first"


def test_post_market_reads_three_candidates_from_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(rec, "_POST_ROOT", tmp_path)
    payload = {
        "schema_version": 1,
        "date": "20260929",
        "output": {"generated_at": "2026-09-29T15:10+08:00", "prediction_candidates": _post()["candidates"]},
    }
    (tmp_path / "20260929.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8",
    )
    monkeypatch.setattr(rec.trade_calendar, "next_trade_date", lambda _date: "2026-09-30")
    result = rec.post_market("2026-09-29", generate=False)
    assert result["available"] is True
    assert result["locked"] is True
    assert len(result["candidates"]) == 3
    assert result["decision_for"] == "2026-09-30"
    assert result["canonical_source"] == "a-share-recommendation-skill-snapshot"
    assert result["strategy_contract"]["skill"] == "a-share-recommendation"
    assert len(result["candidate_fingerprint"]) == 64


def test_after_close_default_auction_waits_for_next_session(tmp_path, monkeypatch):
    monkeypatch.setattr(rec, "_POST_ROOT", tmp_path / "post")
    monkeypatch.setattr(rec, "_AUCTION_ROOT", tmp_path / "auction")
    rec._POST_ROOT.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "date": "20260929",
        "output": {"prediction_candidates": _post()["candidates"]},
    }
    (rec._POST_ROOT / "20260929.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8",
    )
    monkeypatch.setattr(rec, "china_today", lambda: "2026-09-29")
    monkeypatch.setattr(rec, "is_a_share_closed", lambda: True)
    monkeypatch.setattr(rec.trade_calendar, "latest_session", lambda: "2026-09-29")
    monkeypatch.setattr(rec.trade_calendar, "next_trade_date", lambda _date: "2026-09-30")
    result = rec.auction_result()
    assert result["available"] is False
    assert result["date"] == "2026-09-30"
    assert "等待" in result["reason"]
