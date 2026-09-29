"""盘后候选 + 次日09:25竞价确认，两阶段都只读固定的三只1进2候选。"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

from . import intraday, trade_calendar
from .util import china_now, china_today, is_a_share_closed


_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = Path(os.environ.get("VR_DATA_DIR") or Path.home() / ".vibe-research")
_POST_ROOT = _DATA_ROOT / "a-share-recommendation" / "snapshots"
_AUCTION_ROOT = _DATA_ROOT / "a-share-recommendation" / "auction"
_RANKER_PATH = (
    _ROOT / ".codex" / "skills" / "a-share-recommendation" / "scripts" / "rank_first_boards.py"
)
_ranker: Any = None


def _compact(date: str) -> str:
    return "".join(ch for ch in str(date or "") if ch.isdigit())[:8]


def _dashed(date: str) -> str:
    value = _compact(date)
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 else ""


def _load_ranker():
    global _ranker
    if _ranker is not None:
        return _ranker
    spec = importlib.util.spec_from_file_location("a_share_recommendation_ranker", _RANKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载推荐脚本：{_RANKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _ranker = module
    return module


def official_snapshot_time() -> str:
    """Single source for the skill-defined official generation time."""
    return str(getattr(_load_ranker(), "OFFICIAL_SNAPSHOT_HHMM", "15:35"))


def official_snapshot_ready() -> bool:
    return is_a_share_closed() and china_now().strftime("%H:%M") >= official_snapshot_time()


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _write_once(path: Path, payload: dict) -> dict:
    existing = _read_json(path)
    if existing is not None:
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except FileExistsError:
        return _read_json(path) or payload
    return payload


def post_market(date: str | None = None, generate: bool = False) -> dict:
    """Read the skill's canonical snapshot; generate only after its official time."""
    target = _dashed(date or trade_calendar.latest_session() or "")
    if not target:
        return {"available": False, "stage": "post_market", "reason": "取不到最近已收盘交易日"}
    path = _POST_ROOT / f"{_compact(target)}.json"
    ranker = _load_ranker()
    ranker.SNAPSHOT_ROOT = _POST_ROOT
    if not path.exists() and generate:
        if target != china_today() or not official_snapshot_ready():
            return {
                "available": False, "stage": "post_market", "date": target,
                "reason": (
                    f"正式快照尚未生成；仅允许交易日{official_snapshot_time()}后生成，"
                    "历史日期禁止用当前数据补算"
                ),
            }
        ranker.load_live(_compact(target), enrich=True)
    try:
        output = ranker.load_canonical(_compact(target))
    except (OSError, ValueError, RuntimeError) as exc:
        return {
            "available": False, "stage": "post_market", "date": target,
            "reason": str(exc) or "这一天尚未生成盘后推荐快照",
        }
    candidates = list(output.get("prediction_candidates") or [])
    return {
        "available": bool(candidates),
        "stage": "post_market",
        "date": target,
        "decision_for": trade_calendar.next_trade_date(target),
        "generated_at": output.get("generated_at"),
        "locked": True,
        "candidates": candidates,
        "high_board_watchlist": output.get("high_board_watchlist") or [],
        "fermentation_watchlist": output.get("fermentation_watchlist") or [],
        "market_gate": output.get("market_gate") or {},
        "canonical_source": output.get("canonical_source"),
        "canonical_snapshot_date": output.get("canonical_snapshot_date"),
        "strategy_contract": output.get("strategy_contract") or {},
        "candidate_fingerprint": output.get("candidate_fingerprint"),
        "reason": "" if candidates else "盘后快照中没有候选",
    }


def _same_sector(left: str, right: str) -> bool:
    left, right = (left or "").strip(), (right or "").strip()
    return bool(left and right) and (left == right or left.startswith(right) or right.startswith(left))


