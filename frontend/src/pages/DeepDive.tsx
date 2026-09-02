import { useEffect, useRef, useState } from "react";
import { Microscope, Loader2, Target } from "lucide-react";
import { cn } from "@/lib/utils";
import { AgentChat } from "@/components/AgentChat";
import { agentFetch, safeArray, type DeepDiveData, type JobStatus } from "@/lib/agent";

const DISCLAIMER =
  "本页由多 agent AI 基于公开数据现场生成，结论为 AI 判断，仅供参考，不构成投资建议；市场有风险，决策与盈亏自负。";

function stanceTone(stance?: string): string {
  if (stance === "值得关注") return "text-success bg-success/15";
  if (stance === "谨慎参与") return "text-warning bg-warning/15";
  if (stance === "回避") return "text-danger bg-danger/15";
  return "text-muted-foreground bg-muted";
}

export function DeepDive() {
  const [data, setData] = useState<DeepDiveData | null>(null);
  const [stock, setStock] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [msg, setMsg] = useState("");
  // 同 AgentReview：防重入 / 卸载停轮询 / 只认最后一次响应
  const polling = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);
  const reqId = useRef(0);

  // ⚠️ alive 必须在**挂载时置回 true**：React 18 StrictMode 开发下会 mount→unmount→mount，
  // 只在 cleanup 里置 false 的话第二次挂载后它永远是 false，所有响应都被当"已卸载"丢弃
  // （表现＝接口 200 但页面空白）。
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  async function loadLatest() {
    const my = ++reqId.current;
    try {
      const d = await agentFetch<DeepDiveData>("/api/deepdive/latest");
      if (!alive.current || my !== reqId.current) return;   // 已卸载 / 有更新的请求 → 丢弃
      if (d && d.code) setData(d);
    } catch {
      if (alive.current && my === reqId.current) setMsg("读取上次深挖失败，仍可重新深挖");
    }
  }
  useEffect(() => { loadLatest(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  function stopPolling() {
    polling.current = false;
    if (alive.current) setRunning(false);
  }

  async function pollOnce() {
    if (!alive.current) return;
    try {
      const st = await agentFetch<JobStatus>("/api/deepdive/status");
      if (!alive.current) return;
      setElapsed(st.elapsed || 0);
      if (st.running) { timer.current = setTimeout(pollOnce, 3000); return; }
      stopPolling();
      if (st.error) setMsg("出错：" + st.error); else loadLatest();
    } catch { stopPolling(); if (alive.current) setMsg("状态查询失败"); }
  }

  async function deepdive() {
    const s = stock.trim();
    if (!s) { setMsg("请输入代码或简称"); return; }
    if (running || polling.current) return;   // ⚠️ 光看 state 挡不住极快双击
    polling.current = true;
    setRunning(true); setMsg(""); setElapsed(0);
    try {
      const resp = await agentFetch<JobStatus>(`/api/deepdive/run?stock=${encodeURIComponent(s)}`, "POST");
      if (resp.busy) { stopPolling(); if (alive.current) setMsg(`正在深挖 ${resp.stock}，请稍后再试`); return; }
    } catch { stopPolling(); if (alive.current) setMsg("启动失败"); return; }
    pollOnce();
  }

  const v = data?.verdict;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold"><Microscope className="h-6 w-6 text-primary" /> 个股深挖</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            4 分析师 + 参与⚔回避辩论 → 深挖结论
            {data && ` · ${data.name}（${data.code}）· 生成于 ${data.generated_at}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input value={stock} onChange={(e) => setStock(e.target.value)} onKeyDown={(e) => e.key === "Enter" && deepdive()}
            placeholder="代码或简称，如 立新能源 / 001258"
            className="w-56 rounded-lg border border-border bg-card px-3 py-2 text-sm" />
          <button onClick={deepdive} disabled={running}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50">
            {running && <Loader2 className="h-4 w-4 animate-spin" />}
            {running ? `深挖中 ${elapsed}s` : "深挖"}
          </button>
        </div>
      </div>

      {msg && <div className="glass rounded-xl px-4 py-3 text-sm text-muted-foreground">{msg}</div>}

      {!data && !running && (
        <div className="glass rounded-2xl py-16 text-center text-muted-foreground">
          输入一只票，点「深挖」。<div className="mt-1 text-xs">4 分析师 + 多空辩论，约 2-3 分钟</div>
        </div>
      )}

      {v && (
        <section>
          <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.2em] text-primary">深挖结论 · Verdict</div>
          <div className="glass rounded-2xl p-6 shadow-glow">
            <div className="mb-3 flex flex-wrap items-center gap-4">
              {v.stance && (
                <span className={cn("rounded-full px-4 py-1.5 text-base font-extrabold tracking-wider", stanceTone(v.stance))}>{v.stance}</span>
              )}
              <span className="flex-1 text-lg font-semibold">{v.one_liner}</span>
            </div>
            <div className="my-4 grid gap-3.5 sm:grid-cols-3">
              {([["题材", v.theme], ["资金", v.capital], ["技术", v.technical]] as const).map(([k, val]) => (
                <div key={k} className="border-l-2 border-border pl-3 text-sm">
                  <div className="mb-0.5 text-xs font-semibold uppercase tracking-wider text-primary">{k}</div>{val}
                </div>
              ))}
            </div>
            <div className="grid gap-5 md:grid-cols-2">
              {safeArray<string>(v.watch_points).length > 0 && (
                <div>
                  <h4 className="mb-1.5 text-sm font-bold">🎯 关注点</h4>
                  <ul className="ml-4 list-disc space-y-1 text-[13px] text-muted-foreground">
                    {safeArray<string>(v.watch_points).map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}
              <div>
                <h4 className="mb-1.5 text-sm font-bold text-danger">⚠ 风险</h4>
                <ul className="ml-4 list-disc space-y-1 text-[13px] text-muted-foreground">
                  {safeArray<string>(v.risks).length
                    ? safeArray<string>(v.risks).map((r, i) => <li key={i}>{r}</li>)
                    : <li className="list-none text-muted-foreground/60">暂无结构化风险项</li>}
                </ul>
              </div>
            </div>
            <div className="mt-4 border-t border-border pt-3">
              <h4 className="mb-1 text-sm font-bold">⚔ 多空辩论</h4>
              <p className="text-[13px] text-muted-foreground">{v.debate_takeaway}</p>
            </div>
          </div>
        </section>
      )}

      {data?.reports && (
        <section>
          <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.2em] text-primary">四维分析 · Analysts</div>
          <div className="grid gap-4 md:grid-cols-2">
            {([["题材归属", "theme"], ["资金流向", "capital"], ["技术形态", "technical"], ["风险排查", "risk"]] as const).map(([t, k]) => (
              <div key={k} className="glass rounded-2xl p-5">
                <span className="mb-2 inline-block rounded bg-muted px-2 py-0.5 text-xs font-bold text-foreground/80">{t}</span>
                <div className="prose prose-sm max-w-none text-[13px]" dangerouslySetInnerHTML={{ __html: data.reports![k] || "<p>—</p>" }} />
              </div>
            ))}
          </div>
        </section>
      )}

      {data?.debate && (data.debate.join || data.debate.avoid) && (
        <section>
          <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.2em] text-primary">多空辩论 · Debate</div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-success/30 bg-success/5 p-5">
              <div className="mb-2 font-extrabold text-success">▲ 参与派</div>
              <div className="prose prose-sm max-w-none text-[13px]" dangerouslySetInnerHTML={{ __html: data.debate.join || "<p>—</p>" }} />
            </div>
            <div className="rounded-2xl border border-danger/30 bg-danger/5 p-5">
              <div className="mb-2 font-extrabold text-danger">▼ 回避派</div>
              <div className="prose prose-sm max-w-none text-[13px]" dangerouslySetInnerHTML={{ __html: data.debate.avoid || "<p>—</p>" }} />
            </div>
          </div>
        </section>
      )}

      {data && (
        <AgentChat
          // 换标的即重建组件，别把上一只票的问答串进新上下文
          key={data.code}
          endpoint="/api/deepdive/chat"
          placeholder={`就 ${data.name || "这只票"} 追问，如：今天的资金和题材说明什么`}
          suggestions={["今天的量能和换手说明什么", "技术位置处在什么区间", "和同板块其他涨停股比资金强度如何", "这类票历史上涨停后的表现统计"]}
        />
      )}

      {data && <p className="border-t border-border pt-4 text-xs text-muted-foreground/70"><Target className="mr-1 inline h-3 w-3" /> {DISCLAIMER}</p>}
    </div>
  );
}
