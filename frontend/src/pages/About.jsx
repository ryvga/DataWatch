import { Eye, Database, Shield, Zap, ArrowRight } from 'lucide-react'
import { BrandMark, ThemeToggle } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

export default function About() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <a href="/"><BrandMark /></a>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <a href="/"><Button variant="outline" size="sm">Home</Button></a>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="border-b py-24 bg-[radial-gradient(ellipse_at_top,hsl(var(--primary)/0.06),transparent_60%)]">
        <div className="mx-auto max-w-4xl px-4 text-center">
          <Badge variant="secondary" className="mb-6 gap-1.5">
            <Eye className="size-3" />
            All-seeing data quality
          </Badge>
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl leading-tight">
            Built for the team that can't afford<br />a silent data failure.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground leading-relaxed">
            Panopta is a data quality monitoring platform built to catch what your dashboards miss — and explain it before your clients do.
          </p>
          <p className="mt-3 text-sm italic text-muted-foreground">
            Named for Panoptes, the all-seeing giant of Greek mythology. Nothing escapes a hundred eyes.
          </p>
        </div>
      </section>

      {/* Story */}
      <section className="border-b py-20">
        <div className="mx-auto max-w-3xl px-4">
          <h2 className="text-2xl font-bold tracking-tight mb-6">The story</h2>
          <div className="prose prose-sm max-w-none dark:prose-invert space-y-4">
            <p>Panopta started as a final-year engineering thesis — a practical answer to a real problem: data teams spend hours every week manually checking their tables for freshness failures, null spikes, and schema drift. By the time something is obviously broken, the damage is already done.</p>
            <p>The thesis question was simple: can a single tool profile every database table automatically, detect anomalies using multiple statistical methods, and generate an AI-written explanation of what broke and why — all without a data engineer?</p>
            <p>The answer became Panopta. Seven days of intensive engineering produced a working MVP. What you see today is that MVP evolved into a production SaaS — with 13 database connectors, 7 anomaly detection methods, AI-generated incident reports, and team-based incident management.</p>
            <p>The name Panoptes stuck because it captures the mission perfectly: relentless, tireless observation. While your team sleeps, Panopta watches. When something breaks, it explains exactly what happened and who should care.</p>
          </div>
        </div>
      </section>

      {/* Values / How it works */}
      <section className="border-b py-20 bg-muted/20">
        <div className="mx-auto max-w-5xl px-4">
          <h2 className="text-2xl font-bold tracking-tight mb-10 text-center">What makes Panopta different</h2>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { icon: Eye, title: 'Always watching', desc: 'Profiles run on schedule, day and night. Anomalies are caught within minutes of a profile run.' },
              { icon: Database, title: 'Every database', desc: '13 connectors — PostgreSQL, MySQL, MongoDB, BigQuery, Snowflake, Redshift, ClickHouse, and more.' },
              { icon: Zap, title: 'AI explains it', desc: 'Every P1/P2 incident gets an AI-written report: what happened, why, business impact, debug query.' },
              { icon: Shield, title: 'Read-only & safe', desc: 'HKDF per-tenant encryption. Panopta never writes to your database. Query timeouts protect production.' },
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

      {/* Tech stack */}
      <section className="border-b py-20">
        <div className="mx-auto max-w-3xl px-4">
          <h2 className="text-2xl font-bold tracking-tight mb-6">Built on solid foundations</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ['Backend', 'Python 3.12, FastAPI (async), SQLAlchemy 2.0'],
              ['Task queue', 'Celery + Redis'],
              ['Database', 'PostgreSQL 16 with JSONB for metrics'],
              ['AI', 'OpenRouter API (per-org key, global fallback)'],
              ['Frontend', 'React 18, Vite, Tailwind CSS, Recharts'],
              ['Infrastructure', 'Docker Compose (dev), Railway (production)'],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border bg-card px-4 py-3">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{label}</div>
                <div className="mt-0.5 text-sm">{value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="mx-auto max-w-xl px-4 text-center">
          <h2 className="text-2xl font-bold tracking-tight">Try Panopta free</h2>
          <p className="mt-3 text-muted-foreground">Connect your first database in 10 minutes. No credit card required.</p>
          <div className="mt-6 flex justify-center gap-3">
            <a href="/">
              <Button size="lg" className="gap-2 px-8">
                Get started <ArrowRight className="size-4" />
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
