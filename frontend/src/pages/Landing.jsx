import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Activity, BarChart3, ChevronRight, Database, FileText,
  Shield, Zap, Check, ArrowRight, Eye,
} from 'lucide-react'
import { BrandMark, ThemeToggle } from '../components/app-ui'
import { workspaceUrl } from '@/lib/subdomain'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

/* ─────────────────────────── Scroll-reveal hook ─────────────────────── */
function useReveal() {
  const ref = useRef(null)
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true) },
      { threshold: 0.1 },
    )
    if (ref.current) obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])
  return [ref, visible]
}

/* ─────────────────────────── FAQ accordion ──────────────────────────── */
function FaqItem({ question, answer }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="py-4">
      <button
        className="flex w-full items-center justify-between gap-4 text-left text-sm font-medium hover:text-primary transition-colors"
        onClick={() => setOpen(prev => !prev)}
        type="button"
      >
        {question}
        <ChevronRight className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{answer}</p>
      )}
    </div>
  )
}

/* ─────────────────────── Product mockup components ──────────────────── */

function MockupShell({ sidebarSlot, mainSlot }) {
  return (
    <div className="rounded-xl overflow-hidden border shadow-2xl flex h-[420px] bg-background text-foreground text-xs select-none">
      {/* Sidebar */}
      <div className="w-44 shrink-0 bg-[#0f172a] flex flex-col py-4 gap-1">
        <div className="px-4 mb-3">
          <div className="flex items-center gap-1.5">
            <div className="size-5 rounded bg-blue-500 flex items-center justify-center">
              <Eye className="size-3 text-white" />
            </div>
            <span className="text-white text-xs font-bold">Panopta</span>
          </div>
        </div>
        {sidebarSlot}
      </div>
      {/* Main */}
      <div className="flex-1 overflow-hidden bg-background p-4 flex flex-col gap-3">
        {mainSlot}
      </div>
    </div>
  )
}

function SidebarItem({ label, active }) {
  return (
    <div className={cn(
      'mx-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-[11px] font-medium cursor-pointer',
      active ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white',
    )}>
      {label}
    </div>
  )
}

function DefaultSidebar({ active }) {
  return (
    <div className="flex flex-col gap-0.5">
      {['Overview', 'Tables', 'Incidents', 'Reports', 'Teams', 'Settings'].map(l => (
        <SidebarItem key={l} label={l} active={active === l} />
      ))}
    </div>
  )
}

/* Mockup 1 — Dashboard */
function DashboardMockup() {
  return (
    <MockupShell
      sidebarSlot={<DefaultSidebar active="Overview" />}
      mainSlot={
        <div className="flex flex-col gap-3 h-full">
          <div>
            <h2 className="text-sm font-bold">Overview</h2>
            <p className="text-[10px] text-muted-foreground">3 monitored tables · 4 open incidents</p>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: 'Health Score', value: '27', color: 'text-red-500' },
              { label: 'Open incidents', value: '4', color: 'text-amber-500' },
              { label: 'Tables', value: '3', color: 'text-foreground' },
              { label: 'Sources', value: '2', color: 'text-foreground' },
            ].map(s => (
              <div key={s.label} className="rounded-lg border bg-card p-2">
                <div className={`text-lg font-black ${s.color}`}>{s.value}</div>
                <div className="text-[9px] text-muted-foreground leading-tight">{s.label}</div>
              </div>
            ))}
          </div>
          <div className="rounded-lg border bg-card p-2 flex-1">
            <p className="text-[10px] font-semibold mb-2 text-muted-foreground uppercase tracking-wide">Active incidents</p>
            <div className="flex flex-col gap-1.5">
              {[
                { sev: 'P1', label: 'orders.payment_status — null rate spike', color: 'bg-red-500/15 border-red-500/30 text-red-500' },
                { sev: 'P2', label: 'users.email — cardinality drop (-34%)', color: 'bg-amber-500/15 border-amber-500/30 text-amber-600' },
                { sev: 'P2', label: 'events.created_at — freshness breach', color: 'bg-amber-500/15 border-amber-500/30 text-amber-600' },
                { sev: 'P3', label: 'products.sku — schema drift detected', color: 'bg-blue-500/15 border-blue-500/30 text-blue-500' },
              ].map((inc, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold ${inc.color}`}>{inc.sev}</span>
                  <span className="text-[10px] truncate">{inc.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      }
    />
  )
}

/* Mockup 2 — Incident Analysis */
function IncidentMockup() {
  return (
    <MockupShell
      sidebarSlot={<DefaultSidebar active="Incidents" />}
      mainSlot={
        <div className="flex flex-col gap-3 h-full overflow-hidden">
          <div className="flex items-center gap-2">
            <span className="rounded border border-red-500/30 bg-red-500/15 px-1.5 py-0.5 text-[9px] font-bold text-red-500">P1</span>
            <span className="text-[11px] font-semibold truncate">orders.payment_status — null rate spike (0.8% → 18.4%)</span>
          </div>
          <div className="rounded-lg border bg-blue-500/5 border-blue-500/20 p-2.5">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[9px] font-bold text-blue-500 uppercase tracking-wide">AI Analysis</span>
              <span className="rounded-full bg-green-500/15 border border-green-500/30 px-1.5 py-0.5 text-[9px] text-green-600 font-semibold">High Confidence</span>
            </div>
            <p className="text-[10px] text-muted-foreground leading-relaxed">
              The orders table had a 37% increase in null payment_status values. ~24,000 rows affected. Issue started around 10:15 following a checkout integration change.
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wide">Likely causes</p>
            {[
              { label: 'Failed payment webhook mapping', prob: 'High', color: 'bg-red-500/15 text-red-500 border-red-500/30' },
              { label: 'Checkout integration deployment', prob: 'Medium', color: 'bg-amber-500/15 text-amber-600 border-amber-500/30' },
              { label: 'Schema migration side-effect', prob: 'Low', color: 'bg-slate-500/15 text-slate-500 border-slate-500/30' },
            ].map((c, i) => (
              <div key={i} className="flex items-center justify-between rounded border bg-card px-2 py-1">
                <span className="text-[10px]">{c.label}</span>
                <span className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${c.color}`}>{c.prob}</span>
              </div>
            ))}
          </div>
          <div className="rounded-lg border bg-card p-2 flex items-center justify-between mt-auto">
            <div>
              <p className="text-[9px] text-muted-foreground">Assigned team</p>
              <p className="text-[10px] font-semibold">Data Engineering</p>
            </div>
            <div className="text-right">
              <p className="text-[9px] text-muted-foreground">Assignee</p>
              <p className="text-[10px] font-semibold">Mounir</p>
            </div>
          </div>
        </div>
      }
    />
  )
}

