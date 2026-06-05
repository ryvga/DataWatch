import { useState } from 'react'
import { Activity, BarChart3, Bell, ChevronRight, Database, GitBranch, Shield, Zap, Check, ArrowRight } from 'lucide-react'
import { BrandMark, ThemeToggle } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

const FEATURES = [
  {
    icon: Database,
    title: 'Universal Connectors',
    desc: 'Connect to Postgres, MySQL, BigQuery, Snowflake, Redshift, ClickHouse, Databricks, Trino, and more. One platform for every warehouse.',
  },
  {
    icon: BarChart3,
    title: 'Deep Profiling',
    desc: 'Row counts, freshness, schema fingerprints, column-level null rates, cardinality, percentiles, and top-value distributions — every run.',
  },
  {
    icon: Zap,
    title: 'Multi-Method Anomaly Detection',
    desc: 'Z-Score rolling windows, Isolation Forest, STL seasonal decomposition, and rule-based checks catch every class of data issue.',
  },
  {
    icon: Activity,
    title: 'AI Incident Reports',
    desc: 'Every P1/P2 incident gets an LLM-generated operator report: what happened, likely causes, impact assessment, and recommended actions.',
  },
  {
    icon: Bell,
    title: 'Smart Alerting',
    desc: 'Route alerts to Slack, email, or PagerDuty with per-channel severity filtering. Alerts include the AI summary — no context switching.',
  },
  {
    icon: Shield,
    title: 'Secure by Design',
    desc: 'HKDF per-tenant key derivation means connection credentials are isolated. Even a master key leak cannot expose cross-tenant data.',
  },
]

const PLANS = [
  {
    name: 'Free',
    price: '$0',
    period: 'forever',
    highlight: false,
    features: ['1 data source', 'Up to 5 tables', '7-day history', 'Email alerts', 'Community support'],
  },
  {
    name: 'Starter',
    price: '$49',
    period: 'per month',
    highlight: false,
    features: ['3 data sources', 'Up to 50 tables', '90-day history', 'Slack + PagerDuty', 'AI incident reports'],
  },
  {
    name: 'Growth',
    price: '$199',
    period: 'per month',
    highlight: true,
    badge: 'Most popular',
    features: ['Unlimited sources', 'Unlimited tables', '1-year history', 'All alert channels', 'Priority support', 'Custom LLM model'],
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: 'contact us',
    highlight: false,
    features: ['Everything in Growth', 'SSO / SAML', 'Dedicated infra', 'SLA guarantee', 'Custom retention', 'Team seats'],
  },
]

const CONNECTORS = ['PostgreSQL', 'MySQL', 'BigQuery', 'Snowflake', 'Redshift', 'ClickHouse', 'Databricks', 'Trino', 'DuckDB', 'SQLite']

