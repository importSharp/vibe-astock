"""用项目 a-stock-data 适配层筛选真实首板的次日 1进2候选。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter
from datetime import date as date_type
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


BEIJING = timezone(timedelta(hours=8))
SNAPSHOT_SCHEMA = 1
STRATEGY_ID = "a-share-recommendation"
STRATEGY_CONTRACT_VERSION = 1
OFFICIAL_SNAPSHOT_HHMM = "15:35"
OFFICIAL_SNAPSHOT_TIME = time(15, 35)
SNAPSHOT_ROOT = Path(
    os.environ.get("A_SHARE_SNAPSHOT_DIR")
    or Path(os.environ.get("VR_DATA_DIR") or Path.home() / ".vibe-research")
    / "a-share-recommendation"
    / "snapshots"
)
MIN_LIMIT_UP = 42.0
MIN_BUYABILITY = 21.6
LIMIT_UP_WEIGHT = 1.4
BUYABILITY_WEIGHT = 0.6
CROWDED_SECTOR_PCT = 4.0
CROWDED_SECTOR_NET = 100.0
CROWDING_PENALTY = 3.0
MARKET_MIN_BREADTH = 0.50
MARKET_MIN_PROMOTION = 0.25
MARKET_MAX_BREAK_RATE = 0.25
MARKET_MIN_LIMIT_RETENTION = 0.70
HARD_RISK_TERMS = ("风险提示", "停牌核查", "暂停相关投资者账户交易", "严重异常波动")
SOFT_RISK_TERMS = ("股票交易异常波动", "减持", "监管")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _price(row: dict) -> float:
    return round(_num(row.get("p")) / 1000, 2)


def is_main_board(code: Any) -> bool:
    """仅接受沪深主板证券代码；排除创业板、科创板和北交所。"""
    value = str(code or "").strip()
    return len(value) == 6 and value.isdigit() and value.startswith(
        ("600", "601", "603", "605", "000", "001", "002", "003")
    )


def is_true_first_board(row: dict, max_price: float = 40.0) -> bool:
    """主板严格首板：板数口径为1，且价格严格低于上限。"""
    stats = row.get("zttj") or {}
    name = str(row.get("n") or "").upper()
    code = str(row.get("c") or "")
    return (
        is_main_board(code)
        and int(_num(row.get("lbc"), 1)) == 1
        and int(_num(stats.get("days"), 0)) == 1
        and int(_num(stats.get("ct"), 0)) == 1
        and 0 < _price(row) < max_price
        and "ST" not in name
    )


def _hhmm(value: Any) -> str:
    digits = str(int(_num(value))).zfill(6)
    return f"{digits[:2]}:{digits[2:4]}"


def _minutes(value: Any) -> int:
    raw = int(_num(value))
    hour, minute = raw // 10000, (raw // 100) % 100
    return hour * 60 + minute


def _sector_scores(sectors: list[dict]) -> dict[str, float]:
    ordered = sorted(
        sectors,
        key=lambda x: (_num(x.get("net")), _num(x.get("pct"))),
        reverse=True,
    )
    total = max(len(ordered), 1)
    scores = {}
    for index, sector in enumerate(ordered):
        rank_component = 26 * (1 - index / total)
        pct = _num(sector.get("pct"))
        trend_component = max(0.0, min(9.0, pct * 2.25))
        scores[str(sector.get("name") or "")] = round(rank_component + trend_component, 2)
    return scores


def _sector_score_for(name: str, scores: dict[str, float]) -> float:
    """兼容行情源中被截短的行业名，例如“汽车零部”与“汽车零部件”。"""
    if name in scores:
        return scores[name]
    matches = [score for sector, score in scores.items()
               if name.startswith(sector) or sector.startswith(name)]
    return max(matches, default=6.0)


def _sector_metrics_for(name: str, sectors: list[dict]) -> dict[str, float]:
    """取得评分板块的涨幅与净流入，兼容行情源截短行业名。"""
    matches = [
        row for row in sectors
        if name == str(row.get("name") or "")
        or name.startswith(str(row.get("name") or ""))
        or str(row.get("name") or "").startswith(name)
    ]
    if not matches:
        return {"pct": 0.0, "net": 0.0}
    best = max(matches, key=lambda row: (_num(row.get("net")), _num(row.get("pct"))))
    return {"pct": _num(best.get("pct")), "net": _num(best.get("net"))}


def match_sector(concept_tags: list[str], sector_names: set[str]) -> list[str]:
    """把“半导体概念”等标准概念名映射到同行业资金口径“半导体”。"""
    matches = []
    for sector in sector_names:
        if sector in concept_tags or f"{sector}概念" in concept_tags:
            matches.append(sector)
    return matches


def board_profile(row: dict) -> str:
    """按封板时间、开板次数和换手给首板贴可交易性标签。"""
    first = _minutes(row.get("fbt"))
    last = _minutes(row.get("lbt"))
    breaks = int(_num(row.get("zbc")))
    turnover = _num(row.get("hs"))
    amount = _num(row.get("amount"))
    if first <= 575 and last <= 575 and breaks == 0:
        return "过强硬板"
    if first >= 870:
        return "尾盘板"
    if 585 <= first <= 810 and breaks <= 2 and 5 <= turnover <= 20 and amount >= 100_000_000:
        return "换手首板"
    return "普通首板"


def next_day_path_profile(row: dict) -> dict[str, str]:
    """仅用盘后已知板型估计次日可参与路径，不生成盘中买点。"""
    first = _minutes(row.get("fbt"))
    last = _minutes(row.get("lbt"))
    breaks = int(_num(row.get("zbc")))
    turnover = _num(row.get("hs"))
    amount = _num(row.get("amount"))

    if first <= 580 and last <= 580 and breaks == 0:
        return {
            "type": "秒板难买风险",
            "availability_grade": "C",
            "explanation": "首板09:40前封住且零开板，次日若继续强化可能快速封死；涨停潜力不等于可成交。",
        }
    if first <= 585 and (breaks >= 1 or turnover < 5):
        return {
            "type": "早盘冲板分歧风险",
            "availability_grade": "B-",
            "explanation": "首板早盘冲板但存在开板或换手不足，次日容易先冲高再分歧，不能仅凭早盘强度判断晋级。",
        }
    if 585 <= first <= 810 and breaks <= 2 and 5 <= turnover <= 20 and amount >= 100_000_000:
        return {
            "type": "换手接力倾向",
            "availability_grade": "A",
            "explanation": "首板经过换手后封板，历史形态上通常比秒板提供更多可成交窗口，但仍不代表必然晋级。",
        }
    if first >= 870:
        return {
            "type": "尾盘延续风险",
            "availability_grade": "C",
            "explanation": "首板封板过晚，次日持续性和辨识度需要额外验证。",
        }
    return {
        "type": "普通接力路径",
        "availability_grade": "B",
        "explanation": "盘后板型未出现明显秒板或尾盘板特征；次日具体强弱仍由用户自行观察。",
    }


def _stock_quality(row: dict) -> float:
    first = _minutes(row.get("fbt"))
    time_score = 12 if first <= 585 else 10 if first <= 600 else 7 if first <= 660 else 5 if first <= 810 else 3 if first <= 870 else 1
    breaks = int(_num(row.get("zbc")))
    break_score = 8 if breaks == 0 else 6 if breaks == 1 else 4 if breaks == 2 else 2 if breaks == 3 else 0
    seal_ratio = _num(row.get("fund")) / max(_num(row.get("ltsz")), 1)
    seal_score = min(8.0, seal_ratio * 400)
    turnover = _num(row.get("hs"))
    amount = _num(row.get("amount"))
    liquidity_score = 7 if 3 <= turnover <= 20 and amount >= 100_000_000 else 4 if amount >= 50_000_000 else 1
    return round(min(35.0, time_score + break_score + seal_score + liquidity_score), 2)


def _information_score(row: dict) -> float:
    reason = str(row.get("reason") or "").strip()
    verified = row.get("information_verified") is True
    return 15.0 if verified else 10.0 if reason else 0.0


def sector_phase(row: dict) -> str:
    """区分成熟梯队与尚未形成高度、但可能继续扩散的低位首板。"""
    limit_count = int(_num(row.get("sector_limit_count"), 1))
    max_board = int(_num(row.get("sector_max_board"), 1))
    first_board_count = int(_num(row.get("sector_first_board_count"), 1))
    if max_board >= 2 and limit_count >= 3:
        return "成熟梯队延续"
    if max_board == 1 and first_board_count >= 2:
        return "首板扩散"
    if max_board == 1 and first_board_count == 1:
        return "低位发酵种子"
    return "梯队过渡"


def _fermentation_score(row: dict) -> float:
    """低位发酵最多14分；只奖励首板扩散和可换手的单一首板种子。"""
    if int(_num(row.get("sector_max_board"), 1)) != 1:
        return 0.0
    first_board_count = int(_num(row.get("sector_first_board_count"), 1))
    # 单一种子只进入观察雷达，不因“新”本身挤掉成熟高质量股。
    if first_board_count <= 1:
        return 0.0
    score = min(6.0, first_board_count * 3.0)
    if board_profile(row) == "换手首板":
        score += 4.0
    if int(_num(row.get("zbc"))) <= 1 and 585 <= _minutes(row.get("fbt")) <= 810:
        score += 2.0
    return round(min(14.0, score), 2)


def _continuation_score(row: dict) -> float:
    """板块结构14分：成熟梯队与低位发酵取较强者，避免只追昨日热点。"""
    limit_count = int(_num(row.get("sector_limit_count"), 1))
    max_board = int(_num(row.get("sector_max_board"), 1))
    breadth = min(6.0, max(0, limit_count - 1) * 1.5)
    height = min(8.0, max(0, max_board - 1) * 2.5)
    ladder_score = breadth + height
    return round(max(ladder_score, _fermentation_score(row)), 2)


def _sector_health(row: dict) -> dict[str, Any]:
    """只按板块群体结构判断活跃度，单只个股失败不得否决板块。"""
    limit_count = int(_num(row.get("sector_limit_count"), 1))
    max_board = int(_num(row.get("sector_max_board"), 1))
    first_board_count = int(_num(row.get("sector_first_board_count"), 1))
    active_signals = []
    if max_board >= 2:
        active_signals.append("仍有高度板")
    if first_board_count >= 1:
        active_signals.append("仍有新首板")
    if limit_count >= 3:
        active_signals.append("涨停宽度至少3只")

    if max_board >= 2 and first_board_count >= 1:
        state = "梯队活跃"
    elif first_board_count >= 2 or limit_count >= 3:
        state = "首板扩散"
    else:
        state = "孤立首板待确认"
    return {
        "state": state,
        "active_signals": active_signals,
        "sector_first_board_count": first_board_count,
        "single_stock_failure_can_veto": False,
    }


def _limit_up_score(row: dict, sector_score: float, crowding_penalty: float = 0.0) -> float:
    """原始涨停分50：趋势10 + 梯队14 + 板质21 + 催化5 - 过热惩罚。"""
    sector_part = min(10.0, max(0.0, sector_score / 35 * 10))
    continuation_part = _continuation_score(row)
    stock_part = min(21.0, max(0.0, _stock_quality(row) / 35 * 21))
    information_part = min(5.0, _information_score(row) / 15 * 5)
    return round(max(
        0.0,
        sector_part + continuation_part + stock_part + information_part - crowding_penalty,
    ), 2)


def _tradability(row: dict) -> float:
    """可买性 50 分：价格空间10 + 流动性10 + 换手10 + 封板形态20。"""
    price = _price(row)
    price_score = 10 if price <= 30 else max(0.0, (40 - price))
    amount = _num(row.get("amount"))
    amount_score = 10 if amount >= 300_000_000 else 8 if amount >= 100_000_000 else 3
    turnover = _num(row.get("hs"))
    turnover_score = 10 if 5 <= turnover <= 20 else 7 if 3 <= turnover < 5 else 3
    profile_score = {
        "换手首板": 20,
        "普通首板": 14,
        "过强硬板": 5,
        "尾盘板": 0,
    }[board_profile(row)]
    return round(min(50.0, price_score + amount_score + turnover_score + profile_score), 2)


def _status(total: float, row: dict, parts: dict[str, float]) -> str:
    profile = board_profile(row)
    if int(_num(row.get("zbc"))) >= 5 or profile == "尾盘板":
        return "禁止买入"
    balanced = parts["limit_up"] >= MIN_LIMIT_UP and parts["buyability"] >= MIN_BUYABILITY
    if total >= 70 and balanced:
        return "次日满足条件后可考虑"
    if total >= 55:
        if parts["buyability"] < MIN_BUYABILITY:
            return "仅观察（次日等换手）"
        return "仅观察"
    return "禁止买入"


def evaluate_market_gate(overview: dict | None, emotion: dict | None) -> dict[str, Any]:
    """识别进攻/防守模式；两项风险出现时不再隐藏三只预测样本。"""
    overview = overview or {}
    emotion = emotion or {}
    sentiment = overview.get("sentiment") or overview
    up = _num(sentiment.get("up"))
    down = _num(sentiment.get("down"))
    breadth = up / (up + down) if up + down else None
    promotion = _num(emotion.get("promotion_rate"), -1)
    break_rate = _num(emotion.get("break_rate"), -1)
    zt_count = _num(emotion.get("zt_count"), -1)
    yesterday_zt = _num(emotion.get("yzt_count"), -1)
    retention = zt_count / yesterday_zt if zt_count >= 0 and yesterday_zt > 0 else None

    missing = []
    adverse = []
    if breadth is None:
        missing.append("涨跌家数")
    elif breadth < MARKET_MIN_BREADTH:
        adverse.append("上涨家数不足半数")
    if promotion < 0:
        missing.append("晋级率")
    elif promotion < MARKET_MIN_PROMOTION:
        adverse.append("晋级率低于25%")
    if break_rate < 0:
        missing.append("炸板率")
    elif break_rate > MARKET_MAX_BREAK_RATE:
        adverse.append("炸板率高于25%")
    if retention is None:
        missing.append("涨停家数变化")
    elif retention < MARKET_MIN_LIMIT_RETENTION:
        adverse.append("涨停家数较前日收缩超过30%")

    is_open = not missing and len(adverse) < 2
    mode = "进攻模式" if is_open else "防守模式"
    return {
        "open": is_open,
        "mode": mode,
        "state": "进攻条件允许" if is_open else "弱市防守观察",
        "adverse_signals": adverse,
        "missing_metrics": missing,
        "metrics": {
            "breadth": round(breadth, 4) if breadth is not None else None,
            "promotion_rate": promotion if promotion >= 0 else None,
            "break_rate": break_rate if break_rate >= 0 else None,
            "limit_retention": round(retention, 4) if retention is not None else None,
        },
        "rule": "四项中出现至少两项风险或关键数据缺失时转为防守模式",
    }


def information_risk(context: dict | None) -> dict[str, Any]:
    """公告只做否决/降级，不把新闻热度当作涨停加分。"""
    context = context or {}
    titles = [
        str(item.get("title") or "")
        for group in (context.get("news", []), context.get("announcements", []))
        for item in group
    ]
    hard_hits = sorted({term for term in HARD_RISK_TERMS if any(term in title for title in titles)})
    soft_hits = sorted({term for term in SOFT_RISK_TERMS if any(term in title for title in titles)})
    return {
        "blocked": bool(hard_hits),
        "hard_signals": hard_hits,
        "soft_signals": soft_hits,
    }


def apply_information_risk(candidate: dict, context: dict | None) -> dict:
    candidate["information_context"] = context or {"news": [], "announcements": []}
    risk = information_risk(candidate["information_context"])
    candidate["information_risk"] = risk
    if risk["blocked"]:
        candidate["status"] = "仅观察（风险信息否决）"
    return candidate


def rank_candidates(pool: list[dict], sectors: list[dict], limit: int = 3) -> list[dict]:
    sector_scores = _sector_scores(sectors)
    ranked = []
    for row in pool:
        if not is_true_first_board(row):
            continue
        primary_industry = str(row.get("hybk") or "未分类")
        sector = str(row.get("selected_sector") or primary_industry)
        sector_score = round(_sector_score_for(sector, sector_scores), 2)
        sector_metrics = _sector_metrics_for(sector, sectors)
        is_crowded = (
            sector_metrics["pct"] >= CROWDED_SECTOR_PCT
            or sector_metrics["net"] >= CROWDED_SECTOR_NET
        )
        crowding_penalty = CROWDING_PENALTY if is_crowded else 0.0
        adjusted_trend_score = round(max(0.0, sector_score - crowding_penalty * 2), 2)
        raw_limit_up = _limit_up_score(row, sector_score, crowding_penalty)
        raw_buyability = _tradability(row)
        parts = {
            "limit_up": round(raw_limit_up * LIMIT_UP_WEIGHT, 2),
            "buyability": round(raw_buyability * BUYABILITY_WEIGHT, 2),
        }
        total = round(sum(parts.values()), 2)
        ranked.append({
            "code": str(row.get("c")),
            "name": str(row.get("n") or ""),
            "price": _price(row),
            "sector": sector,
            "primary_industry": primary_industry,
            "theme_sector": sector if sector != primary_industry else "",
            "sector_trend_score": sector_score,
            "sector_trend_adjusted_score": adjusted_trend_score,
            "sector_metrics": sector_metrics,
            "trend_confirmation": "单日趋势未验证",
            "crowding_risk": is_crowded,
            "seal_time": _hhmm(row.get("fbt")),
            "last_seal_time": _hhmm(row.get("lbt")),
            "break_count": int(_num(row.get("zbc"))),
            "turnover_pct": round(_num(row.get("hs")), 2),
            "amount": _num(row.get("amount")),
            "seal_amount": _num(row.get("fund")),
            "reason": str(row.get("reason") or ""),
            "concept_tags": list(row.get("concept_tags") or []),
            "board_profile": board_profile(row),
            "next_day_path": next_day_path_profile(row),
            "score": total,
            "score_parts": parts,
            "score_evidence": {
                "raw_limit_up_50": raw_limit_up,
                "raw_buyability_50": raw_buyability,
                "crowding_penalty_50": crowding_penalty,
                "fermentation_score_14": _fermentation_score(row),
            },
            "sector_phase": sector_phase(row),
            "continuation_context": {
                "sector_limit_count": int(_num(row.get("sector_limit_count"), 1)),
                "sector_max_board": int(_num(row.get("sector_max_board"), 1)),
                "sector_first_board_count": int(_num(row.get("sector_first_board_count"), 1)),
            },
            "sector_health": _sector_health(row),
            "status": _status(total, row, parts),
        })
    ranked.sort(key=lambda x: (
        -x["score"],
        -x["score_parts"]["limit_up"],
        -x["score_parts"]["buyability"],
        x["seal_time"],
        x["code"],
    ))

    selected: list[dict] = []
    counts: Counter[str] = Counter()
    for row in ranked:
        if counts[row["sector"]] >= 2:
            continue
        selected.append(row)
        counts[row["sector"]] += 1
        if len(selected) == limit:
            break

    if selected and limit >= 2 and len({x["sector"] for x in selected}) < 2:
        alternative = next((x for x in ranked if x["sector"] != selected[0]["sector"]), None)
        if alternative:
            selected[-1] = alternative

    for row in selected:
        row["slot_type"] = "综合排名席"

    return selected


def select_fermentation_watchlist(
    ranked: list[dict], selected_codes: set[str] | None = None, limit: int = 3,
) -> list[dict]:
    """列出低位发酵线索；仅用于防止漏看新方向，不是额外买入名单。"""
    selected_codes = selected_codes or set()
    phases = {"首板扩散", "低位发酵种子"}
    candidates = [
        row for row in ranked
        if row.get("sector_phase") in phases and row.get("code") not in selected_codes
    ]
    candidates.sort(key=lambda row: (
        -_num((row.get("score_evidence") or {}).get("fermentation_score_14")),
        -_num(row.get("score")),
        str(row.get("seal_time") or ""),
    ))
    seen_sectors: set[str] = set()
    output = []
    for row in candidates:
        sector = str(row.get("sector") or "未分类")
        if sector in seen_sectors:
            continue
        seen_sectors.add(sector)
        output.append({
            "code": row.get("code"),
            "name": row.get("name"),
            "sector": sector,
            "sector_phase": row.get("sector_phase"),
            "board_profile": row.get("board_profile"),
            "score": row.get("score"),
            "status": "发酵观察",
            "action": "只作次日板块验证，不是第四只买入候选",
            "reason": "板块尚未形成成熟高度梯队，但已有真实首板种子或首板扩散。",
        })
        if len(output) >= limit:
            break
    return output


def select_high_board_anchors(
    pool: list[dict], preferred_sectors: set[str] | None = None, limit: int = 2,
) -> list[dict]:
    """选择市场高度锚与候选板块高度锚；它们只验证情绪，不进入买入池。"""
    preferred_sectors = preferred_sectors or set()
    candidates = [
        row for row in pool
        if is_main_board(row.get("c"))
        and int(_num(row.get("lbc"), 1)) >= 2
        and "ST" not in str(row.get("n") or "").upper()
    ]
    candidates.sort(key=lambda row: (
        -int(_num(row.get("lbc"), 1)),
        -_num(row.get("amount")),
        str(row.get("c") or ""),
    ))
    selected: list[tuple[dict, str]] = []
    if candidates:
        selected.append((candidates[0], "市场高度锚"))
    relevant = next(
        (
            row for row in candidates
            if row not in [item[0] for item in selected]
            and str(row.get("hybk") or "未分类") in preferred_sectors
        ),
        None,
    )
    if relevant:
        selected.append((relevant, "候选板块高度锚"))
    for row in candidates:
        if len(selected) >= limit:
            break
        if row not in [item[0] for item in selected]:
            selected.append((row, "市场次高锚"))

    return [
        {
            "code": str(row.get("c") or ""),
            "name": str(row.get("n") or ""),
            "price": _price(row),
            "sector": str(row.get("hybk") or "未分类"),
            "boards": int(_num(row.get("lbc"), 1)),
            "role": role,
            "status": "高标观察",
            "action": "只观察，禁止作为1进2候选买入",
            "purpose": "验证市场高度、接力情绪和候选板块承接",
        }
        for row, role in selected[:limit]
    ]


def build_three_plus_two(
    ranked: list[dict], market_gate: dict, high_board_pool: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """3+2：三只统一按70:30排序的1进2候选，加两只高标观察锚。"""
    candidates = select_prediction_samples(ranked, market_gate, limit=3)
    preferred_sectors = {row["sector"] for row in candidates}
    high_board_watchlist = select_high_board_anchors(
        high_board_pool or [], preferred_sectors, limit=2,
    )
    return candidates, high_board_watchlist


def select_prediction_samples(ranked: list[dict], market_gate: dict, limit: int = 3) -> list[dict]:
    """固定输出涨停潜力70%、可买性30%排序最高的真实首板。"""
    if not ranked or limit <= 0:
        return []

    safe = [
        row for row in ranked
        if not (row.get("information_risk") or {}).get("blocked")
    ]
    pool = safe if len(safe) >= limit else ranked
    defensive = not market_gate.get("open")
    ordered = sorted(
        pool,
        key=lambda row: (
            -row["score"],
            -row["score_parts"]["limit_up"],
            -row["score_parts"]["buyability"],
            row["seal_time"],
            row["code"],
        ),
    )
    selected: list[dict] = []
    for row in ordered:
        if sum(item["sector"] == row["sector"] for item in selected) >= 2:
            continue
        selected.append(row)
        if len(selected) >= limit:
            break

    output: list[dict] = []
    for index, original in enumerate(selected[:limit]):
        row = original.copy()
        row["slot_type"] = f"1进2优先级{index + 1}"
        row["individual_status"] = original.get("status", "")
        row["market_mode"] = "防守模式" if defensive else "进攻模式"
        row["ranking_formula"] = "涨停潜力70% + 可买性30%"
        row["capital_confirmation"] = {
            "sector_pct": row["sector_metrics"]["pct"],
            "sector_net": row["sector_metrics"]["net"],
            "seal_amount": row["seal_amount"],
        }
        hard_veto = (
            str(original.get("status", "")).startswith("禁止买入")
            or (original.get("information_risk") or {}).get("blocked")
        )
        row["status"] = "风险样本" if hard_veto else "1进2预测候选"
        row["action"] = "仅提供候选排序和可买性评价；具体买点由用户自行判断"
        row["entry_conditions"] = []
        row["abandon_conditions"] = []
        row["buyability_note"] = (
            f"{row['board_profile']}；首封{row['seal_time']}；"
            f"换手{row['turnover_pct']}%；开板{row['break_count']}次"
        )
        row["evaluation_rule"] = {
            "limit_up_hit": "次日收盘封住涨停",
            "executable_limit_up_hit": "次日存在连续非涨停成交窗口，随后收盘封住涨停",
            "user_executable_limit_up_hit": "次日进入+1%至+3%的向上或稳定换手窗口，随后收盘封住涨停",
            "touch_board_failure": "次日触及涨停但收盘未封住",
        }
        output.append(row)
    return output


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "vr" / "astock.py").exists():
            return parent
    raise RuntimeError("找不到项目根目录 vr/astock.py")


def _normalize_data_date(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


def _snapshot_path(trading_date: str) -> Path:
    return SNAPSHOT_ROOT / f"{trading_date}.json"


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256_payload(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def strategy_contract() -> dict[str, Any]:
    """Return the deterministic contract shared by Codex and the website."""
    root = _skill_root()
    resources = [
        root / "SKILL.md",
        root / "references" / "strategy-spec.md",
        Path(__file__).resolve(),
    ]
    digest = hashlib.sha256()
    for path in resources:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "skill": STRATEGY_ID,
        "contract_version": STRATEGY_CONTRACT_VERSION,
        "rules_fingerprint": digest.hexdigest(),
        "official_snapshot_time": OFFICIAL_SNAPSHOT_HHMM,
    }


def candidate_fingerprint(candidates: list[dict]) -> str:
    """Fingerprint the complete ordered candidate payload, not only stock codes."""
    return _sha256_payload(candidates)


def load_snapshot(trading_date: str) -> dict | None:
    path = _snapshot_path(trading_date)
    if not path.exists():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != SNAPSHOT_SCHEMA:
        raise RuntimeError(f"快照版本不兼容：{path}")
    if document.get("date") != trading_date:
        raise RuntimeError(f"快照日期与文件名不一致：{path}")
    return document


def load_canonical(date: str | None = None) -> dict:
    """Read the immutable official result used by both Codex and the website.

    This function never performs a live recomputation. A missing official snapshot
    is an explicit error so callers cannot silently diverge from the website.
    """
    trading_date = _normalize_data_date(date)
    if not trading_date:
        snapshots = sorted(SNAPSHOT_ROOT.glob("????????.json"), reverse=True)
        if not snapshots:
            raise RuntimeError("尚无正式推荐快照；请等待交易日15:35自动生成")
        trading_date = snapshots[0].stem
    document = load_snapshot(trading_date)
    if document is None:
        raise RuntimeError(f"{trading_date} 尚无正式推荐快照；禁止用实时数据替代")
    output = dict(document.get("output") or {})
    candidates = list(output.get("prediction_candidates") or [])
    output.update({
        "canonical_source": "a-share-recommendation-skill-snapshot",
        "canonical_snapshot_date": trading_date,
        "canonical_snapshot_path": str(_snapshot_path(trading_date)),
        "strategy_contract": strategy_contract(),
        "candidate_fingerprint": candidate_fingerprint(candidates),
        "snapshot_status": "stored",
    })
    return output


def save_snapshot(document: dict) -> dict:
    """按交易日首次写入后保持不可变；重复保存直接返回原快照。"""
    trading_date = _normalize_data_date(document.get("date"))
    if not trading_date:
        raise ValueError("快照缺少有效交易日期")
    existing = load_snapshot(trading_date)
    if existing is not None:
        return existing
    payload = dict(document)
    payload["schema_version"] = SNAPSHOT_SCHEMA
    payload["date"] = trading_date
    payload.setdefault("snapshot_created_at", datetime.now(BEIJING).isoformat(timespec="seconds"))
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(trading_date)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except FileExistsError:
        return load_snapshot(trading_date) or payload
    return payload


def _historical_snapshot_or_raise(
    requested_date: str, today: date_type | None = None,
) -> dict | None:
    """历史回放必须读同日快照，禁止拿当前资金数据补算过去。"""
    trading_date = _normalize_data_date(requested_date)
    snapshot = load_snapshot(trading_date)
    if snapshot is not None:
        return snapshot
    today = today or datetime.now(BEIJING).date()
    requested = datetime.strptime(trading_date, "%Y%m%d").date()
    if requested < today:
        raise RuntimeError(
            f"历史日期 {trading_date} 缺少同日快照；已拒绝使用当前板块资金重算"
        )
    return None


def load_live(date: str | None = None, enrich: bool = True) -> dict:
    requested_date = _normalize_data_date(date) if date else ""
    if requested_date:
        stored = _historical_snapshot_or_raise(requested_date)
        if stored is not None:
            output = dict(stored.get("output") or {})
            output["snapshot_status"] = "stored"
            output["snapshot_path"] = str(_snapshot_path(requested_date))
            return output

    root = _project_root()
    sys.path.insert(0, str(root / "vr"))
    import astock  # type: ignore
    import firstboard  # type: ignore
    import market  # type: ignore

    base = datetime.strptime(requested_date, "%Y%m%d").date() if requested_date else datetime.now(BEIJING).date()
    resolved, pool = "", []
    for back in range(8):
        candidate_date = (base - timedelta(days=back)).strftime("%Y%m%d")
        pool = astock.em_zt_topic_pool("getTopicZTPool", candidate_date, "fbt:asc")
        if pool:
            resolved = candidate_date
            break
    if not pool:
        raise RuntimeError("最近8日未取得涨停池")

    reasons, reason_note = firstboard.get_reasons(resolved)
    sector_ladders: dict[str, dict[str, int]] = {}
    for row in pool:
        industry = str(row.get("hybk") or "未分类")
        stats = sector_ladders.setdefault(
            industry,
            {"limit_count": 0, "max_board": 1, "first_board_count": 0},
        )
        stats["limit_count"] += 1
        stats["max_board"] = max(stats["max_board"], int(_num(row.get("lbc"), 1)))
        if is_true_first_board(row):
            stats["first_board_count"] += 1
    eligible = [row.copy() for row in pool if is_true_first_board(row)]
    for row in eligible:
        row["reason"] = reasons.get(str(row.get("c")), "")
        ladder = sector_ladders.get(str(row.get("hybk") or "未分类"), {})
        row["sector_limit_count"] = ladder.get("limit_count", 1)
        row["sector_max_board"] = ladder.get("max_board", 1)
        row["sector_first_board_count"] = ladder.get("first_board_count", 1)

    try:
        overview = market.get_overview()
        emotion = market.get_short_term_emotion()
    except Exception as exc:  # noqa: BLE001 - 数据缺失必须保守关闭，不应中断输出
        overview, emotion = {}, {}
        market_error = f"{type(exc).__name__}: {exc}"
    else:
        market_error = ""
    sectors = list(overview.get("sectors") or [])
    sector_names = {str(item.get("name")) for item in sectors}
    if enrich:
        # 先按原始行业和板质保留前20，补概念后再做最终排名，控制请求量。
        prelim = sorted(eligible, key=_stock_quality, reverse=True)[:20]
        for row in prelim:
            blocks = astock.concept_blocks(str(row.get("c")))
            tags = [str(x.get("name")) for x in blocks.get("boards", [])]
            row["concept_tags"] = tags
            matched = match_sector(tags, sector_names)
            if matched:
                scores = _sector_scores(sectors)
                row["selected_sector"] = max(matched, key=lambda x: scores.get(x, 0))

    ranked = rank_candidates(eligible, sectors, limit=len(eligible))
    # 在组成3+2之前核查公告；风险词只做否决/降级，不做涨停加分。
    for candidate in ranked:
        code = candidate["code"]
        try:
            news = astock.stock_news(code, limit=6)
            announcements = astock.announcements(code, limit=5)
            information_error = ""
        except Exception as exc:  # noqa: BLE001 - 单股资讯故障不得拖垮整份计划
            news, announcements = [], []
            information_error = f"{type(exc).__name__}: {exc}"
        context = {
            "news": [
                {
                    "title": item.get("新闻标题", ""),
                    "published_at": item.get("发布时间", ""),
                    "url": item.get("新闻链接", ""),
                }
                for item in news
            ],
            "announcements": [
                {
                    "title": item.get("title", ""),
                    "date": item.get("date", ""),
                    "type": item.get("type", ""),
                    "url": item.get("url", ""),
                }
                for item in announcements
            ],
        }
        if information_error:
            context["data_error"] = information_error
        apply_information_risk(candidate, context)
        if information_error and candidate["status"] == "次日满足条件后可考虑":
            candidate["status"] = "仅观察（信息未验证）"

    market_gate = evaluate_market_gate(overview, emotion)
    if market_error:
        market_gate["data_error"] = market_error
    predictions, watchlist = build_three_plus_two(ranked, market_gate, pool)
    fermentation_watchlist = select_fermentation_watchlist(
        ranked, {row["code"] for row in predictions}, limit=3,
    )
    output = {
        "date": resolved,
        "generated_at": datetime.now(BEIJING).isoformat(timespec="minutes"),
        "source": "a-stock-data derived: Eastmoney limit pool/sector/concepts",
        "reason_note": reason_note,
        "eligible_count": len(eligible),
        "sector_data_available": bool(sectors),
        "market_gate": market_gate,
        "prediction_candidates": predictions,
        # 兼容旧调用方；该字段现在也是预测候选，不代表系统替用户作出买入决定。
        "purchase_candidates": predictions,
        "high_board_watchlist": watchlist,
        "fermentation_watchlist": fermentation_watchlist,
        "watchlist": watchlist,
        "candidates": predictions,
    }
    overview_date = _normalize_data_date((overview.get("sentiment") or {}).get("date"))
    emotion_date = _normalize_data_date(emotion.get("date"))
    now = datetime.now(BEIJING)
    dates_match = bool(overview_date and emotion_date) and {
        overview_date, emotion_date
    } == {resolved}
    after_close = resolved < now.strftime("%Y%m%d") or now.time() >= OFFICIAL_SNAPSHOT_TIME
    if dates_match and after_close and enrich:
        document = save_snapshot({
            "date": resolved,
            "enriched": True,
            "input_dates": {
                "limit_pool": resolved,
                "sector_and_breadth": overview_date,
                "short_term_emotion": emotion_date,
            },
            "inputs": {
                "limit_pool": pool,
                "overview": overview,
                "emotion": emotion,
                "ranked_candidates": ranked,
            },
            "output": output,
        })
        output["snapshot_status"] = "saved" if document.get("output") == output else "stored"
        output["snapshot_path"] = str(_snapshot_path(resolved))
    else:
        if not enrich:
            output["snapshot_status"] = "not_saved_without_enrichment"
        elif not dates_match:
            output["snapshot_status"] = "not_saved_date_mismatch"
        else:
            output["snapshot_status"] = "not_saved_before_close"
        output["snapshot_date_check"] = {
            "limit_pool": resolved,
            "sector_and_breadth": overview_date or "missing",
            "short_term_emotion": emotion_date or "missing",
        }
        if enrich:
            market_gate.setdefault("data_error", "数据日期不一致或尚未收盘，未生成不可变快照")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--canonical", action="store_true",
        help="读取网站与Codex共用的盘后不可变正式快照",
    )
    mode.add_argument(
        "--live", action="store_true",
        help="诊断模式：重新请求实时/收盘数据，不作为正式推荐结果",
    )
    parser.add_argument("--date", help="YYYYMMDD；缺省为最近有数据日期")
    parser.add_argument("--no-enrich", action="store_true", help="不请求概念归属")
    args = parser.parse_args()
    result = (
        load_canonical(args.date)
        if args.canonical
        else load_live(args.date, not args.no_enrich)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