/* Mockup 3 — Teams & On-call */
function TeamsMockup() {
  return (
    <MockupShell
      sidebarSlot={<DefaultSidebar active="Teams" />}
      mainSlot={
        <div className="flex flex-col gap-3 h-full">
          <div>
            <h2 className="text-sm font-bold">Teams</h2>
            <p className="text-[10px] text-muted-foreground">Manage on-call rotation and assignments</p>
          </div>
          <div className="flex flex-col gap-1.5">
            {[
              { name: 'Data Engineering', dot: 'bg-blue-500', members: '2 members', oncall: 'Alice Chen on-call', open: true },
              { name: 'Analytics', dot: 'bg-green-500', members: '1 member', oncall: '' },
              { name: 'Platform', dot: 'bg-purple-500', members: '1 member', oncall: '' },
            ].map((t, i) => (
              <div key={i} className={cn('rounded-lg border p-2 bg-card', t.open && 'border-blue-500/30')}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`size-1.5 rounded-full ${t.dot}`} />
                    <span className="text-[11px] font-semibold">{t.name}</span>
                  </div>
                  <span className="text-[9px] text-muted-foreground">{t.members}</span>
                </div>
                {t.oncall && <p className="text-[9px] text-blue-500 mt-1 ml-3.5">{t.oncall}</p>}
              </div>
            ))}
          </div>
          <div className="rounded-lg border bg-card p-2 flex-1">
            <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">On-call schedule</p>
            <div className="flex gap-1 items-end h-12">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, i) => (
                <div key={d} className="flex-1 flex flex-col items-center gap-1">
                  <div className={cn('w-full rounded-sm', i < 3 ? 'h-8 bg-blue-500/40' : i < 5 ? 'h-6 bg-green-500/40' : 'h-4 bg-slate-400/30')} />
                  <span className="text-[8px] text-muted-foreground">{d}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      }
    />
  )
}

