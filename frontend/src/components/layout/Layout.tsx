import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  Moon, Sun, ChevronsLeft, ChevronsRight, CandlestickChart, Cog, Swords, Menu, X,
  Activity, Flame, CalendarRange, Github, Bot, NotebookPen, TrendingDown,
  Microscope, Sunrise, Eye, Briefcase, Star, LineChart, Radio } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

function XLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z" />
    </svg>
  );
}
import { useDarkMode } from "@/hooks/useDarkMode";

const APP_VERSION = "v0.2.0";
const REPO_URL = "https://github.com/simonlin1212/Vibe-Astock";
// 作者联系方式只留 X。
const X_URL = "https://x.com/linsizhen";
const X_HANDLE = "@linsizhen";
const AUTHOR = "Simon 林";

// 产品主体 = 复盘看板：打开就看清今天的短线情绪。
// 复盘看板本身由 agent 驱动（带 🤖 角标），其余是它的分项数据。
const REVIEW_NAV = [
  { to: "/agent/review", icon: Swords, label: "复盘看板", agent: true },
  { to: "/daily-review", icon: Activity, label: "盘面数据" },
  { to: "/first-board", icon: Flame, label: "首板分析" },
  { to: "/heat", icon: CalendarRange, label: "近5天热度" },
  { to: "/backtest", icon: TrendingDown, label: "涨停样本统计" },
];

// 个人交易记录。⛔ 这一组的数据只在本机流动，不接入任何 AI prompt。
const JOURNAL_NAV = [
  { to: "/journal", icon: NotebookPen, label: "交易日志" },
];

// 盯盘与自选：看当下与自己关心的标的
const WATCH_NAV = [
  { to: "/watch", icon: Eye, label: "盯盘" },
  { to: "/portfolio", icon: Briefcase, label: "持仓股" },
  { to: "/watchlist", icon: Star, label: "自选股" },
  { to: "/stock-data", icon: LineChart, label: "个股数据" },
  { to: "/intel", icon: Radio, label: "资讯雷达" },
];

// 按需跑的单股 agent（与每日复盘不同：它是你点一次跑一次）
const AGENT_NAV = [
  { to: "/agent/intraday", icon: Sunrise, label: "盘中核验" },
  { to: "/agent/deepdive", icon: Microscope, label: "个股深挖", agent: true },
];

const SETTINGS_NAV = [{ to: "/settings", icon: Cog, label: "接入 AI" }];

