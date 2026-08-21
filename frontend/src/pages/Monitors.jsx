import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Activity, CheckCircle2, Code2, Copy, Database, FileCode2, Loader2, Play, RefreshCw, ShieldCheck, Table2, XCircle } from 'lucide-react'
import {
  activateSafeMonitor,
  createSafeMonitorDraft,
  getAllCustomMonitors,
  getSafeMonitorRuns,
  getSafeMonitors,
  getTables,
  previewSafeMonitorDefinition,
  runSafeMonitorNow,
} from '../api/endpoints'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, formatDateTime } from '../components/app-ui'
import { notify } from '@/lib/notify'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useRealtime } from '@/hooks/useRealtime'

const FILTERS = [
  { value: 'all', label: 'All monitors' },
  { value: 'dsl', label: 'Typed DSL' },
  { value: 'legacy', label: 'Legacy SQL' },
]

const DSL_STATUS_STYLES = {
  active: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  draft: 'border-amber-600/25 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  paused: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

const RUN_STATUS_STYLES = {
  succeeded: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  failed: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  queued: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
  running: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

function tableLabel(table) {
  return table ? `${table.schema_name}.${table.table_name}` : 'Unknown table'
}

function statusLabel(value) {
  return String(value || 'unknown').replaceAll('_', ' ')
}

function slugify(value) {
  return String(value || '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 63)
}

function parseLiteral(value) {
  const text = String(value ?? '').trim()
  if (text === '') return ''
  if (text === 'true') return true
  if (text === 'false') return false
  if (text === 'null') return null
  if (/^-?\d+(\.\d+)?$/.test(text)) return Number(text)
  return text
}

function apiErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter(Boolean)
    if (messages.length) return messages.join('; ')
  }
  return fallback
}

const INITIAL_DSL_FORM = {
  tableId: '',
  name: '',
  kind: 'row_count',
  breachOperator: 'gt',
  threshold: '0',
  field: '',
  predicateOperator: 'is_null',
  predicateValue: '',
  output: 'rate',
  severity: 'P2',
  mode: 'alert',
  triggerType: 'on_profile',
  description: '',
  owner: '',
  qualityDimension: '',
  filterField: '',
  filterOperator: 'none',
  filterValue: '',
  consecutiveBreaches: '1',
  recoveryPasses: '1',
}

function BuildDslDefinition({ form }) {
  const metadataName = slugify(form.name)
  const threshold = parseLiteral(form.threshold)
  const isRowCount = form.kind === 'row_count'
  const isViolation = form.kind === 'violations'
  const metricByKind = {
    freshness: 'freshness_seconds',
    null_rate: 'null_rate',
    duplicate_rate: 'duplicate_count',
    negative_rate: 'negative_rate',
    empty_string_rate: 'empty_string_rate',
  }
  const measurementId = isRowCount ? 'rows' : isViolation ? 'violations' : 'value'
  const breachRef = isRowCount ? 'rows' : isViolation ? `violations.${form.output}` : 'value'
  const predicate = ['is_null', 'is_not_null', 'is_missing', 'is_nan', 'is_zero', 'is_negative', 'is_empty', 'is_whitespace', 'is_true', 'is_false', 'is_future', 'is_past'].includes(form.predicateOperator)
    ? { op: form.predicateOperator, value: { field: form.field.trim() } }
    : {
      op: form.predicateOperator,
      left: { field: form.field.trim() },
      right: { literal: parseLiteral(form.predicateValue) },
    }

  const filterWhen = form.filterField.trim() && form.filterOperator !== 'none'
    ? ['is_null', 'is_not_null'].includes(form.filterOperator)
      ? { op: form.filterOperator, value: { field: form.filterField.trim() } }
      : { op: form.filterOperator, left: { field: form.filterField.trim() }, right: { literal: parseLiteral(form.filterValue) } }
    : null
  const metadata = {
    name: metadataName,
    ...(form.description.trim() ? { description: form.description.trim() } : {}),
    ...(form.owner.trim() ? { owner: form.owner.trim() } : {}),
    ...(form.qualityDimension ? { qualityDimension: form.qualityDimension } : {}),
  }
  const measurement = isRowCount
    ? { id: measurementId, type: 'metric', metric: 'row_count' }
    : isViolation
      ? { id: measurementId, type: 'violations', violationWhen: predicate, output: [form.output] }
      : { id: measurementId, type: 'metric', metric: metricByKind[form.kind], field: form.field.trim(), ...(filterWhen ? { filterWhen } : {}) }

  return {
    apiVersion: 'datawatch.io/v1alpha1',
    kind: 'Monitor',
    metadata,
    spec: {
      target: { assetId: form.tableId },
      trigger: { type: form.triggerType },
      measurements: [measurement],
      breachWhen: {
        op: form.breachOperator,
        left: { ref: breachRef },
        right: { literal: threshold },
      },
      policy: {
        mode: form.mode,
        severity: form.severity,
        consecutiveBreaches: Number(form.consecutiveBreaches) || 1,
        recoveryPasses: Number(form.recoveryPasses) || 1,
        cooldownMinutes: 60,
        notifyOnExecutionError: true,
      },
      execution: { timeoutSeconds: 30, sampling: { mode: 'auto' } },
    },
  }
}

function DslBuilderDialog({ open, onOpenChange, tables, initialTableId, onCreated }) {
  const [form, setForm] = useState({ ...INITIAL_DSL_FORM, tableId: initialTableId || '' })
  const [preview, setPreview] = useState(null)
  const [definition, setDefinition] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    if (!open) return
    setForm((current) => ({ ...current, tableId: current.tableId || initialTableId || tables[0]?.id || '' }))
  }, [initialTableId, open, tables])

  const set = (key) => (event) => {
    const value = event?.target ? event.target.value : event
    setForm((current) => ({ ...current, [key]: value }))
    setPreview(null)
    setError('')
  }

  const validateForm = () => {
    if (!form.tableId) return 'Choose a monitored table.'
    if (!slugify(form.name)) return 'Add a name using lowercase letters, numbers, or hyphens.'
    if (!form.threshold.trim() || !Number.isFinite(Number(form.threshold))) return 'Enter a numeric breach threshold.'
    if (!['row_count'].includes(form.kind) && !form.field.trim()) return 'Choose the column this rule should inspect.'
    if (form.kind === 'violations' && !['is_null', 'is_not_null', 'is_missing', 'is_nan', 'is_zero', 'is_negative', 'is_empty', 'is_whitespace', 'is_true', 'is_false', 'is_future', 'is_past'].includes(form.predicateOperator) && !form.predicateValue.trim()) {
      return 'Enter the value the column should be compared with.'
    }
    if (form.filterField.trim() && form.filterOperator !== 'none' && !['is_null', 'is_not_null'].includes(form.filterOperator) && !form.filterValue.trim()) {
      return 'Enter a value for the optional metric filter.'
    }
    return ''
  }

  const previewDefinition = async () => {
    const validationError = validateForm()
    if (validationError) {
      setError(validationError)
      return
    }
    const nextDefinition = BuildDslDefinition({ form })
    setBusy('preview')
    setError('')
    try {
      const response = await previewSafeMonitorDefinition(nextDefinition)
      setDefinition(nextDefinition)
      setPreview(response.data)
    } catch (err) {
      setPreview(null)
      setError(apiErrorMessage(err, 'Definition validation failed.'))
    } finally {
      setBusy('')
    }
  }

  const createAndActivate = async () => {
    if (!preview || !definition) return
    setBusy('create')
    setError('')
    try {
      const draftResponse = await createSafeMonitorDraft(form.tableId, definition)
      const draft = draftResponse.data
      const attestation = preview.preview?.attestation
      const activationSupported = preview.capabilityPlan?.activationSupported
      if (attestation && activationSupported) {
        await activateSafeMonitor(draft.id, {
          expectedRevision: draft.currentRevision,
          previewAttestation: attestation,
        })
        notify.ok('Typed DSL monitor activated', definition.metadata.name)
      } else {
        notify.ok('Typed DSL draft created', `${definition.metadata.name} needs activation review`)
      }
      onCreated?.()
      onOpenChange(false)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not create the DSL monitor.'))
    } finally {
      setBusy('')
    }
  }

  const close = (nextOpen) => {
    if (!nextOpen) {
      setPreview(null)
      setDefinition(null)
      setError('')
      setBusy('')
      setForm({ ...INITIAL_DSL_FORM, tableId: initialTableId || tables[0]?.id || '' })
    }
    onOpenChange(nextOpen)
  }

  const capabilityPlan = preview?.capabilityPlan
  const predicateValueOperators = !['is_null', 'is_not_null', 'is_missing', 'is_nan', 'is_zero', 'is_negative', 'is_empty', 'is_whitespace', 'is_true', 'is_false', 'is_future', 'is_past'].includes(form.predicateOperator)

  const copyDefinition = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(definition, null, 2))
      notify.ok('Definition copied', 'Paste it into a review or version-control change')
    } catch {
      notify.err('Copy failed', 'Your browser did not grant clipboard access')
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[92vh] overflow-y-auto p-0 sm:max-w-3xl">
        <DialogHeader className="border-b px-6 py-5">
          <DialogTitle>New typed DSL monitor</DialogTitle>
          <DialogDescription>Build a schema-bound monitor, preview its connector plan, then activate the immutable revision.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-5 px-6 py-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2 sm:col-span-2">
              <Label htmlFor="dsl-target">Monitored table</Label>
              <Select value={form.tableId} onValueChange={set('tableId')}>
                <SelectTrigger id="dsl-target" className="w-full"><SelectValue placeholder="Choose a table" /></SelectTrigger>
                <SelectContent>
                  {tables.map((table) => <SelectItem key={table.id} value={table.id}>{table.schema_name}.{table.table_name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dsl-name">Monitor name</Label>
              <Input id="dsl-name" value={form.name} onChange={set('name')} placeholder="orders-row-count" />
              <p className="text-xs text-muted-foreground">Stored as: {slugify(form.name) || 'lowercase-kebab-name'}</p>
            </div>
            <div className="grid gap-2">
              <Label>Rule type</Label>
              <Select value={form.kind} onValueChange={set('kind')}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="row_count">Volume · row count</SelectItem>
                  <SelectItem value="freshness">Freshness · seconds since update</SelectItem>
                  <SelectItem value="null_rate">Completeness · null rate</SelectItem>
                  <SelectItem value="duplicate_rate">Uniqueness · duplicate count</SelectItem>
                  <SelectItem value="negative_rate">Validity · negative values</SelectItem>
                  <SelectItem value="empty_string_rate">Completeness · empty strings</SelectItem>
                  <SelectItem value="violations">Validation · row predicate</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {form.kind === 'row_count' ? (
            <div className="grid gap-4 rounded-md border bg-muted/20 p-4 sm:grid-cols-[1fr_1fr]">
              <div className="grid gap-2">
                <Label>Breach when row count is</Label>
                <Select value={form.breachOperator} onValueChange={set('breachOperator')}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="gt">greater than</SelectItem>
                    <SelectItem value="gte">at least</SelectItem>
                    <SelectItem value="lt">less than</SelectItem>
                    <SelectItem value="lte">at most</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="dsl-threshold">Row count threshold</Label>
                <Input id="dsl-threshold" type="number" min="0" step="1" value={form.threshold} onChange={set('threshold')} />
              </div>
            </div>
          ) : form.kind === 'violations' ? (
            <div className="grid gap-4 rounded-md border bg-muted/20 p-4">
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label htmlFor="dsl-field">Column</Label>
                  <Input id="dsl-field" value={form.field} onChange={set('field')} placeholder="payment_status" />
                </div>
                <div className="grid gap-2">
                  <Label>Column rule</Label>
                  <Select value={form.predicateOperator} onValueChange={set('predicateOperator')}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="is_null">is null</SelectItem>
                      <SelectItem value="is_not_null">is not null</SelectItem>
                      <SelectItem value="eq">equals</SelectItem>
                      <SelectItem value="ne">does not equal</SelectItem>
                      <SelectItem value="gt">greater than</SelectItem>
                      <SelectItem value="gte">at least</SelectItem>
                      <SelectItem value="lt">less than</SelectItem>
                      <SelectItem value="lte">at most</SelectItem>
                      <SelectItem value="contains">contains</SelectItem>
                      <SelectItem value="is_empty">is empty</SelectItem>
                      <SelectItem value="is_whitespace">is whitespace-only</SelectItem>
                      <SelectItem value="is_true">is true</SelectItem>
                      <SelectItem value="is_false">is false</SelectItem>
                      <SelectItem value="is_future">is in the future</SelectItem>
                      <SelectItem value="is_past">is in the past</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {predicateValueOperators && (
                <div className="grid gap-2 sm:max-w-sm">
                  <Label htmlFor="dsl-predicate-value">Expected value</Label>
                  <Input id="dsl-predicate-value" value={form.predicateValue} onChange={set('predicateValue')} placeholder="paid or 0" />
                </div>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label>Count or rate</Label>
                  <Select value={form.output} onValueChange={set('output')}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="rate">Violation rate (0–1)</SelectItem>
                      <SelectItem value="count">Violation count</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="dsl-violation-threshold">Breach threshold</Label>
                  <Input id="dsl-violation-threshold" type="number" min="0" step="0.01" value={form.threshold} onChange={set('threshold')} placeholder={form.output === 'rate' ? '0.01' : '1'} />
                </div>
              </div>
            </div>
          ) : (
            <div className="grid gap-4 rounded-md border bg-muted/20 p-4">
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label htmlFor="dsl-metric-field">Column</Label>
                  <Input id="dsl-metric-field" value={form.field} onChange={set('field')} placeholder={form.kind === 'freshness' ? 'updated_at' : 'amount'} />
                  <p className="text-xs text-muted-foreground">The field is checked against the table’s typed schema before activation.</p>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="dsl-metric-threshold">Breach threshold</Label>
                  <Input id="dsl-metric-threshold" type="number" min="0" step="0.01" value={form.threshold} onChange={set('threshold')} />
                  <Select value={form.breachOperator} onValueChange={set('breachOperator')}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="gt">greater than</SelectItem>
                      <SelectItem value="gte">at least</SelectItem>
                      <SelectItem value="lt">less than</SelectItem>
                      <SelectItem value="lte">at most</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-4 rounded-md border bg-muted/20 p-4">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="dsl-description">Monitor description</Label>
                <Textarea id="dsl-description" value={form.description} onChange={set('description')} placeholder="What should this monitor protect?" className="min-h-20" />
              </div>
              <div className="grid gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="dsl-owner">Owner</Label>
                  <Input id="dsl-owner" value={form.owner} onChange={set('owner')} placeholder="data-platform@example.com" />
                </div>
                <div className="grid gap-2">
                  <Label>Quality dimension</Label>
                  <Select value={form.qualityDimension || 'none'} onValueChange={(value) => set('qualityDimension')(value === 'none' ? '' : value)}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Not specified</SelectItem>
                      <SelectItem value="accuracy">Accuracy</SelectItem>
                      <SelectItem value="completeness">Completeness</SelectItem>
                      <SelectItem value="consistency">Consistency</SelectItem>
                      <SelectItem value="timeliness">Timeliness</SelectItem>
                      <SelectItem value="validity">Validity</SelectItem>
                      <SelectItem value="uniqueness">Uniqueness</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </div>

          {form.kind !== 'violations' && form.kind !== 'row_count' && (
            <div className="grid gap-3 rounded-md border bg-muted/20 p-4">
              <div>
                <p className="text-sm font-medium">Optional metric filter</p>
                <p className="mt-1 text-xs text-muted-foreground">Scope the metric to a typed WHERE condition, such as status = paid. Literals stay parameterized.</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <Input aria-label="Metric filter field" value={form.filterField} onChange={set('filterField')} placeholder="status" />
                <Select value={form.filterOperator} onValueChange={set('filterOperator')}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No filter</SelectItem>
                    <SelectItem value="eq">equals</SelectItem>
                    <SelectItem value="ne">does not equal</SelectItem>
                    <SelectItem value="is_null">is null</SelectItem>
                    <SelectItem value="is_not_null">is not null</SelectItem>
                  </SelectContent>
                </Select>
                <Input aria-label="Metric filter value" value={form.filterValue} onChange={set('filterValue')} placeholder="paid" disabled={form.filterOperator === 'none' || ['is_null', 'is_not_null'].includes(form.filterOperator)} />
              </div>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="grid gap-2">
              <Label>Severity</Label>
              <Select value={form.severity} onValueChange={set('severity')}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="P1">P1 — Critical</SelectItem><SelectItem value="P2">P2 — High</SelectItem><SelectItem value="P3">P3 — Medium</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Run mode</Label>
              <Select value={form.mode} onValueChange={set('mode')}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="alert">Alert on breach</SelectItem><SelectItem value="track">Track only</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Trigger</Label>
              <Select value={form.triggerType} onValueChange={set('triggerType')}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="on_profile">After each profile</SelectItem><SelectItem value="manual">Manual only</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dsl-breaches">Consecutive breaches</Label>
              <Input id="dsl-breaches" type="number" min="1" max="20" value={form.consecutiveBreaches} onChange={set('consecutiveBreaches')} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dsl-recovery">Recovery passes</Label>
              <Input id="dsl-recovery" type="number" min="1" max="20" value={form.recoveryPasses} onChange={set('recoveryPasses')} />
            </div>
          </div>

          {error && <Alert variant="destructive"><XCircle className="size-4" /><AlertDescription>{String(error)}</AlertDescription></Alert>}
          {preview && (
            <div className="grid gap-3 rounded-md border bg-muted/20 p-4">
              <div className="flex items-center justify-between gap-2 text-sm font-medium">
                <div className="flex items-center gap-2">
                  {capabilityPlan?.activationSupported ? <CheckCircle2 className="size-4 text-emerald-600" /> : <XCircle className="size-4 text-amber-600" />}
                  {capabilityPlan?.activationSupported ? 'Preview compiled and ready to activate' : 'Preview valid, but activation is gated'}
                </div>
                <Button type="button" size="sm" variant="ghost" onClick={copyDefinition} aria-label="Copy DSL definition">
                  <Copy className="size-3.5" /> Copy JSON
                </Button>
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>{preview.stats?.measurements || 0} measurement(s)</span>
                <span>·</span>
                <span>{preview.definitionHash?.slice(0, 12)}…</span>
                {capabilityPlan?.sourceType && <><span>·</span><span>{capabilityPlan.sourceType}</span></>}
              </div>
              {!capabilityPlan?.activationSupported && capabilityPlan?.activationBlockers?.length > 0 && (
                <p className="text-xs text-amber-700 dark:text-amber-300">Activation blockers: {capabilityPlan.activationBlockers.join(', ')}</p>
              )}
              <Textarea readOnly value={JSON.stringify(definition, null, 2)} className="min-h-36 font-mono text-xs" aria-label="DSL definition preview" />
            </div>
          )}
        </div>
        <DialogFooter className="border-t px-6 py-4">
          <Button type="button" variant="outline" onClick={() => close(false)}>Cancel</Button>
          {!preview ? (
            <Button type="button" onClick={previewDefinition} disabled={busy !== ''}>{busy === 'preview' && <Loader2 className="size-3.5 animate-spin" />}Validate & preview</Button>
          ) : (
            <Button type="button" onClick={createAndActivate} disabled={busy !== ''}>{busy === 'create' && <Loader2 className="size-3.5 animate-spin" />}{capabilityPlan?.activationSupported ? 'Create & activate' : 'Create draft'}</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SummaryItem({ icon: Icon, label, value, detail }) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-md border bg-card px-4 py-3">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <Icon className="size-4" />
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="mt-0.5 truncate text-lg font-semibold tabular-nums text-foreground">{value}</div>
        {detail && <div className="truncate text-xs text-muted-foreground">{detail}</div>}
      </div>
    </div>
  )
}

function MonitorCard({ monitor, onOpenTable, onRun, running }) {
  const isDsl = monitor.kind === 'dsl'
  const tableId = monitor.tableId || monitor.table_id
  const latest = monitor.latestRun
  const monitorStatus = isDsl ? monitor.status : monitor.is_active ? 'active' : 'paused'
  const runStatus = latest?.status || (isDsl && monitorStatus === 'active' ? 'not_run' : null)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-3 border-b bg-muted/20 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border bg-background text-muted-foreground">
              {isDsl ? <ShieldCheck className="size-4" /> : <Code2 className="size-4" />}
            </div>
            <div className="min-w-0">
              <CardTitle className="truncate text-base">{monitor.name}</CardTitle>
              <button type="button" className="mt-1 flex items-center gap-1 text-left text-xs text-muted-foreground hover:text-foreground" onClick={() => onOpenTable(tableId)}>
                <Table2 className="size-3" />
                <span className="truncate">{monitor.tableLabel}</span>
              </button>
            </div>
          </div>
          <Badge variant="outline" className="shrink-0">{isDsl ? 'Typed DSL' : 'Legacy SQL'}</Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pt-4">
        {isDsl ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className={DSL_STATUS_STYLES[monitorStatus] || ''}>{statusLabel(monitorStatus)}</Badge>
              <Badge variant="outline">Revision {monitor.currentRevision}</Badge>
              {runStatus && <Badge variant="outline" className={RUN_STATUS_STYLES[runStatus] || ''}>{statusLabel(runStatus)}</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">
              {latest
                ? `${latest.result?.transition || latest.errorCode || 'completed'} · ${formatDateTime(latest.completedAt || latest.queuedAt)}`
                : monitorStatus === 'active'
                  ? 'Waiting for the first profile or a manual run.'
                  : 'Draft revision. Preview and activate it before execution.'}
            </p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{monitor.definitionVersion || 'datawatch.io/v1alpha1'}</span>
              {monitor.activationSupported === false && <span>· activation gated by connector capability</span>}
            </div>
            <div className="flex flex-wrap gap-2">
              {monitorStatus === 'active' && (
                <Button size="sm" variant="outline" onClick={() => onRun(monitor)} disabled={running}>
                  {running ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                  {running ? 'Queueing…' : 'Run now'}
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => onOpenTable(tableId)}>Open table</Button>
            </div>
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className={DSL_STATUS_STYLES[monitorStatus] || ''}>{monitorStatus}</Badge>
              <Badge variant="outline">{monitor.severity}</Badge>
              {monitor.run_on_profile && <span className="text-xs text-muted-foreground">Runs on every profile</span>}
            </div>
            <p className="line-clamp-2 text-sm text-muted-foreground">{monitor.description || 'SQL violation check managed from the table detail page.'}</p>
            <p className="text-xs text-muted-foreground">Last run: {formatDateTime(monitor.last_run_at)}</p>
            <Button size="sm" variant="ghost" className="w-fit" onClick={() => onOpenTable(monitor.table_id)}>Open table</Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}

export default function Monitors() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const [tables, setTables] = useState([])
  const [monitors, setMonitors] = useState([])
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [running, setRunning] = useState({})
  const [builderOpen, setBuilderOpen] = useState(false)

  const load = async ({ quiet = false } = {}) => {
    if (quiet) setRefreshing(true)
    else setLoading(true)
    setError('')
    try {
      const [tablesResponse, legacyResponse] = await Promise.all([getTables(), getAllCustomMonitors()])
      const nextTables = tablesResponse.data || []
      const tableById = Object.fromEntries(nextTables.map((table) => [table.id, table]))
      const dslResults = await Promise.allSettled(nextTables.map((table) => getSafeMonitors(table.id)))
      const dslMonitors = []
      let dslFailures = 0
      dslResults.forEach((result, index) => {
        if (result.status === 'rejected') {
          dslFailures += 1
          return
        }
        for (const monitor of result.value.data || []) {
          const tableId = monitor.assetId || nextTables[index].id
          dslMonitors.push({
            ...monitor,
            kind: 'dsl',
            tableId,
            tableLabel: tableLabel(tableById[tableId]),
          })
        }
      })

      const runResults = await Promise.allSettled(
        dslMonitors.map((monitor) => getSafeMonitorRuns(monitor.id)),
      )
      runResults.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          dslMonitors[index].latestRun = (result.value.data || [])[0] || null
        }
      })

      const legacyMonitors = (legacyResponse.data || []).map((monitor) => ({
        ...monitor,
        kind: 'legacy',
        tableLabel: tableLabel(tableById[monitor.table_id]),
      }))
      setTables(nextTables)
      setMonitors([...dslMonitors, ...legacyMonitors])
      if (dslFailures && dslFailures === nextTables.length) {
        setError('Typed DSL monitor data is temporarily unavailable. Legacy SQL monitors are still shown.')
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load monitors')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useRealtime((event) => {
    if (['monitor.run.completed', 'profile.completed', 'incident.updated', 'alert.route.updated'].includes(event?.type)) {
      load({ quiet: true })
    }
  })

  useEffect(() => {
    if (searchParams.get('table') && tables.length > 0) setBuilderOpen(true)
  }, [searchParams, tables.length])

  const visibleMonitors = useMemo(
    () => monitors.filter((monitor) => filter === 'all' || monitor.kind === filter),
    [filter, monitors],
  )
  const dslCount = monitors.filter((monitor) => monitor.kind === 'dsl').length
  const activeDslCount = monitors.filter((monitor) => monitor.kind === 'dsl' && monitor.status === 'active').length
  const legacyCount = monitors.filter((monitor) => monitor.kind === 'legacy').length

  const openTable = (tableId) => nav(`/tables/${tableId}`)

  const runMonitor = async (monitor) => {
    setRunning((current) => ({ ...current, [monitor.id]: true }))
    try {
      await runSafeMonitorNow(monitor.id, `monitors-page-${monitor.id}-${Date.now()}`)
      notify.ok('Typed DSL monitor queued', monitor.name)
      await load({ quiet: true })
    } catch (err) {
      notify.err(err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Unable to queue typed DSL monitor')
    } finally {
      setRunning((current) => ({ ...current, [monitor.id]: false }))
    }
  }

  if (loading && monitors.length === 0) return <LoadingState label="Loading monitors" />

  return (
    <div className="dw-page">
      <PageHeader
        title="Monitors"
        description="Typed DSL monitors and legacy SQL checks across every monitored table."
        actions={(
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setBuilderOpen(true)} disabled={tables.length === 0}>
              <ShieldCheck className="size-3.5" />
              New DSL monitor
            </Button>
            <Button variant="outline" size="sm" onClick={() => load({ quiet: true })} disabled={refreshing}>
              {refreshing ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
              Refresh
            </Button>
          </div>
        )}
      />

      <ErrorNotice message={error} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryItem icon={ShieldCheck} label="Typed DSL" value={dslCount} detail={`${activeDslCount} active`} />
        <SummaryItem icon={Activity} label="Active runtime" value={activeDslCount} detail="Schema-bound monitors" />
        <SummaryItem icon={Code2} label="Legacy SQL" value={legacyCount} detail="Custom table checks" />
        <SummaryItem icon={Database} label="Tables covered" value={tables.length} detail="Available monitor targets" />
      </div>

      <Card className="border-dashed bg-muted/20">
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <FileCode2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">Typed DSL runtime</p>
              <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                DSL monitors are schema-bound, revisioned, and run safely on supported connectors. Build and preview definitions here; this page is the workspace inventory, activation, and run control surface.
              </p>
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => nav('/help#dsl-guide')}>Open DSL guide</Button>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2 border-b pb-3">
        {FILTERS.map((item) => (
          <Button key={item.value} type="button" size="sm" variant={filter === item.value ? 'secondary' : 'ghost'} onClick={() => setFilter(item.value)}>
            {item.label}
          </Button>
        ))}
        <span className="ml-auto text-xs text-muted-foreground">{visibleMonitors.length} shown</span>
      </div>

      {visibleMonitors.length === 0 ? (
        <EmptyState
          icon={filter === 'dsl' ? ShieldCheck : Code2}
          title={filter === 'dsl' ? 'No typed DSL monitors yet' : filter === 'legacy' ? 'No legacy SQL monitors' : 'No monitors yet'}
          description={filter === 'dsl'
            ? 'Use New DSL monitor to validate and create a schema-bound definition. Once active, it will appear here and on its table detail page.'
            : 'Create a monitor from a table detail page to start checking data quality.'}
          action={filter === 'dsl' ? <Button variant="outline" onClick={() => nav('/help#dsl-guide')}>Open DSL guide</Button> : <Button onClick={() => nav('/tables')}>Open tables</Button>}
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {visibleMonitors.map((monitor) => (
            <MonitorCard
              key={`${monitor.kind}-${monitor.id}`}
              monitor={monitor}
              onOpenTable={openTable}
              onRun={runMonitor}
              running={!!running[monitor.id]}
            />
          ))}
        </div>
      )}
      <DslBuilderDialog
        open={builderOpen}
        onOpenChange={setBuilderOpen}
        tables={tables}
        initialTableId={searchParams.get('table') || ''}
        onCreated={() => load({ quiet: true })}
      />
    </div>
  )
}