/* Mockup 4 — Reports */
function ReportsMockup() {
  const sparkHeights = [30, 45, 35, 60, 50, 40, 55, 70, 48, 65, 55, 80, 72, 90]
  return (
    <MockupShell
      sidebarSlot={<DefaultSidebar active="Reports" />}
      mainSlot={
        <div className="flex flex-col gap-3 h-full">
          <div>
            <h2 className="text-sm font-bold">Reports</h2>
            <p className="text-[10px] text-muted-foreground">Weekly reliability report</p>
          </div>
          <div className="rounded-lg border bg-card p-2.5">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-semibold">Health score trend</p>
              <span className="text-[10px] font-black text-green-500">92/100</span>
            </div>
            <div className="flex items-end gap-0.5 h-10">
              {sparkHeights.map((h, i) => (
                <div key={i} className="flex-1 rounded-sm bg-blue-500/60" style={{ height: `${h}%` }} />
              ))}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Incidents', value: '11' },
              { label: 'Resolved', value: '8' },
              { label: 'Uptime SLA', value: '98.4%' },
            ].map(s => (
              <div key={s.label} className="rounded-lg border bg-card p-2 text-center">
                <div className="text-base font-black">{s.value}</div>
                <div className="text-[9px] text-muted-foreground">{s.label}</div>
              </div>
            ))}
          </div>
          <div className="rounded-lg border bg-card p-2 flex-1">
            <p className="text-[9px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Recent incidents</p>
            <div className="flex flex-col gap-1">
              {[
                { sev: 'P1', table: 'orders.payment_status', status: 'Resolved', statusColor: 'text-green-500' },
                { sev: 'P2', table: 'users.email', status: 'Resolved', statusColor: 'text-green-500' },
                { sev: 'P3', table: 'products.sku', status: 'Open', statusColor: 'text-amber-500' },
              ].map((r, i) => (
                <div key={i} className="flex items-center justify-between border-b border-border/50 pb-1 last:border-0 last:pb-0">
                  <div className="flex items-center gap-1.5">
                    <span className={cn(
                      'rounded border px-1 py-0.5 text-[8px] font-bold',
                      r.sev === 'P1' ? 'border-red-500/30 bg-red-500/15 text-red-500'
                        : r.sev === 'P2' ? 'border-amber-500/30 bg-amber-500/15 text-amber-600'
                        : 'border-blue-500/30 bg-blue-500/15 text-blue-500',
                    )}>{r.sev}</span>
                    <span className="text-[10px] truncate max-w-[100px]">{r.table}</span>
                  </div>
                  <span className={`text-[9px] font-semibold ${r.statusColor}`}>{r.status}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      }
    />
  )
}

/* ─────────────────────────── Static data ────────────────────────────── */

const FEATURES = [
  {
    icon: Database,
    title: 'Every database you use',
    desc: 'PostgreSQL, MySQL, MongoDB, ClickHouse, SQL Server, BigQuery, Snowflake, Redshift — operational databases and warehouses in one place.',
  },
  {
    icon: Activity,
    title: 'AI explains every incident',
    desc: 'Not just "null spike detected." Panopta tells you what happened, why it likely happened, the business impact, and the exact debug query to run.',
  },
  {
    icon: BarChart3,
    title: 'Deep column profiling',
    desc: 'Null rates, cardinality, percentiles (p25/p50/p75/p95), top values, schema fingerprints, freshness — captured on every run, automatically.',
  },
  {
    icon: Zap,
    title: '7-method anomaly detection',
    desc: 'Z-Score, Isolation Forest, STL seasonal decomposition, cardinality drop, row growth rate, enum drift, and rule-based checks — nothing slips through.',
  },
  {
    icon: FileText,
    title: 'Client-ready reports',
    desc: 'Generate weekly reliability reports, executive summaries, and client-safe incident reports automatically. Agencies: white-label with your branding.',
  },
  {
    icon: Shield,
    title: 'Safe by design',
    desc: 'Read-only credentials. HKDF per-tenant encryption. Panopta cannot modify your data. Query timeouts protect production databases.',
  },
]

const PLANS = [
  {
    name: 'Free',
    price: '$0',
    period: 'forever',
    highlight: false,
    features: ['1 data source', 'Up to 5 tables', '7-day history', 'Email alerts', 'Basic monitors'],
  },
  {
    name: 'Starter',
    price: '$49',
    period: 'per month',
    highlight: false,
    features: ['3 data sources', 'Up to 50 tables', '90-day history', 'Slack + webhook', 'AI incident summaries'],
  },
  {
    name: 'Growth',
    price: '$149',
    period: 'per month',
    highlight: true,
    badge: 'Most popular',
    features: ['Unlimited sources', 'Unlimited tables', '1-year history', 'All alert channels', 'AI monitor recommender', 'Weekly PDF reports', '5 members'],
  },
  {
    name: 'Agency',
    price: '$299',
    period: 'per month',
    highlight: false,
    badge: 'For consultants',
    features: ['Everything in Growth', 'Multi-client workspaces', 'Client viewer role', 'White-label reports', 'Auto-scheduled delivery', '15 members'],
  },
]

const CONNECTORS = [
  { name: 'PostgreSQL', tier: 1 },
  { name: 'MySQL', tier: 1 },
  { name: 'MongoDB', tier: 1 },
  { name: 'ClickHouse', tier: 2 },
  { name: 'SQL Server', tier: 2 },
  { name: 'BigQuery', tier: 2 },
  { name: 'Snowflake', tier: 2 },
  { name: 'Redshift', tier: 2 },
  { name: 'Databricks', tier: 2 },
  { name: 'Trino', tier: 2 },
  { name: 'DuckDB', tier: 2 },
  { name: 'SQLite', tier: 2 },
]

const HOW_IT_WORKS = [
  { n: '01', title: 'Connect your database', desc: 'Paste read-only credentials. Panopta scans your schema in seconds.' },
  { n: '02', title: 'AI recommends monitors', desc: 'Panopta reads your tables and proposes monitors: freshness, nulls, duplicates, schema drift, business rules.' },
  { n: '03', title: 'Incidents with AI context', desc: 'When something breaks, get an AI-written report — what happened, why, the business impact, debug queries.' },
  { n: '04', title: 'Reports sent automatically', desc: 'Weekly reliability reports go to your team. Client-safe summaries go to your clients. You stay ahead.' },
]

const COMPARISON = [
  { name: 'Monte Carlo', price: '$1,000–5,000+/mo', note: 'Enterprise only, 3-6 month setup' },
  { name: 'Soda', price: '$400–1,000/mo', note: 'Warehouse-first, no app databases' },
  { name: 'Elementary', price: '$200+/mo', note: 'dbt-only, no MongoDB, no app DBs' },
  { name: 'Panopta', price: 'From $49/mo', note: 'Operational + warehouse, AI-first, 10-min setup', highlight: true },
]

const PANOPTES_QUOTES = [
  {
    quote: "Nothing escapes the gaze of a hundred eyes.",
    context: "Panoptes, the all-seeing giant of Greek mythology, never slept — at least one eye was always open. Your data deserves the same vigilance.",
  },
  {
    quote: "While some eyes rest, others watch.",
    context: "Panoptes never missed a thing. Panopta runs every check, on every table, on every schedule — so nothing silently breaks while you sleep.",
  },
  {
    quote: "All-seeing. Always-on. Instantly explainable.",
    context: "Named for the giant who watched Io for Zeus, Panopta watches your data with the same tireless attention — then tells you exactly what it saw.",
  },
]

const SHOWCASE_TABS = ['Dashboard', 'Incident Analysis', 'Teams & On-call', 'Reports']
const SHOWCASE_MOCKUPS = [DashboardMockup, IncidentMockup, TeamsMockup, ReportsMockup]

/* ─────────────────────────── Main component ─────────────────────────── */

export default function Landing() {
  const nav = useNavigate()
  const [workspaceInput, setWorkspaceInput] = useState('')

  /* Product showcase */
  const [activeTab, setActiveTab] = useState(0)
  const pauseUntilRef = useRef(0)

  /* Auto-rotate every 4 s, respecting manual pause */
  useEffect(() => {
    const timer = setInterval(() => {
      if (Date.now() < pauseUntilRef.current) return
      setActiveTab(t => (t + 1) % 4)
    }, 4000)
    return () => clearInterval(timer)
  }, [])

  const handleTabClick = (i) => {
    setActiveTab(i)
    pauseUntilRef.current = Date.now() + 10000
  }

  /* Reveal refs */
  const [heroStatsRef, heroStatsVisible] = useReveal()
  const [featuresRef, featuresVisible] = useReveal()
  const [showcaseRef, showcaseVisible] = useReveal()
  const [pricingRef, pricingVisible] = useReveal()

  const goToWorkspace = () => {
    const slug = workspaceInput.trim().toLowerCase().replace(/[^a-z0-9-]/g, '')
    if (!slug) return
    window.location.href = workspaceUrl(slug)
  }

  const scrollToWorkspace = () => {
    document.getElementById('workspace-input')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setTimeout(() => document.getElementById('workspace-input')?.focus(), 400)
  }

  const ActiveMockup = SHOWCASE_MOCKUPS[activeTab]

  return (
    <div className="min-h-screen bg-background text-foreground">

      {/* ── Nav ── */}
      <header className="sticky top-0 z-50 border-b backdrop-blur-sm bg-background/90">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <BrandMark />
          <nav className="hidden items-center gap-6 text-sm md:flex">
            <a href="#how-it-works" className="text-muted-foreground hover:text-foreground transition-colors">How it works</a>
            <a href="#features" className="text-muted-foreground hover:text-foreground transition-colors">Features</a>
            <a href="#connectors" className="text-muted-foreground hover:text-foreground transition-colors">Connectors</a>
            <a href="#pricing" className="text-muted-foreground hover:text-foreground transition-colors">Pricing</a>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="outline" size="sm" onClick={scrollToWorkspace}>Sign in</Button>
            <Button size="sm" onClick={() => nav('/register')}>Start for free</Button>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative overflow-hidden border-b">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,hsl(var(--primary)/0.10),transparent_60%)]" />
        <div
          className="absolute inset-0 opacity-30"
          style={{
            background: 'radial-gradient(ellipse at 80% 20%, hsl(var(--primary)/0.12), transparent 50%)',
            animation: 'pulse 6s ease-in-out infinite',
          }}
        />
        <div className="relative mx-auto max-w-6xl px-4 py-24 text-center">
          <Badge variant="secondary" className="mb-6 gap-1.5">
            <Eye className="size-3" />
            Open Beta — Free to start
          </Badge>

          <h1 className="mx-auto max-w-4xl text-4xl font-extrabold tracking-tight sm:text-6xl leading-tight">
            Stop discovering data quality issues{' '}
            <span className="text-primary">from your users.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed">
            Panopta detects anomalies across your data warehouse before they reach production — and explains them in plain English.
          </p>

          <p className="mx-auto mt-4 max-w-xl text-sm text-muted-foreground italic">
            "Nothing escapes the gaze of a hundred eyes." — Named for Panoptes, the all-seeing giant of Greek mythology.
          </p>

          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Button size="lg" className="gap-2 font-semibold px-8" onClick={() => nav('/register')}>
              Start for free
              <ArrowRight className="size-4" />
            </Button>
            <Button size="lg" variant="outline" className="gap-2" onClick={() => document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' })}>
              See how it works
            </Button>
          </div>

          {/* Social proof strip */}
          <div
            ref={heroStatsRef}
            className={cn(
              'mt-10 inline-flex items-center gap-4 rounded-full border bg-card px-6 py-2.5 text-sm text-muted-foreground transition-all duration-700',
              heroStatsVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4',
            )}
          >
            <span>Monitoring <strong className="text-foreground">347 tables</strong></span>
            <span className="text-border">·</span>
            <span><strong className="text-foreground">12 workspaces</strong></span>
            <span className="text-border">·</span>
            <span><strong className="text-green-500">98.4% uptime SLA</strong></span>
          </div>

          {/* Workspace jump */}
          <div id="workspace-input" className="mt-10 flex items-center justify-center mx-auto max-w-sm overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="flex items-center pl-4 text-sm text-muted-foreground select-none whitespace-nowrap">
              <span>panopta.app /</span>
            </div>
            <input
              className="flex-1 bg-transparent px-2 py-3 text-sm outline-none font-mono"
              placeholder="your-workspace"
              value={workspaceInput}
              onChange={(e) => setWorkspaceInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && goToWorkspace()}
            />
            <Button variant="ghost" className="rounded-none border-l h-full px-4" onClick={goToWorkspace}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-2 text-center">
            Already have a workspace?{' '}
            <span className="text-foreground">Enter your slug above to sign in.</span>
            {' · '}
            <Link to="/register" className="text-primary hover:underline">Create a new workspace →</Link>
          </p>
        </div>
      </section>

      {/* ── Comparison strip ── */}
      <section className="border-b py-8 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4">
          <p className="mb-5 text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Monte Carlo-quality detection. A fraction of the price.
          </p>
          <div className="grid gap-3 sm:grid-cols-4">
            {COMPARISON.map((c) => (
              <div key={c.name} className={`rounded-xl border p-4 text-center ${c.highlight ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/20' : 'bg-card'}`}>
                <div className={`font-semibold text-sm ${c.highlight ? 'text-primary' : ''}`}>{c.name}</div>
                <div className={`mt-1 text-lg font-black ${c.highlight ? '' : 'text-muted-foreground'}`}>{c.price}</div>
                <div className="mt-1 text-xs text-muted-foreground">{c.note}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Panoptes mythology callout ── */}
      <section className="border-b py-16 bg-primary/5">
        <div className="mx-auto max-w-4xl px-4">
          <div className="text-center mb-10">
            <div className="inline-flex size-14 items-center justify-center rounded-full bg-primary/10 mb-4">
              <Eye className="size-7 text-primary" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight">The myth behind the name</h2>
          </div>
          <div className="grid gap-5 sm:grid-cols-3">
            {PANOPTES_QUOTES.map((q, i) => (
              <div key={i} className="rounded-xl border bg-card p-5 flex flex-col gap-3">
                <blockquote className="text-base font-semibold text-foreground leading-snug">
                  "{q.quote}"
                </blockquote>
                <p className="text-sm text-muted-foreground leading-relaxed">{q.context}</p>
              </div>
            ))}
          </div>
          <p className="mt-8 text-center text-sm text-muted-foreground max-w-2xl mx-auto">
            In Greek mythology, <strong>Panoptes</strong> (Πανόπτης, "all-seeing") was a giant with a hundred eyes who never slept — some eyes always remained open to watch. We named our platform <strong>Panopta</strong> to embody that same relentless, tireless vigilance over your data.
          </p>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how-it-works" className="border-b py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mx-auto mb-16 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight">Up and running in 10 minutes</h2>
            <p className="mt-4 text-muted-foreground">No data engineer. No YAML. No 6-month onboarding.</p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {HOW_IT_WORKS.map((s) => (
              <div key={s.n} className="rounded-xl border bg-card p-6">
                <div className="mb-4 text-4xl font-black text-primary/20">{s.n}</div>
                <h3 className="font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Product showcase ── */}
      <section className="border-b py-24 bg-muted/20" id="showcase">
        <div className="mx-auto max-w-6xl px-4">
          <div
            ref={showcaseRef}
            className={cn(
              'mb-10 text-center transition-all duration-700',
              showcaseVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8',
            )}
          >
            <h2 className="text-3xl font-bold tracking-tight">See it in action</h2>
            <p className="mt-4 text-muted-foreground">A real look at what Panopta puts in front of your team.</p>
          </div>

          {/* Tab bar */}
          <div className="flex justify-center gap-2 mb-8 flex-wrap">
            {SHOWCASE_TABS.map((tab, i) => (
              <button
                key={tab}
                type="button"
                onClick={() => handleTabClick(i)}
                className={cn(
                  'rounded-full border px-4 py-1.5 text-sm font-medium transition-all',
                  activeTab === i
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-card text-muted-foreground hover:text-foreground hover:border-primary/40',
                )}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Active mockup */}
          <div className="relative mx-auto max-w-3xl">
            <ActiveMockup />
          </div>

          {/* Dot indicators */}
          <div className="flex justify-center gap-2 mt-6">
            {SHOWCASE_TABS.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => handleTabClick(i)}
                className={cn(
                  'h-2 rounded-full transition-all',
                  activeTab === i ? 'w-5 bg-primary' : 'w-2 bg-muted-foreground/30',
                )}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ── AI incident example ── */}
      <section className="border-b py-24">
        <div className="mx-auto max-w-4xl px-4">
          <div className="mb-10 text-center">
            <h2 className="text-3xl font-bold tracking-tight">Not "null spike detected." This.</h2>
            <p className="mt-4 text-muted-foreground">Panopta tells your team exactly what to do, not just that something broke.</p>
          </div>
          <div className="rounded-xl border bg-card p-6 font-mono text-sm leading-relaxed space-y-3">
            <div className="flex items-center gap-2 pb-2 border-b">
              <span className="rounded-full bg-red-500/15 border border-red-500/30 px-2 py-0.5 text-xs text-red-600 dark:text-red-400 font-sans font-semibold">P1 Incident</span>
              <span className="text-foreground font-sans font-medium">orders.payment_status — null rate spike</span>
            </div>
            <p className="text-muted-foreground font-sans text-sm">
              <span className="font-semibold text-foreground">What happened:</span> The{' '}
              <code className="text-primary">orders</code> table had a 37% increase in null{' '}
              <code className="text-primary">payment_status</code> values today. The null rate increased from 0.8% to 18.4% — affecting ~24,000 rows.
            </p>
            <p className="text-muted-foreground font-sans text-sm">
              <span className="font-semibold text-foreground">Business impact:</span> Revenue reporting and order fulfillment dashboards may show incorrect data. Payment reconciliation will be affected.
            </p>
            <p className="text-muted-foreground font-sans text-sm">
              <span className="font-semibold text-foreground">Likely cause:</span> Recent checkout integration change or failed payment webhook mapping. Issue started around 10:15.
            </p>
            <div className="pt-2 border-t">
              <p className="text-xs font-sans text-muted-foreground mb-2 font-semibold uppercase tracking-wide">Debug query</p>
              <div className="rounded-lg bg-muted/60 p-3 text-xs">
                <span className="text-blue-500">SELECT</span> * <span className="text-blue-500">FROM</span> orders{' '}
                <span className="text-blue-500">WHERE</span> payment_status <span className="text-blue-500">IS NULL</span>{' '}
                <span className="text-blue-500">AND</span> created_at{' '}
                <span className="text-blue-500">&gt;=</span> NOW() - <span className="text-blue-500">INTERVAL</span>{' '}
                <span className="text-green-500">'24 hours'</span> <span className="text-blue-500">LIMIT</span> 100;
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="border-b py-24 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mx-auto mb-16 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight">Everything you need to trust your data</h2>
            <p className="mt-4 text-muted-foreground">Full-stack data observability without the enterprise price tag.</p>
          </div>
          <div
            ref={featuresRef}
            className={cn(
              'grid gap-6 sm:grid-cols-2 lg:grid-cols-3 transition-all duration-700',
              featuresVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8',
            )}
          >
            {FEATURES.map((f) => (
              <div key={f.title} className="rounded-xl border bg-card p-6 hover:shadow-md transition-shadow">
                <div className="mb-4 inline-flex size-10 items-center justify-center rounded-lg bg-primary/10">
                  <f.icon className="size-5 text-primary" />
                </div>
                <h3 className="font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Connectors ── */}
      <section id="connectors" className="border-b py-16">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mb-8 text-center">
            <h2 className="text-2xl font-bold tracking-tight">Connects to every database you use</h2>
            <p className="mt-2 text-sm text-muted-foreground">Operational databases and cloud warehouses in one platform.</p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            {CONNECTORS.map((c) => (
              <div key={c.name} className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium ${c.tier === 1 ? 'border-primary/30 bg-primary/8 text-primary' : 'bg-card'}`}>
                {c.name}
                {c.tier === 1 && <span className="text-xs opacity-70">Tier 1</span>}
              </div>
            ))}
          </div>
          <p className="mt-4 text-center text-xs text-muted-foreground">
            Tier 1: full profiling + AI recommendations. Tier 2: standard monitoring. More connectors on the roadmap.
          </p>
        </div>
      </section>

      {/* ── Agency feature callout ── */}
      <section className="border-b py-24">
        <div className="mx-auto max-w-4xl px-4 grid gap-8 lg:grid-cols-2 items-center">
          <div>
            <Badge variant="outline" className="mb-4">For agencies &amp; consultants</Badge>
            <h2 className="text-3xl font-bold tracking-tight">Give every client a professional database health report</h2>
            <p className="mt-4 text-muted-foreground leading-relaxed">
              Stop writing database health emails manually. Panopta generates client-safe reports automatically — no internal table names, no sensitive data — and delivers them on your schedule.
            </p>
            <ul className="mt-6 space-y-2">
              {[
                'Multi-client workspaces — manage all your clients from one place',
                'Client viewer role — clients see health scores, not credentials',
                'White-label reports — your branding, your delivery',
                'Auto-scheduled weekly and monthly reports',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2 text-sm">
                  <Check className="size-4 mt-0.5 text-primary shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <Button className="mt-6 gap-2" onClick={() => nav('/register')}>
              Try Agency plan <ArrowRight className="size-4" />
            </Button>
          </div>
          <div className="rounded-xl border bg-card p-5 space-y-3">
            <div className="flex items-center justify-between pb-3 border-b">
              <div className="text-sm font-semibold">Client: Acme Corp</div>
              <span className="rounded-full bg-green-500/15 border border-green-500/30 px-2 py-0.5 text-xs text-green-600 dark:text-green-400 font-semibold">Healthy 94/100</span>
            </div>
            {[
              { label: 'Tables monitored', value: '24' },
              { label: 'Open incidents', value: '0' },
              { label: 'Checks passed (24h)', value: '847 / 851' },
              { label: 'Last incident', value: '6 days ago' },
            ].map((row) => (
              <div key={row.label} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{row.label}</span>
                <span className="font-medium">{row.value}</span>
              </div>
            ))}
            <div className="pt-3 border-t">
              <div className="text-xs text-muted-foreground">Weekly report delivered automatically every Monday.</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="border-b py-20">
        <div className="mx-auto max-w-3xl px-4">
          <div className="mb-10 text-center">
            <h2 className="text-3xl font-bold tracking-tight">Frequently asked questions</h2>
          </div>
          <div className="divide-y">
            {[
              {
                q: 'How does Panopta connect to my database?',
                a: 'You provide read-only connection credentials (host, port, user, password, database name). Panopta stores them encrypted using HKDF per-tenant Fernet keys — they are never stored in plaintext. Panopta only executes SELECT queries and never writes to your database.'
              },
              {
                q: 'Does Panopta store my actual data?',
                a: 'No. Panopta only stores aggregate statistics — row counts, null rates, column cardinalities, percentiles, min/max values, and schema structure. It never reads, copies, or stores the actual content of your rows.'
              },
              {
                q: 'What counts as an "anomaly"?',
                a: 'Panopta uses 7 detection methods: Z-Score (statistical outliers), Isolation Forest (multivariate ML), STL Seasonal Decomposition (time-series patterns), Cardinality Drop, Row Growth Rate, Rule-Based checks (empty tables, SLA breaches, schema drift), and Enum/Category Drift. Each method has configurable sensitivity.'
              },
              {
                q: 'How many tables can I monitor on the free plan?',
                a: 'The free plan allows 1 data source and up to 5 monitored tables, with 7 days of profile history and email alerts. Starter (from $49/mo) supports 3 sources and 50 tables. Growth ($149/mo) is fully unlimited.'
              },
              {
                q: 'Is Panopta GDPR compliant?',
                a: 'Yes. Panopta processes only aggregate statistics, not personal data from your databases. Account data is stored securely, encrypted at rest, and you can request deletion at any time via privacy@panopta.app.'
              },
              {
                q: 'Can I get alerts on Slack or PagerDuty?',
                a: 'Yes. Slack and webhook alerts are available on Starter ($49/mo) and above. PagerDuty, Microsoft Teams, Discord, and OpsGenie are available on Growth ($149/mo) and above. Email alerts are available on all plans including free.'
              },
              {
                q: 'What is the AI narration feature?',
                a: 'For every P1 and P2 incident, Panopta generates an AI-written report explaining: what happened (with data), the likely cause, business impact, and a recommended debug query. It uses your configured LLM via OpenRouter (you can set your own API key).'
              },
              {
                q: 'How do I cancel my subscription?',
                a: 'You can cancel anytime from Settings → Billing → Cancel subscription. Your plan remains active until the end of the billing period. No refunds on partial periods, but you will never be charged after cancellation.'
              },
            ].map((faq, i) => (
              <FaqItem key={i} question={faq.q} answer={faq.a} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing ── */}
      <section id="pricing" className="border-b py-24 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mx-auto mb-6 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight">Transparent pricing</h2>
            <p className="mt-4 text-muted-foreground">Start free. No credit card. Upgrade when your stack grows.</p>
          </div>
          <p className="text-center text-sm text-muted-foreground mb-10">
            Monte Carlo starts at <span className="line-through">$1,000+/month</span>. Panopta starts at <span className="text-primary font-semibold">$0</span>.
          </p>
          <div
            ref={pricingRef}
            className={cn(
              'grid gap-6 sm:grid-cols-2 lg:grid-cols-4 transition-all duration-700',
              pricingVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8',
            )}
          >
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`relative rounded-xl border p-6 ${plan.highlight ? 'border-primary/60 bg-primary/5 ring-1 ring-primary/20' : 'bg-card'}`}
              >
                {plan.badge && (
                  <Badge className="absolute -top-3 left-1/2 -translate-x-1/2 text-xs">{plan.badge}</Badge>
                )}
                <div className="mb-4">
                  <div className="text-sm font-semibold text-muted-foreground">{plan.name}</div>
                  <div className="mt-1 text-3xl font-black">{plan.price}</div>
                  <div className="text-xs text-muted-foreground">{plan.period}</div>
                </div>
                <Separator className="my-4" />
                <ul className="flex flex-col gap-2">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm">
                      <Check className="size-4 mt-0.5 text-primary shrink-0" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  className="mt-6 w-full"
                  variant={plan.highlight ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => nav('/register')}
                >
                  Get started
                </Button>
              </div>
            ))}
          </div>
          <p className="mt-6 text-center text-xs text-muted-foreground">
            Enterprise plan available. Annual billing: 20% discount. Billing integration coming soon.
          </p>
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section className="py-24">
        <div className="mx-auto max-w-2xl px-4 text-center">
          <div className="inline-flex size-12 items-center justify-center rounded-full bg-primary/10 mb-6">
            <Eye className="size-6 text-primary" />
          </div>
          <h2 className="text-3xl font-bold tracking-tight">Your data is breaking silently right now.</h2>
          <p className="mt-4 text-muted-foreground text-lg">Panopta catches it — and explains it — before your clients or dashboards do.</p>
          <p className="mt-2 text-sm text-muted-foreground italic">"While some eyes rest, others watch."</p>
          <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
            <Button size="lg" className="gap-2 px-10 font-semibold" onClick={() => nav('/register')}>
              Start for free <ArrowRight className="size-4" />
            </Button>
            <Button size="lg" variant="outline" onClick={scrollToWorkspace}>
              Sign in to workspace
            </Button>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">No credit card. Setup in 10 minutes. Cancel anytime.</p>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t py-12 bg-muted/10">
        <div className="mx-auto max-w-6xl px-4">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4 mb-10">
            <div>
              <BrandMark />
              <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
                All-seeing data quality monitoring. Named for Panoptes, the tireless guardian of Greek mythology.
              </p>
            </div>
            <div>
              <p className="text-sm font-semibold mb-3">Product</p>
              <div className="flex flex-col gap-2 text-sm text-muted-foreground">
                <a href="#features" className="hover:text-foreground">Features</a>
                <a href="#pricing" className="hover:text-foreground">Pricing</a>
                <a href="#connectors" className="hover:text-foreground">Connectors</a>
                <a href="#how-it-works" className="hover:text-foreground">How it works</a>
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold mb-3">Company</p>
              <div className="flex flex-col gap-2 text-sm text-muted-foreground">
                <a href="/about" className="hover:text-foreground">About</a>
                <a href="/privacy" className="hover:text-foreground">Privacy Policy</a>
                <a href="/terms" className="hover:text-foreground">Terms of Service</a>
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold mb-3">Support</p>
              <div className="flex flex-col gap-2 text-sm text-muted-foreground">
                <button type="button" onClick={scrollToWorkspace} className="text-left hover:text-foreground">Sign in</button>
                <Link to="/register" className="hover:text-foreground">Create workspace</Link>
                <a href="mailto:hello@panopta.app" className="hover:text-foreground">Contact us</a>
              </div>
            </div>
          </div>
          <div className="border-t pt-6 flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
            <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} Panopta. All-seeing data quality monitoring.</p>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <a href="/privacy" className="hover:text-foreground">Privacy</a>
              <a href="/terms" className="hover:text-foreground">Terms</a>
              <a href="/about" className="hover:text-foreground">About</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
