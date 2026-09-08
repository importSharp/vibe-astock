"""个人决策辅助 —— 用收盘后已知事实缩小次日观察范围。

这不是模型荐股器。它只做三件事：

1. 把已有的市场情绪读数压成一个可解释的环境分；
2. 用固定、可审计的规则给当日涨停样本排序并执行风险否决；
3. 若已有回测缓存，附上同类样本的历史统计（绝不冒充个股概率）。

所有输入都在目标交易日收盘后可见，结果用于次一交易日观察，避免前视偏差。
"""

from __future__ import annotations

from typing import Any, Optional

from . import backtest, market_facts


VERSION = 1
MIN_PROBABILITY_SAMPLE = 30
MAX_ACTIVE = 12
MAX_REJECTED = 6


def _num(value: Any) -> Optional[float]:
    try:
        n = float(value)
        return n if n == n else None
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _clock(value: Any) -> str:
    """东财时间有时以整数 93100 返回；补成 HHMMSS 后才能安全比较。"""
    raw = str(value or "").strip().replace(":", "")
    return raw.zfill(6) if raw.isdigit() and len(raw) <= 6 else raw


def _market_environment(review: dict) -> dict:
    metrics = review.get("emotion_metrics") or {}
    facts = review.get("market_facts") or {}
    money = metrics.get("money_effect") or {}
    promotion = metrics.get("promotion") or {}
    cycle = metrics.get("cycle") or {}
    seal = facts.get("seal_quality") or {}
    breadth = facts.get("breadth") or {}

    score = 50.0
    signals: list[dict] = []

    def apply(label: str, raw: Any, delta: float, detail: str) -> None:
        nonlocal score
        if raw is None:
            return
        score += delta
        signals.append({"label": label, "value": raw, "delta": round(delta, 1), "detail": detail})

    median = _num(money.get("median"))
    if median is not None:
        apply("赚钱效应中位数", round(median, 2), _clamp(median * 2.0, -10, 10),
              "昨日涨停样本今天的中位收益")

    positive = _num(money.get("positive_rate"))
    if positive is not None:
        apply("翻红率", round(positive, 3), _clamp((positive - 0.5) * 20, -8, 8),
              "昨日涨停样本中收红的比例")

    promotion_rate = _num((promotion.get("overall") or {}).get("rate"))
    if promotion_rate is not None:
        apply("整体晋级率", round(promotion_rate, 3),
              _clamp((promotion_rate - 0.25) * 32, -8, 8), "昨日涨停股今天继续涨停的比例")

    broken_rate = _num(seal.get("broken_rate"))
    if broken_rate is not None:
        apply("真实炸板率", round(broken_rate, 3), _clamp((0.30 - broken_rate) * 25, -8, 8),
              "越高表示封板失败和试错成本越大")

    up, down = _num(breadth.get("up")), _num(breadth.get("down"))
    if up is not None and down is not None and up + down:
        ratio = (up - down) / (up + down)
        apply("市场宽度", round(ratio, 3), _clamp(ratio * 10, -6, 6), "上涨家数相对下跌家数")

    trend = str(cycle.get("trend") or "")
    if trend:
        delta = 5.0 if any(k in trend for k in ("走强", "上升", "回升")) else (
            -5.0 if any(k in trend for k in ("转弱", "下降", "走低")) else 0.0)
        apply("周期趋势", trend, delta, "近几日情绪周期的方向")

    score = round(_clamp(score, 0, 100), 1)
    if score >= 65:
        level, posture = "进攻窗口", "只观察高质量、强协同样本"
    elif score >= 50:
        level, posture = "谨慎窗口", "降低预期，优先等待次日确认"
    elif score >= 35:
        level, posture = "防守窗口", "仅跟踪，不因排名强行选择"
    else:
        level, posture = "回避窗口", "没有候选也属于有效结果"
    return {"score": score, "level": level, "posture": posture, "signals": signals}


def _theme_index(facts: dict) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    sectors = {
        str(t.get("sector") or ""): t
        for t in ((facts.get("theme_structure") or {}).get("themes") or [])
        if t.get("sector")
    }
    tags: dict[str, list[dict]] = {}
    for theme in ((facts.get("theme_tree") or {}).get("themes") or []):
        for member in theme.get("members") or []:
            code = str(member.get("code") or "").zfill(6)
            if code and code != "000000":
                tags.setdefault(code, []).append(theme)
    return sectors, tags