def _auction_status(
    pct: float | None, sector_avg: float | None, market_median: float | None,
    coverage_rate: float | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if coverage_rate is None or coverage_rate < 0.8:
        return "数据不足", ["竞价行情覆盖率不足80%"]
    if pct is None:
        return "数据不足", ["候选股票竞价行情缺失"]
    if pct < -2:
        return "竞价淘汰", [f"竞价低开{pct:.2f}%，弱于-2%底线"]
    if sector_avg is not None and sector_avg < -1 and pct < 1:
        return "竞价淘汰", [f"所属行业昨日涨停股竞价均值{sector_avg:.2f}%，且个股未转强"]
    if pct > 7:
        return "等待换手", [f"竞价高开{pct:.2f}%，强度高但可成交性下降"]
    if 1 <= pct <= 5 and (sector_avg is None or sector_avg >= 0) and (
        market_median is None or market_median >= -1
    ):
        reasons.append(f"竞价涨幅{pct:.2f}%处于+1%至+5%确认区间")
        if sector_avg is not None:
            reasons.append(f"所属行业同批竞价均值{sector_avg:.2f}%")
        return "竞价确认", reasons
    reasons.append(f"竞价涨幅{pct:.2f}%尚未同时满足个股与行业确认条件")
    return "等待换手", reasons


def build_auction_result(post: dict, auction: dict) -> dict:
    """只重排盘后三只，不允许竞价阶段换股。"""
    candidates = list(post.get("candidates") or [])
    stocks = list(auction.get("stocks") or [])
    quotes = {str(row.get("code") or ""): row for row in stocks}
    coverage = auction.get("coverage_rate")
    market_median = (auction.get("overall") or {}).get("median")
    output = []
    for index, candidate in enumerate(candidates, start=1):
        code = str(candidate.get("code") or "")
        quote = quotes.get(code) or {}
        pct = quote.get("pct")
        sector = str(candidate.get("primary_industry") or candidate.get("sector") or "")
        peer_values = [
            float(row["pct"]) for row in stocks
            if row.get("pct") is not None and _same_sector(sector, str(row.get("sector") or ""))
        ]
        sector_avg = round(mean(peer_values), 2) if peer_values else None
        status, reasons = _auction_status(
            float(pct) if pct is not None else None,
            sector_avg,
            float(market_median) if market_median is not None else None,
            float(coverage) if coverage is not None else None,
        )
        output.append({
            "code": code,
            "name": candidate.get("name"),
            "sector": candidate.get("sector"),
            "primary_industry": candidate.get("primary_industry"),
            "post_market_rank": index,
            "post_market_score": candidate.get("score"),
            "auction_pct": round(float(pct), 2) if pct is not None else None,
            "sector_peer_avg": sector_avg,
            "status": status,
            "reasons": reasons,
        })
    status_order = {"竞价确认": 0, "等待换手": 1, "数据不足": 2, "竞价淘汰": 3}
    output.sort(key=lambda row: (
        status_order.get(str(row.get("status")), 9),
        -(row.get("auction_pct") if row.get("auction_pct") is not None else -99),
        row["post_market_rank"],
    ))
    for index, row in enumerate(output, start=1):
        row["auction_rank"] = index
    return {
        "available": bool(output),
        "stage": "auction",
        "date": auction.get("date"),
        "post_market_date": post.get("date"),
        "captured_at": auction.get("captured_at"),
        "locked_candidates": True,
        "coverage_rate": coverage,
        "market_median": market_median,
        "candidates": output,
        "counts": {status: sum(row["status"] == status for row in output)
                   for status in ("竞价确认", "等待换手", "竞价淘汰", "数据不足")},
        "data_scope": "腾讯L1竞价涨跌幅 + 昨日涨停股行业联动；不含逐笔撤单和未匹配单",
    }


def auction_result(date: str | None = None, persist: bool = True) -> dict:
    today = china_today()
    if date:
        target = _dashed(date)
    else:
        today_path = _AUCTION_ROOT / f"{_compact(today)}.json"
        if today_path.exists():
            target = today
        else:
            latest_post = post_market(generate=False)
            target = (
                str(latest_post.get("decision_for") or today)
                if latest_post.get("date") == today and is_a_share_closed()
                else today
            )
    path = _AUCTION_ROOT / f"{_compact(target)}.json"
    stored = _read_json(path)
    if stored is not None:
        return stored
    if target > today:
        return {
            "available": False, "stage": "auction", "date": target,
            "post_market_date": latest_post.get("date") if not date else None,
            "reason": f"等待 {target} 09:25 集合竞价结束后生成确认结果",
        }
    auction = intraday.auction_check(target)
    if not auction.get("available"):
        return {
            "available": False, "stage": "auction", "date": target,
            "reason": auction.get("reason") or "09:25竞价快照不可用",
        }
    previous = str(auction.get("prev_date") or "")
    post = post_market(previous, generate=False)
    if not post.get("available"):
        return {
            "available": False, "stage": "auction", "date": target,
            "post_market_date": previous,
            "reason": f"无法匹配前一交易日盘后候选：{post.get('reason', '快照缺失')}",
        }
    result = build_auction_result(post, auction)
    return _write_once(path, result) if persist else result