export function Layout() {
  const { pathname } = useLocation();
  const { dark, toggle } = useDarkMode();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("va-sidebar") === "collapsed");
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("va-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  const item = ({ to, icon: Icon, label }: { to: string; icon: LucideIcon; label: string }, agent = false) => {
    const active = pathname === to;
    return (
      <Link
        key={to}
        to={to}
        title={collapsed ? label : undefined}
        className={cn(
          "flex items-center rounded-lg text-sm transition-colors",
          collapsed ? "justify-center p-2.5" : "gap-2.5 px-3 py-2.5",
          active
            ? "bg-primary/15 font-medium text-primary shadow-glow"
            : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
        )}
      >
        {agent ? (
          <span className="relative flex shrink-0">
            <Icon className="h-4 w-4" />
            <Bot className="absolute -right-1.5 -top-1.5 h-2.5 w-2.5 rounded-full bg-background text-primary" />
          </span>
        ) : (
          <Icon className="h-4 w-4 shrink-0" />
        )}
        {!collapsed && label}
      </Link>
    );
  };

  const groupLabel = (text: string) =>
    !collapsed && (
      <div className="mb-1 mt-3 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/60 first:mt-0">{text}</div>
    );

  const mobileGroup = (label: string, links: Array<{ to: string; icon: LucideIcon; label: string; agent?: boolean }>) => (
    <section key={label} className="space-y-1">
      <p className="px-3 pt-3 text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/60">{label}</p>
      {links.map(({ to, icon: Icon, label: linkLabel, agent }) => {
        const active = pathname === to;
        return (
          <Link key={to} to={to} onClick={() => setMobileOpen(false)}
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm transition-colors",
              active ? "bg-primary/15 font-medium text-primary shadow-glow" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}>
            <Icon className="h-4 w-4 shrink-0" />
            <span>{linkLabel}</span>
            {agent && <Bot className="ml-auto h-3 w-3 text-primary" />}
          </Link>
        );
      })}
    </section>
  );

  return (
    <div className="min-h-dvh md:flex">
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-border/60 bg-background/90 px-4 py-3 backdrop-blur md:hidden">
        <Link to="/agent/review" className="flex items-center gap-2" aria-label="Vibe-Astock 首页">
          <CandlestickChart className="h-5 w-5 text-primary text-glow" />
          <span className="font-extrabold tracking-tight">Vibe-<span className="text-primary">Astock</span></span>
        </Link>
        <button type="button" onClick={() => setMobileOpen(true)} className="rounded-lg p-2 text-muted-foreground hover:bg-muted/60 hover:text-foreground" aria-label="打开导航菜单">
          <Menu className="h-5 w-5" />
        </button>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="导航菜单">
          <button type="button" className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} aria-label="关闭导航菜单" />
          <aside className="relative flex h-full w-[min(19rem,84vw)] flex-col border-r border-border/60 bg-background shadow-2xl">
            <div className="flex items-center justify-between border-b border-border/60 p-4">
              <span className="flex items-center gap-2 font-extrabold tracking-tight"><CandlestickChart className="h-5 w-5 text-primary" />Vibe-<span className="text-primary">Astock</span></span>
              <button type="button" onClick={() => setMobileOpen(false)} className="rounded-lg p-2 text-muted-foreground hover:bg-muted/60 hover:text-foreground" aria-label="关闭导航菜单"><X className="h-5 w-5" /></button>
            </div>
            <nav className="flex-1 overflow-y-auto px-3 py-2">
              {mobileGroup("复盘", REVIEW_NAV)}
              {mobileGroup("盯盘与自选", WATCH_NAV)}
              {mobileGroup("按需分析", AGENT_NAV)}
              {mobileGroup("我的交易", JOURNAL_NAV)}
              {mobileGroup("设置", SETTINGS_NAV)}
            </nav>
            <div className="flex items-center justify-between border-t border-border/60 p-4">
              <button onClick={toggle} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
                {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}{dark ? "亮色" : "暗色"}
              </button>
              <span className="text-[11px] text-muted-foreground/60">{APP_VERSION}</span>
            </div>
          </aside>
        </div>
      )}

      {/* Sidebar */}
      <aside className={cn(
        "glass z-10 m-2 hidden h-[calc(100dvh-1rem)] shrink-0 flex-col rounded-2xl transition-all duration-200 md:flex",
        collapsed ? "w-14" : "w-60",
      )}>
        {/* Brand */}
        <div className={cn("border-b border-border/50", collapsed ? "flex justify-center p-3" : "p-4")}>
          <Link to="/agent/review" className={cn("flex items-center", collapsed ? "justify-center" : "gap-2")}>
            <CandlestickChart className="h-6 w-6 shrink-0 text-primary text-glow" />
            {!collapsed && <span className="text-lg font-extrabold tracking-tight">Vibe-<span className="text-primary">Astock</span></span>}
          </Link>
          {}
          {!collapsed && <p className="mt-1 text-[11px] text-muted-foreground">A 股短线复盘</p>}
        </div>

        {/* Nav */}
        <nav className={cn("flex-1 space-y-0.5 overflow-auto", collapsed ? "p-1.5" : "p-2.5")}>
          {groupLabel("复盘")}
          {REVIEW_NAV.map((n) => item(n, "agent" in n && n.agent))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("盯盘与自选")}
          {WATCH_NAV.map((n) => item(n))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("按需分析")}
          {AGENT_NAV.map((n) => item(n, "agent" in n && n.agent))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {groupLabel("我的交易")}
          {JOURNAL_NAV.map((n) => item(n))}

          {!collapsed && <div className="my-2 border-t border-border/40" />}
          {SETTINGS_NAV.map((n) => item(n))}
        </nav>

        {/* Footer */}
        <div className={cn("border-t border-border/50", collapsed ? "flex flex-col items-center gap-2 p-2" : "space-y-2 p-3")}>
          {collapsed ? (
            <>
              <button onClick={toggle} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title={dark ? "亮色" : "暗色"}>
                {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
              <a href={X_URL} target="_blank" rel="noreferrer" className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title={`作者 ${AUTHOR} · X ${X_HANDLE}`}>
                <XLogo className="h-3.5 w-3.5" />
              </a>
              <button onClick={() => setCollapsed(false)} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title="展开">
                <ChevronsRight className="h-4 w-4" />
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <button onClick={toggle} className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground">
                  {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                  {dark ? "亮色" : "暗色"}
                </button>
                <div className="flex items-center gap-2">
                  <a href={X_URL} target="_blank" rel="noreferrer" className="text-muted-foreground transition-colors hover:text-foreground" title={`作者 ${AUTHOR} · X ${X_HANDLE}`}>
                    <XLogo className="h-3 w-3" />
                  </a>
                  <a href={REPO_URL} target="_blank" rel="noreferrer" className="text-muted-foreground transition-colors hover:text-foreground" title="GitHub">
                    <Github className="h-3.5 w-3.5" />
                  </a>
                  <button onClick={() => setCollapsed(true)} className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground" title="收起">
                    <ChevronsLeft className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground/70">
                作者：{AUTHOR} ·{" "}
                <a href={X_URL} target="_blank" rel="noreferrer"
                  className="text-primary/80 transition-colors hover:text-primary">
                  X {X_HANDLE}
                </a>
              </p>
              <p className="text-[11px] leading-relaxed text-muted-foreground/60">{APP_VERSION} · AI 生成 · 仅供参考 · 非投资建议</p>
            </>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="min-w-0 flex-1 md:h-screen md:overflow-auto">
        <div className="mx-auto max-w-6xl px-3 py-4 sm:px-6 sm:py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
