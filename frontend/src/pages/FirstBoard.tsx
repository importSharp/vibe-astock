import { Fragment, useEffect, useState } from "react";
import { Flame, Loader2, Sparkles, AlertCircle, X, MoonStar, TimerReset } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Caliber } from "@/components/ui/Caliber";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { useDeepDive, DeepDivePanel, RunAllButton, type DiveItem } from "@/components/ui/DeepDive";
import {
  api, type AuctionRecommendation, type FirstBoardData, type FirstBoardStock,
  type PostMarketRecommendation,
} from "@/lib/api";

const fmt = (v: number) => v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
const yi = (v: number | null) => (v == null ? "—" : `${fmt(v / 1e8)} 亿`); // 元 → 亿

const dateLabel = (d: string) =>
  d.length === 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}` : d;

export function FirstBoard() {
  const [data, setData] = useState<FirstBoardData | null>(null);
  const [postMarket, setPostMarket] = useState<PostMarketRecommendation | null>(null);
  const [auction, setAuction] = useState<AuctionRecommendation | null>(null);
  const [loaded, setLoaded] = useState(false);
  const dd = useDeepDive("firstboard", data?.date || "");

  useEffect(() => {
    Promise.allSettled([
      api.firstBoard().then(setData),
      api.postMarketRecommendation().then(setPostMarket),
      api.auctionRecommendation().then(setAuction),
    ]).finally(() => setLoaded(true));
  }, []);

  const buildPrompt = (s: FirstBoardStock) =>
    `今天（${dateLabel(data?.date || "")}）A 股首板涨停股「${s.name}（${s.code}）」的客观数据：\n` +
    `现价 ${s.price} 元，涨停 +${s.pct}%，首次封板时间 ${s.seal_time || "未知"}，` +
    `炸板 ${s.break_count} 次，成交额 ${yi(s.amount)}，流通市值 ${yi(s.float_cap)}，` +
    `所属行业 ${s.industry || "未知"}，涨停原因题材：${s.reason || "（暂缺，需要自查）"}。\n\n` +
    "请深入分析这只股票今天涨停的原因：\n" +
    "1. 先调用工具查询这只股票的近期新闻与研报，结合上面的题材串，说清今天涨停最可能的驱动因素（消息面 / 题材面 / 资金面）；\n" +
    "2. 就**这个题材板块整体**说清它的强度与所处阶段（情绪性的一日游 / 有产业逻辑或业绩支撑），" +
    "并给出依据 —— 只讲题材板块层面，不要由此推断这只个股接下来会怎样；\n" +
    "3. 客观列出值得注意的点（炸板情况、封板时间早晚、流通盘大小、题材扩散位置）。\n" +
    "个股层面只陈述已经发生的客观数据与事实，方向与强弱判断做到题材板块层面为止：" +
    "不预测个股涨跌、不给个股参与倾向、不推荐任何标的、不构成投资建议。" +
    "输出用纯 Markdown（不要在表格或正文里使用 <br> 等 HTML 标签）。";

  const ctx = (s: FirstBoardStock) => `首板股 ${s.name}(${s.code}) 涨停原因深入分析`;
  const diveItem = (s: FirstBoardStock): DiveItem => ({ key: s.code, prompt: buildPrompt(s), context: ctx(s) });

  const stocks = data?.stocks ?? [];
  const nameByCode = Object.fromEntries(stocks.map((s) => [s.code, s.name]));

  return (
    <div>
      <PageHeader
        title="首板分析"
        subtitle="今日首板涨停股（连板数=1）· 涨停原因题材 · 每只可让 AI 深入分析"
      />

      <div className="mb-4 grid gap-3 lg:grid-cols-2">
        <GlassCard>
          <div className="mb-3 flex items-center gap-2">
            <MoonStar className="h-4 w-4 text-primary" />
            <div>
              <div className="text-sm font-bold">第一阶段 · 盘后推荐</div>
              <div className="text-xs text-muted-foreground">
                {postMarket?.date ? `${postMarket.date} 收盘定稿` : "最近收盘交易日"} · 三只名单锁定
              </div>
            </div>
          </div>
          {!postMarket ? (
            <div className="py-5 text-sm text-muted-foreground">加载中…</div>
          ) : !postMarket.available ? (
            <div className="rounded-lg bg-warning/10 p-3 text-sm text-warning">
              {postMarket.reason || "盘后推荐尚未生成"}
            </div>
          ) : (
            <div className="space-y-2">
              {(postMarket.candidates || []).map((s, i) => (
                <div key={s.code} className="rounded-xl border border-border/50 bg-background/35 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-bold text-primary">#{i + 1}</span>
                    <span className="font-semibold">{s.name}</span>
                    <span className="font-mono text-xs text-muted-foreground">{s.code}</span>
                    <span className="ml-auto text-xs text-muted-foreground">总分 {s.score}</span>
                  </div>
                  <div className="mt-1.5 text-xs text-muted-foreground">
                    {s.sector} · {s.sector_phase || "阶段未标注"} · {s.board_profile}
                  </div>
                  <div className="mt-1 text-xs">
                    涨停潜力 {s.score_parts.limit_up} / 70 · 可买性 {s.score_parts.buyability} / 30
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard>
          <div className="mb-3 flex items-center gap-2">
            <TimerReset className="h-4 w-4 text-primary" />
            <div>
              <div className="text-sm font-bold">第二阶段 · 09:25竞价确认</div>
              <div className="text-xs text-muted-foreground">只确认、等待或淘汰昨晚三只，不临时换股</div>
            </div>
          </div>
          {!auction ? (
            <div className="py-5 text-sm text-muted-foreground">加载中…</div>
          ) : !auction.available ? (
            <div className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">
              {auction.reason || "等待下一交易日09:25竞价快照"}
            </div>
          ) : (
            <div className="space-y-2">
              {(auction.candidates || []).map((s) => {
                const tone = s.status === "竞价确认"
                  ? "bg-primary/10 text-primary"
                  : s.status === "竞价淘汰"
                    ? "bg-danger/10 text-danger"
                    : "bg-warning/10 text-warning";
                return (
                  <div key={s.code} className="rounded-xl border border-border/50 bg-background/35 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${tone}`}>{s.status}</span>
                      <span className="font-semibold">{s.name}</span>
                      <span className="font-mono text-xs text-muted-foreground">{s.code}</span>
                      <span className="ml-auto font-mono text-sm font-bold">
                        {s.auction_pct == null ? "—" : `${s.auction_pct > 0 ? "+" : ""}${s.auction_pct}%`}
                      </span>
                    </div>
                    <div className="mt-1.5 text-xs text-muted-foreground">
                      盘后#{s.post_market_rank} → 竞价#{s.auction_rank} · {s.sector}
                      {s.sector_peer_avg == null ? "" : ` · 行业同批均值 ${s.sector_peer_avg > 0 ? "+" : ""}${s.sector_peer_avg}%`}
                    </div>
                    <div className="mt-1 text-xs">{s.reasons.join("；")}</div>
                  </div>
                );
              })}
              <div className="pt-1 text-[11px] leading-relaxed text-muted-foreground">
                {auction.data_scope}
              </div>
            </div>
          )}
        </GlassCard>
      </div>

      {data && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          {[
            { label: "交易日", value: dateLabel(data.date) },
            { label: "今日涨停", value: `${data.total_zt} 家` },
            { label: "其中首板", value: `${data.first_count} 家` },
          ].map((c) => (
            <GlassCard key={c.label} className="py-3 text-center">
              <div className="text-xs text-muted-foreground">{c.label}</div>
              <div className="mt-1 font-mono text-lg font-bold text-primary">{c.value}</div>
            </GlassCard>
          ))}
        </div>
      )}

      {data?.reason_note && (
        <p className="mb-3 flex items-center gap-1.5 text-xs text-muted-foreground">
          <AlertCircle className="h-3.5 w-3.5" /> 涨停原因：{data.reason_note}
        </p>
      )}

      <GlassCard>
        <div className="mb-2 flex flex-wrap items-center gap-2 text-sm font-semibold">
          <Flame className="h-4 w-4 text-primary" /> 首板名单
          <Caliber text={
            "「炸板」是当天开板过几次，0 就是全天没开过板 —— 这张表里的票**最终都封住了涨停**，\n" +
            "所以炸板次数说的是过程有多难看，不是最后有没有封住。\n" +
            "名单按首次封板时间从早到晚排。\n" +
            "「行业」经常只有四个字（像「互联网电」「自动化设」）——是上游把名字截到四字，\n" +
            "不是这里显示不全；怕猜错所以不替它补全称。"
          } />
          <span className="text-xs font-normal text-muted-foreground">
            按首次封板时间排序（早封在前）· 客观公开榜单，非推荐 / 非预测
          </span>
          <span className="ml-auto font-normal">
            <RunAllButton dd={dd} items={stocks.map(diveItem)} nameOf={(k) => nameByCode[k] || k} />
          </span>
        </div>
        {!loaded ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
          </div>
        ) : stocks.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">暂无数据（数据源异常或非交易日）</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                  {["名称", "首封", "炸板", "现价", "当日涨幅", "成交额", "流通市值", "涨停原因", "行业", ""].map((h) => (
                    <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stocks.map((s) => (
                  <Fragment key={s.code}>
                    <tr className="border-b border-border/30">
                      <td className="whitespace-nowrap px-2 py-2">
                        <span className="font-medium">{s.name}</span>{" "}
                        <span className="text-xs text-muted-foreground/50">{s.code}</span>
                      </td>
                      <td className="whitespace-nowrap px-2 py-2 font-mono text-muted-foreground">{s.seal_time || "—"}</td>
                      <td className="whitespace-nowrap px-2 py-2 font-mono">
                        {s.break_count > 0 ? <span className="text-primary">{s.break_count} 次</span> : <span className="text-muted-foreground/50">0</span>}
                      </td>
                      <td className="px-2 py-2 font-mono">{s.price}</td>
                      <td className="px-2 py-2 font-mono text-danger">+{s.pct}%</td>
                      <td className="whitespace-nowrap px-2 py-2 font-mono text-muted-foreground">{yi(s.amount)}</td>
                      <td className="whitespace-nowrap px-2 py-2 font-mono text-muted-foreground">{yi(s.float_cap)}</td>
                      <td className="max-w-56 px-2 py-2 text-xs">
                        {s.reason ? <span className="text-foreground">{s.reason}</span> : <span className="text-muted-foreground/50">—</span>}
                      </td>
                      <td className="whitespace-nowrap px-2 py-2 text-xs text-muted-foreground">{s.industry}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-right">
                        <button
                          onClick={() => dd.toggle(diveItem(s))}
                          className="inline-flex items-center gap-1 rounded-lg border border-primary/50 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
                        >
                          {dd.running === s.code ? <Loader2 className="h-3 w-3 animate-spin" /> : dd.open === s.code ? <X className="h-3 w-3" /> : <Sparkles className="h-3 w-3" />}
                          {dd.open === s.code ? "收起" : dd.analysis[s.code] ? "展开" : "深入分析"}
                        </button>
                      </td>
                    </tr>
                    {dd.open === s.code && (
                      <DeepDivePanel
                        dd={dd}
                        stockKey={s.code}
                        colSpan={10}
                        noteTitle={`首板深析 · ${s.name}`}
                        onRerun={() => dd.rerun(diveItem(s))}
                      />
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      <Disclaimer />
    </div>
  );
}
