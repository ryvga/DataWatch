import { useEffect, useState } from 'react'
import { BarChart3, CheckCircle2, Activity, AlertTriangle, TrendingUp, Shield, RefreshCw, Loader2, Sparkles, Clock } from 'lucide-react'
import { getWeeklyReport, getOrgHealth, generateWeeklySummary } from '../api/endpoints'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { PageHeader } from '../components/app-ui'
import { toast } from 'sonner'

const severityStyles = {
  P1: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  P2: 'border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-300',
  P3: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-yellow-300',
}

const healthStyles = {
  green: 'text-emerald-600 dark:text-emerald-400',
  yellow: 'text-yellow-600 dark:text-yellow-400',
  red: 'text-red-600 dark:text-red-400',
}

function formatNumber(value) {
  return value == null ? '0' : Number(value).toLocaleString()
}

function formatRelative(iso) {
  if (!iso) return null
  const diff = Date.now() - new Date(iso).getTime()
  const hours = Math.floor(diff / 3600000)
  if (hours < 1) return 'just now'
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function HealthScoreRing({ score = 0, grade = 'N/A', color = 'red' }) {
  const normalizedScore = Math.max(0, Math.min(100, Number(score) || 0))
  const radius = 44
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (normalizedScore / 100) * circumference
  const colorClass = healthStyles[color] || healthStyles.red

  return (
    <div className="flex items-center gap-5">
      <div className="relative size-32 shrink-0">
        <svg viewBox="0 0 120 120" className="size-32 -rotate-90" role="img" aria-label={`Health score ${Math.round(normalizedScore)}`}>
          <circle cx="60" cy="60" r={radius} fill="none" stroke="currentColor" strokeWidth="10" className="text-muted" />
          <circle cx="60" cy="60" r={radius} fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="10"
            strokeDasharray={circumference} strokeDashoffset={offset} className={colorClass} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-3xl font-bold tabular-nums text-foreground">{Math.round(normalizedScore)}</div>
          <div className="text-xs text-muted-foreground">score</div>
        </div>
      </div>
      <div className="min-w-0">
        <Badge variant="outline" className={colorClass}>Grade {grade}</Badge>
        <div className="mt-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">Last 7 days</div>
        <div className="mt-2 text-sm text-muted-foreground">
          Weighted average of passed checks and open incidents over the past week.
        </div>
      </div>
    </div>
  )
}

function StatCard({ title, value, icon: Icon, highlight }) {
  return (
    <Card className={highlight ? 'border-red-500/30 bg-red-500/5' : ''}>
      <CardContent className="flex items-center justify-between gap-3 p-5">
        <div className="min-w-0">
          <div className="text-sm text-muted-foreground">{title}</div>
          <div className={`mt-1 text-2xl font-bold tabular-nums ${highlight ? 'text-red-600 dark:text-red-400' : 'text-foreground'}`}>
            {formatNumber(value)}
          </div>
        </div>
        <div className={`flex size-10 shrink-0 items-center justify-center rounded-lg border ${highlight ? 'border-red-500/20 bg-red-500/10 text-red-500' : 'bg-muted/40 text-muted-foreground'}`}>
          <Icon className="size-5" />
        </div>
      </CardContent>
    </Card>
  )
}

function EmptyList({ label }) {
  return <div className="rounded-lg border border-dashed bg-muted/20 px-3 py-6 text-center text-sm text-muted-foreground">{label}</div>
}

function AISummaryCard({ summary, onGenerate, generating }) {
  const hasSummary = summary?.text

  return (
    <Card className={hasSummary ? '' : 'border-dashed'}>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="size-4 text-muted-foreground" />
            AI weekly summary
          </CardTitle>
          <div className="flex items-center gap-2">
            {summary?.generated_at && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="size-3" />
                {formatRelative(summary.generated_at)}
              </span>
            )}
            <Button size="sm" variant="outline" onClick={onGenerate} disabled={generating}>
              {generating
                ? <><Loader2 className="size-3.5 animate-spin mr-1.5" />Generating…</>
                : <><Sparkles className="size-3.5 mr-1.5" />{hasSummary ? 'Regenerate' : 'Generate'}</>}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {hasSummary ? (
          <p className="whitespace-pre-wrap text-sm leading-6 text-foreground">{summary.text}</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            No AI summary yet. Click <strong>Generate</strong> to produce a plain-English weekly digest using your configured LLM.
            Summaries are also regenerated automatically every Monday at 6 AM UTC.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export default function Reports() {
  const [report, setReport] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')

  const load = async (isRefresh = false) => {
    setError('')
    if (isRefresh) setRefreshing(true)
    try {
      const [healthResponse, reportResponse] = await Promise.all([
        getOrgHealth(),
        getWeeklyReport(),
      ])
      setHealth(healthResponse.data)
      setReport(reportResponse.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load reports')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await generateWeeklySummary()
      await load()
      toast.success('AI summary generated')
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Generation failed'
      toast.error(msg)
    } finally {
      setGenerating(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) {
    return (
      <div className="dw-page">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading weekly report…
        </div>
      </div>
    )
  }

  const score = report?.health_score ?? health?.score ?? 0
  const grade = report?.health_grade ?? health?.grade ?? 'N/A'
  const color = report?.health_color ?? health?.color ?? 'red'
  const topFailingChecks = report?.top_failing_checks || []
  const severityCounts = report?.incidents_by_severity || {}
  const tablesWithIncidents = report?.tables_with_incidents || []
  const recommendations = report?.recommendations || []
  const aiSummary = report?.ai_summary || null
  const openIncidents = report?.incidents_open ?? health?.open_incidents ?? 0

  return (
    <div className="dw-page">
      <PageHeader
        title="Reports"
        description={`Weekly report${report?.window_days ? ` · last ${report.window_days} days` : ''}`}
        actions={
          <Button type="button" variant="outline" onClick={() => load(true)} disabled={refreshing}>
            <RefreshCw data-icon="inline-start" className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </Button>
        }
      />

      {error && (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="flex items-start gap-3 p-4 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <div>{error}</div>
          </CardContent>
        </Card>
      )}

      {/* Health + stats */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="size-4 text-muted-foreground" />
              Health score
            </CardTitle>
          </CardHeader>
          <CardContent>
            <HealthScoreRing score={score} grade={grade} color={color} />
          </CardContent>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2">
          <StatCard title="Total Incidents" value={report?.incidents_total} icon={AlertTriangle} />
          <StatCard title="Open Incidents" value={openIncidents} icon={Activity} highlight={openIncidents > 0} />
          <StatCard title="Checks Passed" value={report?.checks_passed ?? health?.passed_checks} icon={CheckCircle2} />
          <StatCard title="Tables Monitored" value={report?.tables_monitored ?? health?.monitored_tables} icon={BarChart3} />
        </div>
      </div>

      {/* AI summary */}
      <AISummaryCard summary={aiSummary} onGenerate={handleGenerate} generating={generating} />

      {/* Failing checks + severity */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="size-4 text-muted-foreground" />
              Top failing checks
            </CardTitle>
          </CardHeader>
          <CardContent>
            {topFailingChecks.length === 0 ? (
              <EmptyList label="No failing checks in this report window." />
            ) : (
              <div className="space-y-1">
                {topFailingChecks.map((check, index) => (
                  <div key={`${check.check_name}-${index}`} className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-muted/40">
                    <div className="min-w-0 truncate text-sm font-medium">{check.check_name}</div>
                    <Badge variant="secondary" className="tabular-nums shrink-0">{formatNumber(check.count)} failures</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Incidents by severity</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {['P1', 'P2', 'P3'].map((sev) => (
              <div key={sev} className="flex items-center justify-between gap-3">
                <Badge variant="outline" className={severityStyles[sev]}>{sev}</Badge>
                <span className="text-sm font-semibold tabular-nums text-foreground">{formatNumber(severityCounts[sev] || 0)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Tables + recommendations */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tables with incidents</CardTitle>
          </CardHeader>
          <CardContent>
            {tablesWithIncidents.length === 0 ? (
              <EmptyList label="No tables had incidents in this report window." />
            ) : (
              <div className="space-y-1">
                {tablesWithIncidents.map((table) => (
                  <div key={table} className="rounded-lg px-3 py-2 font-mono text-xs hover:bg-muted/40">{table}</div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recommendations</CardTitle>
          </CardHeader>
          <CardContent>
            {recommendations.length === 0 ? (
              <EmptyList label="No recommendations available." />
            ) : (
              <div className="space-y-3">
                {recommendations.map((rec, index) => (
                  <div key={`${rec}-${index}`} className="flex gap-3 text-sm">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                    <div className="text-foreground">{rec}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Separator />
    </div>
  )
}
