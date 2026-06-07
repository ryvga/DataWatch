import { Eye, Database, Shield, Zap, Users, BarChart3, Globe, Clock, ArrowRight, CheckCircle } from 'lucide-react'
import { BrandMark, ThemeToggle } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

const STATS = [
  { value: '12,400+', label: 'Tables monitored' },
  { value: '840+', label: 'Teams worldwide' },
  { value: '99.99%', label: 'Uptime SLA' },
  { value: '< 5 min', label: 'Avg. detection time' },
  { value: '13', label: 'Database connectors' },
  { value: '7', label: 'Detection methods' },
]

const VALUES = [
  {
    icon: Eye,
    title: 'Relentless observation',
    desc: "Your data never sleeps — neither do we. Panopta profiles tables on your schedule, around the clock, so anomalies are caught within minutes of appearing.",
  },
  {
    icon: Zap,
    title: 'Answers, not alerts',
    desc: 'Every incident comes with an AI-written explanation: what broke, why it likely happened, the business impact, and the exact query to start debugging.',
  },
  {
    icon: Shield,
    title: 'Privacy by architecture',
    desc: 'Read-only credentials. Per-tenant encryption. Zero data stored outside your configured retention window. Panopta can never modify your data.',
  },
  {
    icon: Users,
    title: 'Built for teams',
    desc: 'Assign incidents to engineers, set on-call rotations, route alerts to the right Slack channel. Data quality is a team sport.',
  },
]

const WHAT_WE_MONITOR = [
  'Row count drops & spikes',
  'Null rate changes',
  'Schema drift & column drops',
  'Freshness SLA breaches',
  'Cardinality drops',
  'Enum / category drift',
  'Statistical anomalies (Z-Score, Isolation Forest, STL)',
  'Duplicate record injection',
  'Row growth rate outliers',
  'Cross-table volume inconsistencies',
]

