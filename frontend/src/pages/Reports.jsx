import { useEffect, useState } from 'react'
import { BarChart3, CheckCircle2, Activity, AlertTriangle, TrendingUp, Shield, RefreshCw, Loader2 } from 'lucide-react'
import { getWeeklyReport, getOrgHealth } from '../api/endpoints'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { PageHeader } from '../components/app-ui'

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

function getErrorMessage(err) {
  return err.response?.data?.detail || err.message || 'Failed to load reports'
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
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            className="text-muted"
          />
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="10"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className={colorClass}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-3xl font-bold tabular-nums text-foreground">{Math.round(normalizedScore)}</div>
          <div className="text-xs text-muted-foreground">score</div>
        </div>
      </div>
      <div className="min-w-0">
        <Badge variant="outline" className={colorClass}>
          Grade {grade}
        </Badge>
        <div className="mt-3 text-sm text-muted-foreground">
          Weekly organization health based on incidents and check results.
        </div>
      </div>
    </div>
  )
}

function StatCard({ title, value, icon: Icon }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-5">
        <div className="min-w-0">
          <div className="text-sm text-muted-foreground">{title}</div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-foreground">{formatNumber(value)}</div>
        </div>
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg border bg-muted/40 text-muted-foreground">
          <Icon className="size-5" />
        </div>
      </CardContent>
    </Card>
  )
}

function EmptyList({ label }) {
  return <div className="rounded-lg border border-dashed bg-muted/20 px-3 py-6 text-center text-sm text-muted-foreground">{label}</div>
}

export default function Reports() {
  const [report, setReport] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
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
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return (
      <div className="dw-page">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading weekly report
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
  const summary = report?.ai_summary

  return (
    <div className="dw-page">
      <PageHeader
        title="Reports"
        description={`Weekly report${report?.window_days ? ` for the last ${report.window_days} days` : ''}`}
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
          <StatCard title="Open Incidents" value={report?.incidents_open ?? health?.open_incidents} icon={Activity} />
          <StatCard title="Checks Passed" value={report?.checks_passed ?? health?.passed_checks} icon={CheckCircle2} />
          <StatCard title="Tables Monitored" value={report?.tables_monitored ?? health?.monitored_tables} icon={BarChart3} />
        </div>
      </div>

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
                    <Badge variant="secondary" className="tabular-nums">{formatNumber(check.count)}</Badge>
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
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {['P1', 'P2', 'P3'].map((severity) => (
                <Badge key={severity} variant="outline" className={severityStyles[severity]}>
                  {severity}
                  <span className="ml-1 tabular-nums">{formatNumber(severityCounts[severity] || 0)}</span>
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

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
                {recommendations.map((recommendation, index) => (
                  <div key={`${recommendation}-${index}`} className="flex gap-3 text-sm">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                    <div className="text-foreground">{recommendation}</div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {summary && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">AI summary</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{summary}</p>
          </CardContent>
        </Card>
      )}

      <Separator />
    </div>
  )
}
