import { useState } from 'react'
import { Activity, BarChart3, Bell, ChevronRight, Database, FileText, Shield, Users, Zap, Check, ArrowRight, GitBranch } from 'lucide-react'
import { BrandMark, ThemeToggle } from '../components/app-ui'
import { workspaceUrl } from '@/lib/subdomain'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

const FEATURES = [
  {
    icon: Database,
    title: 'Every database you use',
    desc: 'PostgreSQL, MySQL, MongoDB, ClickHouse, SQL Server, BigQuery, Snowflake, Redshift — operational databases and warehouses in one place.',
  },
  {
    icon: Activity,
    title: 'AI explains every incident',
    desc: 'Not just "null spike detected." DataWatch tells you what happened, why it likely happened, the business impact, and the exact debug query to run.',
  },
  {
    icon: BarChart3,
    title: 'Deep column profiling',
    desc: 'Null rates, cardinality, percentiles (p25/p50/p75/p95), top values, schema fingerprints, freshness — captured on every run, automatically.',
  },
  {
    icon: Zap,
    title: '6-method anomaly detection',
    desc: 'Z-Score, Isolation Forest, STL seasonal decomposition, cardinality drop, row growth rate, and rule-based checks — nothing slips through.',
  },
  {
    icon: FileText,
    title: 'Client-ready reports',
    desc: 'Generate weekly reliability reports, executive summaries, and client-safe incident reports automatically. Agencies: white-label with your branding.',
  },
  {
    icon: Shield,
    title: 'Safe by design',
    desc: 'Read-only credentials. HKDF per-tenant encryption. DataWatch cannot modify your data. Query timeouts protect production databases.',
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
  { n: '01', title: 'Connect your database', desc: 'Paste read-only credentials. DataWatch scans your schema in seconds.' },
  { n: '02', title: 'AI recommends monitors', desc: 'DataWatch reads your tables and proposes monitors: freshness, nulls, duplicates, schema drift, business rules.' },
  { n: '03', title: 'Incidents with AI context', desc: 'When something breaks, get an AI-written report — what happened, why, the business impact, debug queries.' },
  { n: '04', title: 'Reports sent automatically', desc: 'Weekly reliability reports go to your team. Client-safe summaries go to your clients. You stay ahead.' },
]

const COMPARISON = [
  { name: 'Monte Carlo', price: '$1,000–5,000+/mo', note: 'Enterprise only, 3-6 month setup' },
  { name: 'Soda', price: '$400–1,000/mo', note: 'Warehouse-first, no app databases' },
  { name: 'Elementary', price: '$200+/mo', note: 'dbt-only, no MongoDB, no app DBs' },
  { name: 'DataWatch', price: 'From $49/mo', note: 'Operational + warehouse, AI-first, 10-min setup', highlight: true },
]

export default function Landing() {
  const [workspaceInput, setWorkspaceInput] = useState('')

  const goToWorkspace = () => {
    const slug = workspaceInput.trim().toLowerCase().replace(/[^a-z0-9-]/g, '')
    if (!slug) return
    window.location.href = workspaceUrl(slug)
  }

  const scrollToWorkspace = () => {
    document.getElementById('workspace-input')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setTimeout(() => document.getElementById('workspace-input')?.focus(), 400)
  }

  return (
    <div className="min-h-screen bg-background text-foreground">

      {/* Nav */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
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
            <Button size="sm" onClick={scrollToWorkspace}>Start free</Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden border-b">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,hsl(var(--primary)/0.08),transparent_60%)]" />
        <div className="relative mx-auto max-w-6xl px-4 py-24 text-center">
          <Badge variant="secondary" className="mb-6 gap-1.5">
            <Activity className="size-3" />
            Open Beta — Free to start
          </Badge>
          <h1 className="mx-auto max-w-4xl text-4xl font-extrabold tracking-tight sm:text-6xl leading-tight">
            DataWatch monitors your databases like a data engineer,<br className="hidden lg:block" />
            <span className="text-primary"> explains incidents like a senior analyst.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed">
            Connect PostgreSQL, MySQL, MongoDB, and 9+ more databases. DataWatch detects silent data problems — freshness failures, null spikes, schema drift, duplicate records — then explains every incident with AI and sends reports your clients actually understand.
          </p>
          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Button size="lg" className="gap-2 font-semibold px-8" onClick={scrollToWorkspace}>
              Start for free
              <ArrowRight className="size-4" />
            </Button>
            <Button size="lg" variant="outline" className="gap-2" onClick={() => document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' })}>
              See how it works
            </Button>
          </div>

          {/* Workspace jump */}
          <div id="workspace-input" className="mt-12 flex items-center justify-center mx-auto max-w-sm overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="flex items-center pl-4 text-sm text-muted-foreground select-none whitespace-nowrap">
              <span>datawatch.io /</span>
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
          <p className="mt-2 text-xs text-muted-foreground">Already have a workspace? Jump right in.</p>
        </div>
      </section>

      {/* Comparison strip */}
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

      {/* How it works */}
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

      {/* AI incident example */}
      <section className="border-b py-24 bg-muted/20">
        <div className="mx-auto max-w-4xl px-4">
          <div className="mb-10 text-center">
            <h2 className="text-3xl font-bold tracking-tight">Not "null spike detected." This.</h2>
            <p className="mt-4 text-muted-foreground">DataWatch tells your team exactly what to do, not just that something broke.</p>
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

      {/* Features */}
      <section id="features" className="border-b py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mx-auto mb-16 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight">Everything you need to trust your data</h2>
            <p className="mt-4 text-muted-foreground">Full-stack data observability without the enterprise price tag.</p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
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

      {/* Connectors */}
      <section id="connectors" className="border-b py-16 bg-muted/20">
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

      {/* Agency feature callout */}
      <section className="border-b py-24">
        <div className="mx-auto max-w-4xl px-4 grid gap-8 lg:grid-cols-2 items-center">
          <div>
            <Badge variant="outline" className="mb-4">For agencies & consultants</Badge>
            <h2 className="text-3xl font-bold tracking-tight">Give every client a professional database health report</h2>
            <p className="mt-4 text-muted-foreground leading-relaxed">
              Stop writing database health emails manually. DataWatch generates client-safe reports automatically — no internal table names, no sensitive data — and delivers them on your schedule.
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
            <Button className="mt-6 gap-2" onClick={scrollToWorkspace}>
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

      {/* Pricing */}
      <section id="pricing" className="border-b py-24 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mx-auto mb-6 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight">Transparent pricing</h2>
            <p className="mt-4 text-muted-foreground">Start free. No credit card. Upgrade when your stack grows.</p>
          </div>
          <p className="text-center text-sm text-muted-foreground mb-10">
            Monte Carlo starts at <span className="line-through">$1,000+/month</span>. DataWatch starts at <span className="text-primary font-semibold">$0</span>.
          </p>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
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
                  onClick={scrollToWorkspace}
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

      {/* CTA */}
      <section className="py-24">
        <div className="mx-auto max-w-2xl px-4 text-center">
          <h2 className="text-3xl font-bold tracking-tight">Your data is breaking silently right now.</h2>
          <p className="mt-4 text-muted-foreground text-lg">DataWatch catches it — and explains it — before your clients or dashboards do.</p>
          <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
            <Button size="lg" className="gap-2 px-10 font-semibold" onClick={scrollToWorkspace}>
              Start for free <ArrowRight className="size-4" />
            </Button>
            <Button size="lg" variant="outline" onClick={scrollToWorkspace}>
              Sign in to workspace
            </Button>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">No credit card. Setup in 10 minutes. Cancel anytime.</p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 sm:flex-row sm:justify-between">
          <BrandMark />
          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} DataWatch. Database observability for every team.</p>
          <div className="flex gap-4 text-xs text-muted-foreground">
            <a href="#pricing" className="hover:text-foreground">Pricing</a>
            <a href="#workspace-input" className="hover:text-foreground">Sign in</a>
            <a href="#workspace-input" className="hover:text-foreground">Get started</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
