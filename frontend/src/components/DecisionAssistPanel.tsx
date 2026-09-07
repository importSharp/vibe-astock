import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, ShieldAlert, SlidersHorizontal } from "lucide-react";
import { agentFetch, safeArray, type DecisionAssistData, type DecisionCandidate } from "@/lib/agent";
import { cn } from "@/lib/utils";


function pct(v: number | null | undefined): string {
  return v == null ? "样本不足" : `${Math.round(v * 100)}%`;
}

function amount(v: number | null | undefined): string {
  if (v == null) return "—";
  return v >= 100_000_000 ? `${(v / 100_000_000).toFixed(1)}亿` : `${(v / 10_000).toFixed(0)}万`;
}

function tone(status: DecisionCandidate["status"]): string {
  if (status === "重点观察") return "bg-danger/15 text-danger";
  if (status === "观察") return "bg-primary/15 text-primary";
  if (status === "排除") return "bg-muted text-muted-foreground";
  return "bg-warning/15 text-warning";
}

function CandidateTable({ rows, rejected = false }: { rows: DecisionCandidate[]; rejected?: boolean }) {
  if (!rows.length) {
    return <div className="rounded-lg border border-dashed border-border px-3 py-5 text-center text-xs text-muted-foreground">
      {rejected ? "没有触发硬性否决的附加样本" : "当前规则下没有合格观察候选——空结果也是有效结果"}
    </div>;
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[820px] text-left text-xs">
        <thead className="bg-muted/40 text-muted-foreground">
          <tr>
            <th className="px-3 py-2">状态</th><th className="px-3 py-2">观察对象</th>
            <th className="px-3 py-2 text-right">规则分</th><th className="px-3 py-2">构成</th>
            <th className="px-3 py-2">同类历史</th><th className="px-3 py-2">依据 / 否决</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((c) => (
            <tr key={c.code} className={rejected ? "opacity-70" : ""}>
              <td className="px-3 py-2.5"><span className={cn("whitespace-nowrap rounded px-2 py-1 font-semibold", tone(c.status))}>{c.status}</span></td>
              <td className="px-3 py-2.5">
                <div className="font-semibold">{c.name} <span className="font-normal text-muted-foreground">{c.code}</span></div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">{c.sector || "行业未知"} · {c.boards}板 · 换手 {c.facts.turnover?.toFixed(1) ?? "—"}% · {amount(c.facts.amount)}</div>
              </td>
              <td className="px-3 py-2.5 text-right text-lg font-bold tabular-nums">{c.score.toFixed(1)}</td>
              <td className="px-3 py-2.5 text-[11px] tabular-nums text-muted-foreground">
                市场 {c.components.market} · 题材 {c.components.theme}<br />
                封板 {c.components.quality} · 流动 {c.components.liquidity} · 历史 {c.components.history}
              </td>
              <td className="px-3 py-2.5">
                <div className="font-semibold">{c.history.strategy} · {pct(c.history.win_rate)}</div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  n={c.history.sample}{c.history.avg != null ? ` · 均值 ${c.history.avg > 0 ? "+" : ""}${c.history.avg.toFixed(2)}%` : ""}
                </div>
              </td>
              <td className="max-w-[300px] px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
                {(rejected ? c.vetoes : c.reasons).join("；") || "暂无额外说明"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DecisionAssistPanel({ date }: { date: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<DecisionAssistData | null>(null);
  const [error, setError] = useState("");
  const [showRejected, setShowRejected] = useState(false);

  useEffect(() => {
    setOpen(false); setData(null); setError(""); setShowRejected(false);
  }, [date]);

  async function toggle() {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (data || loading) return;
    setLoading(true); setError("");
    try {
      const result = await agentFetch<DecisionAssistData>(`/api/review/decision-assist?date=${date}`);
      setData(result);
    } catch {
      setError("决策辅助生成失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-3">
      <button onClick={toggle}
        className="glass flex w-full items-center justify-between gap-3 rounded-2xl border border-primary/25 px-5 py-4 text-left hover:border-primary/50">
        <span className="flex items-center gap-3">
          <span className="rounded-lg bg-primary/10 p-2"><SlidersHorizontal className="h-5 w-5 text-primary" /></span>
          <span>
            <span className="block text-sm font-bold">个人决策辅助（实验功能，默认关闭）</span>
            <span className="mt-0.5 block text-xs font-normal text-muted-foreground">收盘事实规则评分 · 风险否决 · 同类历史统计；不输出买卖指令</span>
          </span>
        </span>
        {open ? <ChevronUp className="h-5 w-5 text-muted-foreground" /> : <ChevronDown className="h-5 w-5 text-muted-foreground" />}
      </button>

      {open && (
        <div className="glass space-y-4 rounded-2xl p-5">
          {loading && <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />正在计算规则评分…</div>}
          {error && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</div>}
          {!loading && data && !data.available && <div className="py-6 text-center text-sm text-muted-foreground">{data.reason || "当前不可用"}</div>}
          {!loading && data?.available && data.environment && (
            <>
              <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card/40 p-4">
                <div className="text-center"><div className="text-3xl font-black tabular-nums">{data.environment.score}</div><div className="text-[10px] text-muted-foreground">环境分 / 100</div></div>
                <div className="min-w-[180px] flex-1">
                  <div className="font-bold">{data.environment.level}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{data.environment.posture}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {safeArray<{ label: string; value: string | number; delta: number; detail: string }>(data.environment.signals).map((s) => (
                      <span key={s.label} title={s.detail} className={cn("rounded px-2 py-0.5 text-[10px]",
                        s.delta > 0 ? "bg-danger/10 text-danger" : s.delta < 0 ? "bg-success/10 text-success" : "bg-muted text-muted-foreground")}>{s.label} {s.delta > 0 ? "+" : ""}{s.delta}</span>
                    ))}
                  </div>
                </div>
                <div className="text-right text-[11px] text-muted-foreground">
                  来源 {data.counts?.source ?? 0} 只 · 通过 {data.counts?.active ?? 0} · 否决 {data.counts?.rejected ?? 0}<br />
                  {data.backtest?.available ? `历史窗口 ${data.backtest.days_used ?? "—"} 个交易日` : "尚无可用历史回测缓存"}
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-baseline justify-between gap-2">
                  <h3 className="text-sm font-bold">次日观察候选</h3>
                  <span className="text-[10px] text-muted-foreground">规则分不是上涨概率；同类胜率达到 30 个样本才展示</span>
                </div>
                <CandidateTable rows={safeArray(data.candidates)} />
              </div>

              {!!safeArray(data.rejected).length && (
                <div>
                  <button onClick={() => setShowRejected(!showRejected)} className="mb-2 flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground">
                    <ShieldAlert className="h-3.5 w-3.5" /> {showRejected ? "收起" : "查看"}风险否决样本（{data.counts?.rejected ?? data.rejected?.length}）
                  </button>
                  {showRejected && <CandidateTable rows={safeArray(data.rejected)} rejected />}
                </div>
              )}

              <div className="rounded-lg border border-warning/25 bg-warning/5 px-3 py-2.5">
                <div className="mb-1 text-xs font-bold text-warning">使用边界</div>
                <ul className="ml-4 list-disc space-y-0.5 text-[11px] leading-relaxed text-muted-foreground">
                  {safeArray<string>(data.limitations).map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
