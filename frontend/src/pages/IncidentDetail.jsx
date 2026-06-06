import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Circle,
  Clock,
  Copy,
  Database,
  ExternalLink,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Terminal,
} from 'lucide-react'
import { notify } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { acknowledgeIncident, investigateIncident, getIncident, getTable, resolveIncident, muteIncident, markFalsePositive, retryNarration } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import SeverityBadge from '../components/SeverityBadge'
import { LoadingState, formatDateTime, formatNumber } from '../components/app-ui'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const CONFIDENCE_STYLES = {
  high: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  medium: 'border-amber-600/25 bg-amber-500/12 text-amber-700 dark:text-amber-300',
  low: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

const PROBABILITY_STYLES = {
  high: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  medium: 'border-amber-600/25 bg-amber-500/12 text-amber-700 dark:text-amber-300',
  low: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

function normalizeTone(value) {
  if (typeof value === 'number') {
    if (value >= 0.7) return 'high'
    if (value >= 0.35) return 'medium'
    return 'low'
  }
  const key = String(value || '').trim().toLowerCase()
  if (['high', 'medium', 'low'].includes(key)) return key
  return 'low'
}

function confidenceLabel(value) {
  const tone = normalizeTone(value)
  return `${tone[0].toUpperCase()}${tone.slice(1)} confidence`
}

function probabilityLabel(value) {
  if (typeof value === 'number') return `${Math.round(value * 100)}%`
  const tone = normalizeTone(value)
  return `${tone[0].toUpperCase()}${tone.slice(1)}`
}

function qualifiedTableName(table, incident) {
  if (table?.schema_name && table?.table_name) return `${table.schema_name}.${table.table_name}`
  if (table?.table_name) return table.table_name
  return incident?.table_id || 'table_name'
}

function asArray(value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  if (typeof value === 'string') return value.split('\n').filter(Boolean)
  return []
}

function asQueryArray(value) {
  if (!value) return []
  if (Array.isArray(value)) return value.map(String).filter(Boolean)
  if (typeof value === 'string') return [value].filter(Boolean)
  return []
}

function extractQueriesFromText(text) {
  const lines = String(text || '').split('\n')
  const queries = []

  lines.forEach((line) => {
    const trimmed = line.trim()
    const upper = trimmed.toUpperCase()
    if (!trimmed) return

    if (upper.startsWith('SELECT')) {
      queries.push(trimmed)
      return
    }

    if (upper.startsWith('RUN:')) {
      const query = trimmed.replace(/^run:\s*/i, '').trim()
      if (query) queries.push(query)
      return
    }

    const selectIndex = upper.indexOf('SELECT')
    if (selectIndex >= 0) queries.push(trimmed.slice(selectIndex).trim())
  })

  return queries
}

function uniqueQueries(queries) {
  const seen = new Set()
  return queries.filter((query) => {
    const key = query.replace(/\s+/g, ' ').trim().toLowerCase()
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function getDebugQueries(narration, table, incident) {
  const explicitQueries = uniqueQueries(asQueryArray(narration?.debug_queries))
  if (explicitQueries.length) return explicitQueries

  const extracted = uniqueQueries(
    asArray(narration?.recommended_actions).flatMap((action) => extractQueriesFromText(action))
  )
  if (extracted.length) return extracted

  return [
    `Run this query to inspect affected rows:\nSELECT * FROM ${qualifiedTableName(table, incident)} WHERE ... LIMIT 100`,
  ]
}

function scrubClientText(text, table) {
  const tableNames = [
    table?.table_name,
    table?.schema_name && table?.table_name ? `${table.schema_name}.${table.table_name}` : null,
    table?.source_id,
  ].filter(Boolean)

  let output = String(text || '').replace(/\b[\w.-]+@[\w.-]+\.\w+\b/g, '[contact]')
  tableNames.forEach((name) => {
    output = output.replace(new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), 'the affected dataset')
  })
  return output
    .replace(/\b(select|insert|update|delete|where|join|schema|table|column|database|warehouse|credential|password|token|secret)\b/gi, 'data')
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, 'internal reference')
    .replace(/\s+/g, ' ')
    .trim()
}

function getClientSummary(narration, table, incident) {
  if (narration?.client_safe_summary) return narration.client_safe_summary

  const source = narration?.impact_assessment || narration?.summary
  if (source) return scrubClientText(source, table)

  const severity = incident?.severity ? `${incident.severity} ` : ''
  return `${severity}data quality issue detected. Some reports or workflows that depend on the affected data may be delayed or incomplete while the team investigates.`
}

function formatObservedValue(value) {
  if (value == null || value === '') return '-'
  if (typeof value === 'number') return formatNumber(value)
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function normalizeCheck(check, index) {
  if (typeof check === 'string') {
    return {
      id: `${check}-${index}`,
      check_name: check,
      check_type: 'anomaly',
      status: 'failed',
      observed_value: null,
    }
  }
  return {
    id: check.id || check.check_name || index,
    check_name: check.check_name || check.name || `Check ${index + 1}`,
    check_type: check.check_type || check.type || 'anomaly',
    status: check.status || 'failed',
    observed_value: check.observed_value ?? check.value ?? null,
  }
}

function getTimelineSteps(incident) {
  const isResolved = incident?.status === 'resolved' || !!incident?.resolved_at
  const isAcknowledged = isResolved || incident?.status === 'acknowledged' || !!incident?.acknowledged_at
  const isInvestigating = incident?.status === 'investigating'

  return [
    { key: 'detected', label: 'Detected', timestamp: incident?.created_at, complete: true, current: incident?.status === 'open' },
    { key: 'acknowledged', label: 'Acknowledged', timestamp: incident?.acknowledged_at, complete: isAcknowledged, current: false },
    { key: 'investigating', label: 'Investigating', timestamp: null, complete: isResolved, current: isInvestigating },
    { key: 'resolved', label: 'Resolved', timestamp: incident?.resolved_at, complete: isResolved, current: isResolved },
  ]
}

function IncidentCopilotCard({ narration, incident }) {
  const suggestedMonitors = asArray(narration?.suggested_monitors)
  const ownershipHint = narration?.ownership_hint
  const mutedUntil = incident?.llm_narration?.muted_until
  const falsePositiveUntil = incident?.llm_narration?.false_positive_until

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="size-4 text-muted-foreground" />
          Incident copilot
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {ownershipHint ? (
          <div className="rounded-md border bg-muted/20 p-3">
            <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">Suggested owner</p>
            <p className="mt-1 text-foreground">{ownershipHint}</p>
          </div>
        ) : (
          <div className="rounded-md border bg-muted/20 p-3 text-muted-foreground">
            No ownership hint was generated. Use alert routing to assign table-level owners.
          </div>
        )}

        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">Follow-up monitors</p>
          {suggestedMonitors.length ? (
            <ul className="flex flex-col gap-2">
              {suggestedMonitors.map((item, index) => (
                <li key={`${item}-${index}`} className="rounded-md border bg-muted/20 px-3 py-2 text-sm leading-6">{item}</li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">No extra monitors were suggested for this incident.</p>
          )}
        </div>

        {(mutedUntil || falsePositiveUntil) && (
          <div className="rounded-md border bg-amber-500/10 p-3 text-amber-800 dark:text-amber-200">
            {mutedUntil && <p>Muted until {formatDateTime(mutedUntil)}. Identical checks are suppressed during this window.</p>}
            {falsePositiveUntil && <p>False-positive suppression active until {formatDateTime(falsePositiveUntil)} for identical checks.</p>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function SectionTitle({ children }) {
  return <h3 className="text-sm font-semibold text-foreground">{children}</h3>
}

function TimelineStepper({ incident }) {
  const steps = getTimelineSteps(incident)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Status timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-4">
          {steps.map((step, index) => {
            const Icon = step.complete ? CheckCircle2 : Circle
            return (
              <div key={step.key} className="relative min-w-0">
                {index < steps.length - 1 && (
                  <div className="absolute left-4 top-4 hidden h-px w-[calc(100%_-_1rem)] bg-border sm:block" />
                )}
                <div className="relative z-10 flex min-w-0 items-start gap-3 sm:flex-col sm:gap-2">
                  <span
                    className={cn(
                      'flex size-8 shrink-0 items-center justify-center rounded-full border bg-card',
                      step.complete && 'border-primary/40 bg-primary/10 text-primary',
                      step.current && 'border-amber-500/45 bg-amber-500/12 text-amber-700 dark:text-amber-300'
                    )}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span
                      className={cn(
                        'block text-sm font-medium',
                        step.complete || step.current ? 'text-foreground' : 'text-muted-foreground'
                      )}
                    >
                      {step.label}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {step.timestamp ? formatDateTime(step.timestamp) : step.current ? 'Current status' : 'Pending'}
                    </span>
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

function AnalysisCard({ narration, llmIsEmpty, llmHasError, onRetry, retrying, canRetry }) {
  if (!narration) {
    return (
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <CardTitle className="text-base">AI incident analysis</CardTitle>
          {canRetry && (
            <Button type="button" size="sm" variant="outline" onClick={onRetry} disabled={retrying}>
              {retrying ? <Loader2 className="size-3.5 animate-spin mr-1" /> : <RefreshCw className="size-3.5 mr-1" />}
              {retrying ? 'Retrying…' : 'Retry analysis'}
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {llmHasError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              AI analysis failed. {canRetry ? 'Click "Retry analysis" to try again.' : 'Check that an LLM key is configured in admin settings.'}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">AI analysis is pending. The incident can still be investigated from fired checks and debug queries.</p>
          )}
        </CardContent>
      </Card>
    )
  }

  const confidenceTone = normalizeTone(narration.confidence)

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="size-4 text-muted-foreground" />
          AI incident analysis
        </CardTitle>
        <Badge variant="outline" className={cn('capitalize', CONFIDENCE_STYLES[confidenceTone])}>
          {confidenceLabel(narration.confidence)}
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {narration.summary && <p className="text-sm leading-6 text-foreground">{narration.summary}</p>}

        {narration.likely_causes?.length > 0 && (
          <section className="flex flex-col gap-2">
            <SectionTitle>Likely causes</SectionTitle>
            <div className="flex flex-col gap-2">
              {narration.likely_causes.map((cause, index) => {
                const tone = normalizeTone(cause.probability)
                return (
                  <div key={index} className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-md border bg-muted/20 px-3 py-2.5">
                    <Badge variant="outline" className={cn('mt-0.5', PROBABILITY_STYLES[tone])}>
                      {probabilityLabel(cause.probability)}
                    </Badge>
                    <p className="text-sm leading-6 text-muted-foreground">{cause.hypothesis}</p>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {narration.impact_assessment && (
          <section className="flex flex-col gap-2">
            <SectionTitle>Impact assessment</SectionTitle>
            <p className="text-sm leading-6 text-muted-foreground">{narration.impact_assessment}</p>
          </section>
        )}

        {narration.data_pattern_notes && (
          <section className="flex flex-col gap-2">
            <SectionTitle>Data pattern notes</SectionTitle>
            <p className="text-sm italic leading-6 text-muted-foreground">{narration.data_pattern_notes}</p>
          </section>
        )}
      </CardContent>
    </Card>
  )
}

function RecommendedActionsCard({ actions }) {
  const items = asArray(actions)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recommended actions</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length ? (
          <ol className="flex flex-col gap-2">
            {items.map((action, index) => (
              <li key={index} className="grid grid-cols-[auto_auto_minmax(0,1fr)] items-start gap-3 rounded-md border bg-muted/20 px-3 py-2.5">
                <span className="mt-0.5 flex size-5 items-center justify-center rounded border bg-background text-[11px] font-semibold tabular-nums text-muted-foreground">
                  {index + 1}
                </span>
                <span className="mt-0.5 flex size-5 items-center justify-center rounded border bg-card text-muted-foreground">
                  <Check className="size-3.5" />
                </span>
                <span className="text-sm leading-6 text-foreground">{action}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">No recommended actions were generated for this incident.</p>
        )}
      </CardContent>
    </Card>
  )
}

function DebugQueriesCard({ queries, onCopy }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Terminal className="size-4 text-muted-foreground" />
          Debug queries
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {queries.map((query, index) => (
          <div key={`${query}-${index}`} className="overflow-hidden rounded-md border bg-muted/20">
            <div className="flex items-center justify-between gap-3 border-b px-3 py-2">
              <span className="text-xs font-medium text-muted-foreground">Query {index + 1}</span>
              <Button type="button" size="xs" variant="outline" onClick={() => onCopy(query, 'Query copied')}>
                <Copy data-icon="inline-start" />
                Copy
              </Button>
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap p-3 text-xs leading-5 text-foreground">
              <code>{query}</code>
            </pre>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function ClientSummaryCard({ summary, onCopy }) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-base">Client-safe summary</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">Share with clients &mdash; no internal table names or credentials</p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={() => onCopy(summary, 'Client summary copied')}>
          <Copy data-icon="inline-start" />
          Copy for client
        </Button>
      </CardHeader>
      <CardContent>
        <p className="rounded-md border bg-muted/20 p-3 text-sm leading-6 text-foreground">{summary}</p>
      </CardContent>
    </Card>
  )
}

function FiredChecksCard({ checks }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Fired checks</CardTitle>
      </CardHeader>
      <CardContent>
        {checks.length ? (
          <div className="dw-table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Check</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Observed value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {checks.map((check, index) => (
                  <TableRow key={`${check.id}-${index}`}>
                    <TableCell className="font-mono text-xs text-foreground">{check.check_name}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono text-xs">
                        {check.check_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <HealthBadge status={check.status} />
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatObservedValue(check.observed_value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No fired checks were attached to this incident.</p>
        )}
      </CardContent>
    </Card>
  )
}

function AffectedTableCard({ incident, table, tableLoading, tableError, onOpenTable }) {
  const tableName = qualifiedTableName(table, incident)
  const sourceName = table?.source_name || table?.source?.name || table?.data_source?.name || null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Database className="size-4 text-muted-foreground" />
          Affected table
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Table ID</span>
          <code className="break-all rounded-md border bg-muted/30 px-2 py-1 text-xs text-foreground">{incident.table_id}</code>
        </div>

        {tableLoading && <p className="text-sm text-muted-foreground">Loading table details...</p>}
        {tableError && <p className="text-sm text-destructive">{tableError}</p>}

        {table && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-xs text-muted-foreground">Name</span>
                <p className="mt-1 font-mono text-xs text-foreground">{tableName}</p>
              </div>
              <div>
                <span className="text-xs text-muted-foreground">Status</span>
                <div className="mt-1">
                  <HealthBadge status={table.is_active ? 'healthy' : 'paused'} />
                </div>
              </div>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Source</span>
              <p className="mt-1 font-mono text-xs text-foreground">{sourceName || table.source_id || '-'}</p>
            </div>
          </>
        )}

        <Button type="button" variant="outline" className="w-fit" onClick={onOpenTable}>
          <ExternalLink data-icon="inline-start" />
          View table detail
        </Button>
      </CardContent>
    </Card>
  )
}

export default function IncidentDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [incident, setIncident] = useState(null)
  const [table, setTable] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [tableError, setTableError] = useState('')
  const [updating, setUpdating] = useState(false)
  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getIncident(id)
      .then((response) => {
        if (!cancelled) setIncident(response.data)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  useEffect(() => {
    if (!incident?.table_id) return
    let cancelled = false
    setTableLoading(true)
    setTableError('')
    getTable(incident.table_id)
      .then((response) => {
        if (!cancelled) setTable(response.data)
      })
      .catch(() => {
        if (!cancelled) setTableError('Table details are unavailable for this incident.')
      })
      .finally(() => {
        if (!cancelled) setTableLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [incident?.table_id])

  const llmRaw = incident?.llm_narration
  const llmIsEmpty = !llmRaw || Object.keys(llmRaw).length === 0
  const llmHasError = llmRaw?.error
  const narration = llmRaw && !llmIsEmpty && !llmHasError ? llmRaw : null
  const firedChecks = useMemo(
    () => (incident?.fired_checks || []).map((check, index) => normalizeCheck(check, index)),
    [incident?.fired_checks]
  )
  const debugQueries = useMemo(() => getDebugQueries(narration, table, incident), [narration, table, incident])
  const clientSummary = useMemo(() => getClientSummary(narration, table, incident), [narration, table, incident])

  const copyText = async (text, successMessage) => {
    try {
      await navigator.clipboard.writeText(text)
      notify.ok(successMessage)
    } catch (_) {
      notify.err('Copy failed', 'Clipboard access is unavailable in this browser.')
    }
  }

  const optimisticUpdate = (patch) => {
    const prev = incident
    setIncident((curr) => ({ ...curr, ...patch }))
    return prev
  }

  const doAck = async () => {
    const prev = optimisticUpdate({ status: 'acknowledged', acknowledged_at: new Date().toISOString() })
    setUpdating(true)
    try {
      const response = await acknowledgeIncident(id)
      setIncident(response.data)
      notify.incident.acknowledged(incident.title)
    } catch (err) {
      setIncident(prev)
      notify.err(err.response?.data?.detail || 'Failed to acknowledge incident')
    } finally {
      setUpdating(false)
    }
  }

  const doInvestigate = async () => {
    const prev = optimisticUpdate({ status: 'investigating' })
    setUpdating(true)
    try {
      const response = await investigateIncident(id)
      setIncident(response.data)
    } catch (err) {
      setIncident(prev)
      notify.err(err.response?.data?.detail || 'Failed to mark investigating')
    } finally {
      setUpdating(false)
    }
  }

  const doResolve = async () => {
    const prev = optimisticUpdate({ status: 'resolved', resolved_at: new Date().toISOString() })
    setUpdating(true)
    try {
      const response = await resolveIncident(id)
      setIncident(response.data)
      notify.incident.resolved(incident.title)
    } catch (err) {
      setIncident(prev)
      notify.err(err.response?.data?.detail || 'Failed to resolve incident')
    } finally {
      setUpdating(false)
    }
  }

  const doMute = async () => {
    const prev = optimisticUpdate({ status: 'muted' })
    setUpdating(true)
    try {
      const response = await muteIncident(id, { hours: 24 })
      setIncident(response.data)
    } catch (err) {
      setIncident(prev)
      /* endpoint may not be deployed yet */
    } finally { setUpdating(false) }
  }

  const doFalsePositive = async () => {
    if (!confirm('Mark as false positive? This will close the incident and prevent future re-creation.')) return
    const prev = optimisticUpdate({ status: 'ignored' })
    setUpdating(true)
    try {
      const response = await markFalsePositive(id)
      setIncident(response.data)
    } catch (err) {
      setIncident(prev)
      /* endpoint may not be deployed yet */
    } finally { setUpdating(false) }
  }

  const doRetryNarration = async () => {
    setRetrying(true)
    try {
      const response = await retryNarration(id)
      setIncident(response.data)
      notify.ok('AI analysis re-queued', 'Check back in a moment')
    } catch (err) {
      notify.err(err.response?.data?.detail || 'Retry failed')
    } finally {
      setRetrying(false)
    }
  }

  if (loading) return <LoadingState label="Loading incident" />
  if (!incident) return <div className="dw-page text-destructive">Incident not found</div>

  const detectedAt = incident.created_at ? formatDateTime(incident.created_at) : 'Unknown'
  const timeAgo = incident.created_at ? formatDistanceToNow(new Date(incident.created_at), { addSuffix: true }) : 'unknown time'

  const durationLabel = (() => {
    const mins = incident.duration_minutes
    if (mins == null) return null
    if (mins < 60) return `${mins}m`
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  })()
  const canAcknowledge = incident.status === 'open'
  const canResolve = incident.status !== 'resolved'

  return (
    <div className="dw-page">
      <header className="flex flex-col gap-4 border-b pb-4">
        <Button type="button" variant="ghost" className="w-fit" onClick={() => nav(-1)}>
          <ArrowLeft data-icon="inline-start" />
          Back
        </Button>

        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 space-y-2">
            <h1 className="max-w-5xl break-words text-2xl font-bold leading-tight text-foreground">{incident.title}</h1>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Clock className="size-4" />
              <span>Detected at {detectedAt}</span>
              <span aria-hidden="true">-</span>
              <span>{timeAgo}</span>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <SeverityBadge severity={incident.severity} />
            <HealthBadge status={incident.status} />
            {incident.status === 'acknowledged' && (
              <Button type="button" variant="secondary" onClick={doInvestigate} disabled={updating}>
                <Search data-icon="inline-start" />
                Mark Investigating
              </Button>
            )}
            {canAcknowledge && (
              <Button type="button" variant="outline" onClick={doAck} disabled={updating}>
                <Clock data-icon="inline-start" />
                Acknowledge
              </Button>
            )}
            {canResolve && (
              <Button type="button" onClick={doResolve} disabled={updating}>
                <Check data-icon="inline-start" />
                Resolve
              </Button>
            )}
            {incident.status !== 'resolved' && incident.status !== 'muted' && incident.status !== 'ignored' && (
              <>
                <Button type="button" variant="ghost" size="sm" onClick={doMute} disabled={updating} className="text-muted-foreground hover:text-foreground text-xs">
                  Mute 24h
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={doFalsePositive} disabled={updating} className="text-muted-foreground hover:text-foreground text-xs">
                  False positive
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <div className="grid gap-5">
        <TimelineStepper incident={incident} />

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <main className="flex min-w-0 flex-col gap-5">
            <AnalysisCard
              narration={narration}
              llmIsEmpty={llmIsEmpty}
              llmHasError={llmHasError}
              onRetry={doRetryNarration}
              retrying={retrying}
              canRetry={incident.status !== 'resolved'}
            />
            <IncidentCopilotCard narration={narration} incident={incident} />
            <RecommendedActionsCard actions={narration?.recommended_actions} />
            <DebugQueriesCard queries={debugQueries} onCopy={copyText} />
            <ClientSummaryCard summary={clientSummary} onCopy={copyText} />
            <FiredChecksCard checks={firedChecks} />
          </main>

          <aside className="flex min-w-0 flex-col gap-5">
            <AffectedTableCard
              incident={incident}
              table={table}
              tableLoading={tableLoading}
              tableError={tableError}
              onOpenTable={() => nav(`/tables/${incident.table_id}`)}
            />

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Incident facts</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">Severity</span>
                  <SeverityBadge severity={incident.severity} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">Status</span>
                  <HealthBadge status={incident.status} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">Checks fired</span>
                  <span className="font-medium">{firedChecks.length}</span>
                </div>
                {durationLabel && (
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted-foreground">{incident.status === 'resolved' ? 'TTR' : 'Open for'}</span>
                    <span className="font-medium tabular-nums">{durationLabel}</span>
                  </div>
                )}
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">Acknowledged</span>
                  <span className="text-right text-xs text-muted-foreground">{incident.acknowledged_at ? formatDateTime(incident.acknowledged_at) : '-'}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">Resolved</span>
                  <span className="text-right text-xs text-muted-foreground">{incident.resolved_at ? formatDateTime(incident.resolved_at) : '-'}</span>
                </div>
                {incident.llm_narration?.muted_until && (
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted-foreground">Muted until</span>
                    <span className="text-right text-xs text-muted-foreground">{formatDateTime(incident.llm_narration.muted_until)}</span>
                  </div>
                )}
                {incident.llm_narration?.false_positive_until && (
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-muted-foreground">Suppressed until</span>
                    <span className="text-right text-xs text-muted-foreground">{formatDateTime(incident.llm_narration.false_positive_until)}</span>
                  </div>
                )}
              </CardContent>
            </Card>
          </aside>
        </div>
      </div>
    </div>
  )
}