export default function About() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <a href="/"><BrandMark /></a>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <a href="/register"><Button size="sm">Start for free</Button></a>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="border-b py-24 bg-[radial-gradient(ellipse_at_top,hsl(var(--primary)/0.06),transparent_60%)]">
        <div className="mx-auto max-w-4xl px-4 text-center">
          <Badge variant="secondary" className="mb-6 gap-1.5">
            <Eye className="size-3" />
            Our mission
          </Badge>
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl leading-tight">
            Data quality monitoring that<br />
            <span className="text-primary">works the way your team does.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed">
            Panopta gives every engineering and data team the same data observability capabilities that only enterprise budgets could afford — at a price that makes sense for startups, agencies, and scale-ups alike.
          </p>
        </div>
      </section>

      {/* Stats strip */}
      <section className="border-b py-14 bg-muted/20">
        <div className="mx-auto max-w-5xl px-4">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-6">
            {STATS.map(s => (
              <div key={s.label} className="text-center">
                <div className="text-2xl font-black text-foreground">{s.value}</div>
                <div className="mt-1 text-xs text-muted-foreground">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Mission */}
      <section className="border-b py-20">
        <div className="mx-auto max-w-3xl px-4">
          <h2 className="text-2xl font-bold tracking-tight mb-6">Why we exist</h2>
          <div className="space-y-4 text-sm leading-relaxed text-muted-foreground">
            <p className="text-base text-foreground font-medium">
              Bad data is expensive. Silent data failures are worse.
            </p>
            <p>
              Most data teams discover problems when a client calls, when a dashboard goes blank, or when the weekly revenue number looks wrong in a board meeting. By then, the damage is done — hours of debugging, difficult client conversations, and eroded trust.
            </p>
            <p>
              Panopta was built to flip that equation. Instead of reacting to broken data, your team gets a warning the moment something deviates from normal — with enough context to fix it before anyone downstream notices. Not just a raw alert, but an AI-written incident report that explains what happened, why it likely happened, and what to do about it.
            </p>
            <p>
              We believe data observability shouldn't require a six-month implementation or a dedicated platform engineer. It should be running within the hour, connected to every database your team uses, and explainable to anyone in the org — not just the data engineers.
            </p>
          </div>
        </div>
      </section>

      {/* What we monitor */}
      <section className="border-b py-20 bg-muted/20">
        <div className="mx-auto max-w-4xl px-4">
          <div className="flex flex-col lg:flex-row gap-12 items-start">
            <div className="lg:w-1/2">
              <h2 className="text-2xl font-bold tracking-tight mb-4">What Panopta watches for</h2>
              <p className="text-sm text-muted-foreground leading-relaxed mb-6">
                From simple freshness checks to multivariate statistical anomaly detection, Panopta runs 7 different methods on every table profile — covering the failure patterns that matter most.
              </p>
              <a href="/help">
                <Button variant="outline" size="sm" className="gap-1.5">
                  See all detection methods <ArrowRight className="size-3.5" />
                </Button>
              </a>
            </div>
            <div className="lg:w-1/2">
              <ul className="grid grid-cols-1 gap-2">
                {WHAT_WE_MONITOR.map(item => (
                  <li key={item} className="flex items-center gap-2 text-sm">
                    <CheckCircle className="size-4 text-primary shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Values */}
      <section className="border-b py-20">
        <div className="mx-auto max-w-5xl px-4">
          <h2 className="text-2xl font-bold tracking-tight mb-10 text-center">What we stand for</h2>
          <div className="grid gap-6 sm:grid-cols-2">
            {VALUES.map(f => (
              <div key={f.title} className="rounded-xl border bg-card p-6">
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

      {/* Platform highlights */}
      <section className="border-b py-20 bg-muted/20">
        <div className="mx-auto max-w-4xl px-4">
          <h2 className="text-2xl font-bold tracking-tight mb-2 text-center">Built for production from day one</h2>
          <p className="text-center text-muted-foreground text-sm mb-10">
            The platform your data team will actually rely on — not a toy that breaks under real workloads.
          </p>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              {
                icon: Globe,
                title: '13 connectors',
                desc: 'PostgreSQL, MySQL, MongoDB, ClickHouse, BigQuery, Snowflake, Redshift, SQL Server, Cassandra, Databricks, Trino, DuckDB, SQLite.',
              },
              {
                icon: Clock,
                title: 'Always-on profiling',
                desc: 'Schedule profiles from every 15 minutes to daily. APScheduler runs inside the API — no external scheduler needed.',
              },
              {
                icon: BarChart3,
                title: 'Deep metrics',
                desc: 'Null rates, distinct counts, percentiles (p25/p50/p75/p95), schema fingerprints, row growth — captured every run, forever.',
              },
            ].map(f => (
              <div key={f.title} className="rounded-xl border bg-card p-5">
                <div className="mb-3 inline-flex size-9 items-center justify-center rounded-lg bg-primary/10">
                  <f.icon className="size-5 text-primary" />
                </div>
                <h3 className="font-semibold text-sm">{f.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* SLA commitment */}
      <section className="border-b py-16">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-green-500/30 bg-green-500/5 px-4 py-1.5 text-sm font-medium text-green-600 dark:text-green-400 mb-6">
            <span className="size-1.5 rounded-full bg-green-500" />
            99.99% uptime SLA
          </div>
          <h2 className="text-2xl font-bold tracking-tight">We take reliability seriously</h2>
          <p className="mt-4 text-muted-foreground text-sm leading-relaxed max-w-xl mx-auto">
            Panopta is built to be the most dependable piece of your data stack. Our 99.99% uptime SLA means your monitoring never goes dark — because a monitoring tool that's down is worse than no monitoring tool at all.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="mx-auto max-w-xl px-4 text-center">
          <h2 className="text-2xl font-bold tracking-tight">Ready to stop flying blind?</h2>
          <p className="mt-3 text-muted-foreground">Connect your first database in under 10 minutes. No credit card required.</p>
          <div className="mt-6 flex justify-center gap-3">
            <a href="/register">
              <Button size="lg" className="gap-2 px-8">
                Start for free <ArrowRight className="size-4" />
              </Button>
            </a>
            <a href="/help">
              <Button size="lg" variant="outline">Documentation</Button>
            </a>
          </div>
        </div>
      </section>

      <footer className="border-t py-6">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4">
          <BrandMark iconOnly />
          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} Panopta. All-seeing data quality monitoring.</p>
          <div className="flex gap-4 text-xs text-muted-foreground">
            <a href="/privacy" className="hover:text-foreground">Privacy</a>
            <a href="/terms" className="hover:text-foreground">Terms</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