export default function Landing() {
  const [workspaceInput, setWorkspaceInput] = useState('')

  const goToWorkspace = () => {
    const slug = workspaceInput.trim().toLowerCase()
    if (!slug) return
    window.location.href = `/login?ws=${slug}`
  }

  return (
    <div className="min-h-screen bg-background text-foreground">

      {/* Nav */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <BrandMark />
          <nav className="hidden items-center gap-6 text-sm md:flex">
            <a href="#features" className="text-muted-foreground hover:text-foreground transition-colors">Features</a>
            <a href="#connectors" className="text-muted-foreground hover:text-foreground transition-colors">Connectors</a>
            <a href="#pricing" className="text-muted-foreground hover:text-foreground transition-colors">Pricing</a>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="outline" size="sm" onClick={() => window.location.href = '/login'}>Sign in</Button>
            <Button size="sm" onClick={() => window.location.href = '/login'}>Get started</Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden border-b">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,hsl(var(--primary)/0.08),transparent_60%)]" />
        <div className="relative mx-auto max-w-6xl px-4 py-24 text-center">
          <Badge variant="secondary" className="mb-6 gap-1.5">
            <Activity className="size-3" />
            Open Beta
          </Badge>
          <h1 className="mx-auto max-w-3xl text-4xl font-extrabold tracking-tight sm:text-6xl leading-tight">
            Data quality monitoring<br className="hidden sm:block" /> that speaks human.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed">
            DataWatch profiles your warehouse tables, detects anomalies with four statistical methods, and generates AI-written incident reports that tell your team exactly what happened and why.
          </p>
          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Button size="lg" className="gap-2 font-semibold px-8" onClick={() => window.location.href = '/login'}>
              Start for free
              <ArrowRight className="size-4" />
            </Button>
            <Button size="lg" variant="outline" className="gap-2" onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}>
              See how it works
            </Button>
          </div>

          {/* Workspace jump */}
          <div className="mt-12 flex items-center justify-center gap-0 rounded-xl border bg-card shadow-sm mx-auto max-w-sm overflow-hidden">
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

      {/* Connectors strip */}
      <section id="connectors" className="border-b py-6">
        <div className="mx-auto max-w-6xl px-4">
          <p className="mb-4 text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Connects to every warehouse
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {CONNECTORS.map((c) => (
              <span key={c} className="rounded-full border bg-muted/40 px-3 py-1 text-xs font-medium">{c}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-b py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mx-auto mb-16 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight">Everything you need to trust your data</h2>
            <p className="mt-4 text-muted-foreground">From raw schema profiling to AI-written root-cause analysis, DataWatch handles the full incident lifecycle.</p>
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

      {/* Detection pipeline */}
      <section className="border-b py-24 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight">Four-layer detection pipeline</h2>
            <p className="mt-4 text-muted-foreground">Every table profile runs through all four methods. No anomaly class slips through.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { n: '01', name: 'Z-Score', detail: 'Rolling 14-day window per metric. Catches gradual drift.' },
              { n: '02', name: 'Rule-Based', detail: 'Zero rows, freshness SLA breach, schema drift, null spikes.' },
              { n: '03', name: 'Isolation Forest', detail: 'Multivariate anomaly score on 30-day feature matrix.' },
              { n: '04', name: 'STL Seasonal', detail: 'Seasonal decomposition on row-count time series.' },
            ].map((m) => (
              <div key={m.n} className="rounded-xl border bg-card p-5">
                <div className="mb-3 text-3xl font-black text-primary/20">{m.n}</div>
                <h4 className="font-semibold">{m.name}</h4>
                <p className="mt-1 text-xs text-muted-foreground">{m.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-b py-24">
        <div className="mx-auto max-w-6xl px-4">
          <div className="mx-auto mb-16 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight">Simple, transparent pricing</h2>
            <p className="mt-4 text-muted-foreground">Start free. Upgrade when your data stack grows.</p>
            <Badge variant="outline" className="mt-3">Billing integration coming soon</Badge>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={`relative rounded-xl border p-6 ${plan.highlight ? 'border-primary/60 bg-primary/5 ring-1 ring-primary/20' : 'bg-card'}`}
              >
                {plan.badge && (
                  <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">{plan.badge}</Badge>
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
                  onClick={() => window.location.href = '/login'}
                >
                  {plan.price === 'Custom' ? 'Contact us' : 'Get started'}
                </Button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24">
        <div className="mx-auto max-w-2xl px-4 text-center">
          <h2 className="text-3xl font-bold tracking-tight">Ready to trust your data pipeline?</h2>
          <p className="mt-4 text-muted-foreground">Create your workspace in 60 seconds. No credit card required.</p>
          <Button size="lg" className="mt-8 gap-2 px-10 font-semibold" onClick={() => window.location.href = '/login'}>
            Create free workspace
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 sm:flex-row sm:justify-between">
          <BrandMark />
          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} DataWatch. Data quality monitoring SaaS.</p>
          <div className="flex gap-4 text-xs text-muted-foreground">
            <a href="/login" className="hover:text-foreground">Sign in</a>
            <a href="/login" className="hover:text-foreground">Get started</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