def _theme_score(row: dict, sectors: dict[str, dict], tags: dict[str, list[dict]]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    sector = sectors.get(str(row.get("sector") or "")) or {}
    limit_up = int(_num(sector.get("limit_up")) or 0)
    consec = int(_num(sector.get("consec_boards")) or 0)
    highest = int(_num(sector.get("highest")) or 0)
    broken = _num(sector.get("broken_rate"))
    if limit_up >= 5:
        score += 9
        reasons.append(f"行业涨停 {limit_up} 家")
    elif limit_up >= 3:
        score += 7
        reasons.append(f"行业涨停 {limit_up} 家")
    elif limit_up >= 2:
        score += 3
    if consec >= 2:
        score += 5
        reasons.append(f"行业有 {consec} 只连板")
    elif consec == 1:
        score += 3
    if highest >= 3:
        score += 4
        reasons.append(f"行业高度 {highest} 板")
    elif highest >= 2:
        score += 2
    if broken is not None and broken <= 0.20:
        score += 3
    elif broken is not None and broken >= 0.45:
        score -= 3
        reasons.append("行业炸板率偏高")

    member_tags = tags.get(str(row.get("code") or "").zfill(6), [])
    if member_tags:
        best = max(member_tags, key=lambda x: (int(_num(x.get("limit_up")) or 0),
                                               int(_num(x.get("highest")) or 0)))
        n = int(_num(best.get("limit_up")) or 0)
        cont = _num(best.get("continuation_rate"))
        if n >= 3:
            score += 4
            reasons.append(f"题材「{best.get('tag')}」{n} 家涨停")
        if cont is not None and cont >= 0.35:
            score += 2
            reasons.append(f"题材延续率 {cont:.0%}")
    return round(_clamp(score, 0, 25), 1), reasons


def _quality_score(row: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    broken = int(_num(row.get("broken_times")) or 0)
    first = _clock(row.get("first_seal"))
    last = _clock(row.get("last_seal"))
    if broken == 0:
        score += 10
        reasons.append("全天未开板")
    elif broken == 1:
        score += 6
        reasons.append("开板 1 次后回封")
    elif broken == 2:
        score += 2
        reasons.append("开板 2 次")
    else:
        reasons.append(f"反复开板 {broken} 次")
    if first and first <= "093500":
        score += 5
        reasons.append("早盘快速封板")
    elif first and first <= "100000":
        score += 4
    elif first and first <= "110000":
        score += 2
    if last and last <= "100000":
        score += 5
    elif last and last <= "110000":
        score += 3
    elif last and last <= "140000":
        score += 1
    return round(_clamp(score, 0, 20), 1), reasons


def _liquidity_score(row: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    amount = _num(row.get("amount"))
    turnover = _num(row.get("turnover"))
    if amount is not None:
        if amount >= 1_000_000_000:
            score += 8
            reasons.append("成交额超过 10 亿")
        elif amount >= 500_000_000:
            score += 6
            reasons.append("成交额超过 5 亿")
        elif amount >= 200_000_000:
            score += 4
        elif amount >= 100_000_000:
            score += 2
    if turnover is not None:
        if 3 <= turnover <= 20:
            score += 7
            reasons.append(f"换手率 {turnover:.1f}%")
        elif 20 < turnover <= 35:
            score += 5
        elif 1 <= turnover < 3:
            score += 3
        elif turnover <= 45:
            score += 1
    return round(_clamp(score, 0, 15), 1), reasons


def _strategy_name(row: dict) -> str:
    boards = int(_num(row.get("boards")) or 1)
    last = _clock(row.get("last_seal"))
    if boards >= 3:
        return "高标接力"
    if boards >= 2:
        return "连板接力"
    if last and last <= "100000":
        return "首板·早封"
    if last and last >= "143000":
        return "首板·尾盘封"
    return "首板打板"


def _history_prior(row: dict, cached: Optional[dict]) -> dict:
    strategy = _strategy_name(row)
    result = ((cached or {}).get("strategies") or {}).get(strategy) or {}
    stats = result.get("overall") or {}
    sample = int(_num(stats.get("sample")) or 0)
    win_rate = _num(stats.get("win_rate"))
    avg = _num(stats.get("avg"))
    median = _num(stats.get("median"))
    limit_up_rate = _num(stats.get("limit_up_rate"))
    probability = round(win_rate, 3) if win_rate is not None and sample >= MIN_PROBABILITY_SAMPLE else None
    history_score = 5.0
    if probability is not None:
        history_score = _clamp(probability * 8 + _clamp((avg or 0) / 3, -1, 1) * 2, 0, 10)
    return {
        "strategy": strategy, "sample": sample, "win_rate": probability,
        "avg": round(avg, 2) if avg is not None else None,
        "median": round(median, 2) if median is not None else None,
        "limit_up_rate": round(limit_up_rate, 3) if limit_up_rate is not None and sample >= MIN_PROBABILITY_SAMPLE else None,
        "enough_samples": sample >= MIN_PROBABILITY_SAMPLE,
        "min_samples": MIN_PROBABILITY_SAMPLE,
        "score": round(history_score, 1),
        "scope": "同类规则的历史群体统计，不是该股票的个体概率",
    }


def _vetoes(row: dict, sector_size: int, has_theme_cluster: bool) -> list[str]:
    out: list[str] = []
    name = str(row.get("name") or "")
    broken = int(_num(row.get("broken_times")) or 0)
    last = _clock(row.get("last_seal"))
    first = _clock(row.get("first_seal"))
    turnover = _num(row.get("turnover"))
    boards = int(_num(row.get("boards")) or 1)
    if "ST" in name.upper():
        out.append("ST 风险制度不同")
    if broken >= 4:
        out.append(f"反复开板 {broken} 次")
    if last and last >= "143000":
        out.append("14:30 后才最终封板")
    if turnover is not None and turnover > 45:
        out.append(f"换手率过高（{turnover:.1f}%）")
    if boards == 1 and sector_size <= 1 and not has_theme_cluster:
        out.append("板块孤立，缺少协同")
    if first and last and first <= "093100" and last <= "093100" and broken == 0 and (turnover or 0) < 1:
        out.append("疑似一字板，次日成交可行性不足")
    return out


def _load_backtest() -> Optional[dict]:
    for days in (60, 30):
        found = backtest.load_result(days)
        if found:
            return found
    return None


def build(date: str, review: dict) -> dict:
    """生成次日个人决策辅助快照；失败时返回可解释的 unavailable。"""
    pools = market_facts.pools(date)
    if not pools or not pools.get("zt"):
        return {"available": False, "date": date, "reason": "目标日涨停池明细不可用"}

    facts = review.get("market_facts") or {}
    environment = _market_environment(review)
    sectors, tags = _theme_index(facts)
    cached = _load_backtest()
    candidates = []

    for row in pools["zt"]:
        theme_score, theme_reasons = _theme_score(row, sectors, tags)
        quality_score, quality_reasons = _quality_score(row)
        liquidity_score, liquidity_reasons = _liquidity_score(row)
        prior = _history_prior(row, cached)
        market_score = round(environment["score"] * 0.30, 1)
        total = round(market_score + theme_score + quality_score + liquidity_score + prior["score"], 1)

        sector = str(row.get("sector") or "")
        sector_size = int(_num((sectors.get(sector) or {}).get("limit_up")) or 0)
        member_tags = tags.get(str(row.get("code") or "").zfill(6), [])
        has_theme_cluster = any(int(_num(x.get("limit_up")) or 0) >= 2 for x in member_tags)
        vetoes = _vetoes(row, sector_size, has_theme_cluster)
        if vetoes:
            status = "排除"
        elif environment["score"] < 35:
            status = "仅跟踪"
        elif total >= 72:
            status = "重点观察"
        elif total >= 60:
            status = "观察"
        else:
            status = "低优先级"
        candidates.append({
            "code": str(row.get("code") or "").zfill(6),
            "name": str(row.get("name") or ""),
            "sector": sector,
            "boards": int(_num(row.get("boards")) or 1),
            "score": total,
            "status": status,
            "vetoes": vetoes,
            "components": {
                "market": market_score, "theme": theme_score, "quality": quality_score,
                "liquidity": liquidity_score, "history": prior["score"],
            },
            "reasons": (theme_reasons + quality_reasons + liquidity_reasons)[:5],
            "history": {k: v for k, v in prior.items() if k != "score"},
            "facts": {
                "first_seal": _clock(row.get("first_seal")) or None,
                "last_seal": _clock(row.get("last_seal")) or None,
                "broken_times": int(_num(row.get("broken_times")) or 0),
                "turnover": _num(row.get("turnover")), "amount": _num(row.get("amount")),
            },
        })

    active = sorted((x for x in candidates if not x["vetoes"]), key=lambda x: x["score"], reverse=True)
    rejected = sorted((x for x in candidates if x["vetoes"]), key=lambda x: x["score"], reverse=True)
    return {
        "available": True, "version": VERSION, "date": date,
        "decision_for": "next_session", "environment": environment,
        "candidates": active[:MAX_ACTIVE], "rejected": rejected[:MAX_REJECTED],
        "counts": {"source": len(candidates), "active": len(active), "rejected": len(rejected)},
        "weights": {"market": 30, "theme": 25, "quality": 20, "liquidity": 15, "history": 10},
        "backtest": {
            "available": bool(cached),
            "days_used": (cached or {}).get("days_used"),
            "date_from": (cached or {}).get("date_from"),
            "date_to": (cached or {}).get("date_to"),
        },
        "limitations": [
            "评分只使用收盘后已知数据，供次一交易日观察，不是买卖指令。",
            "历史胜率是同类规则的群体统计，不是某只股票的个体上涨概率。",
            "现有历史样本遗漏冲板未封、排队未成交和部分一字板，真实执行通常更差。",
            "系统允许没有合格候选；不要为了排名而强行选择。",
        ],
    }
