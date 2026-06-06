import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, AlertTriangle, CheckCircle2, Code2, Edit3, Loader2, Play, PlusCircle, Sparkles, Trash2, Wand2, X } from 'lucide-react'
import { getIncidents, getSources, getTable, getTableCheckResults, getTableProfiles, nlRule, recommendMonitors, runTable, getCustomMonitors, createCustomMonitor, updateCustomMonitor, deleteCustomMonitor, runCustomMonitorNow, runCustomCheck } from '../api/endpoints'
import { toast } from 'sonner'
import HealthBadge from '../components/HealthBadge'
import MetricChart from '../components/MetricChart'
import RefreshBar from '../components/RefreshBar'
import SeverityBadge from '../components/SeverityBadge'
import { useAutoRefresh } from '../hooks/useAutoRefresh'
import { EmptyState, LoadingState, PageHeader, formatDateTime, formatNumber } from '../components/app-ui'
import { notify } from '@/lib/notify'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

// ── AI Monitor Recommender ────────────────────────────────────────────────────

function friendlyRecommendError(err) {
  const detail = err?.response?.data?.detail || err?.message || ''
  const lower = detail.toLowerCase()
  if (lower.includes('failed to resolve host') || lower.includes('unreachable') || lower.includes('connection refused') || lower.includes('timed out')) {
    return 'Cannot reach the data source. Check your connection settings.'
  }
  return 'Recommendations temporarily unavailable. You can set up monitoring manually.'
}

const SEVERITY_COLORS = { P1: 'text-red-600 dark:text-red-400', P2: 'text-orange-600 dark:text-orange-400', P3: 'text-yellow-600 dark:text-yellow-400' }

function quoteSqlIdent(identifier) {
  return `"${String(identifier || '').replaceAll('"', '""')}"`
}

function qualifiedTableName(tableName) {
  const parts = String(tableName || '').split('.').filter(Boolean)
  if (parts.length >= 2) return `${quoteSqlIdent(parts[0])}.${quoteSqlIdent(parts.slice(1).join('.'))}`
  return quoteSqlIdent(parts[0] || tableName)
}

function intervalFromConfig(config = {}) {
  const raw = config.max_lag || config.max_age || config.max_age_hours || config.max_lag_hours || '24 hours'
  if (typeof raw === 'number') return `${raw} hours`
  const text = String(raw).trim()
  if (/^\d+$/.test(text)) return `${text} hours`
  if (/^\d+\s*(m|min|minute|minutes)$/i.test(text)) return text.replace(/m$/i, ' minutes')
  if (/^\d+\s*(h|hr|hour|hours)$/i.test(text)) return text.replace(/h$/i, ' hours').replace(/hr$/i, ' hours')
  if (/^\d+\s*(d|day|days)$/i.test(text)) return text.replace(/d$/i, ' days')
  return '24 hours'
}

function recommendationSql(rec, tableName) {
  const table = qualifiedTableName(tableName)
  const column = rec.column_name ? quoteSqlIdent(rec.column_name) : null
  const config = rec.config || {}

  if (rec.monitor_type === 'null_rate' && column) {
    return `SELECT COUNT(*) AS violations FROM ${table} WHERE ${column} IS NULL`
  }
  if (rec.monitor_type === 'row_count') {
    const minRows = Number.isFinite(Number(config.min_rows ?? config.min_threshold))
      ? Number(config.min_rows ?? config.min_threshold)
      : 1
    return `SELECT CASE WHEN COUNT(*) < ${minRows} THEN 1 ELSE 0 END AS violations FROM ${table}`
  }
  if (rec.monitor_type === 'duplicate') {
    const columns = Array.isArray(config.key_columns) && config.key_columns.length > 0
      ? config.key_columns
      : rec.column_name ? [rec.column_name] : []
    if (columns.length === 0) return ''
    const groupBy = columns.map(quoteSqlIdent).join(', ')
    return `SELECT COUNT(*) AS violations FROM (SELECT ${groupBy} FROM ${table} GROUP BY ${groupBy} HAVING COUNT(*) > 1) duplicate_keys`
  }
  if (rec.monitor_type === 'freshness' && column) {
    return `SELECT CASE WHEN MAX(${column}) IS NULL OR MAX(${column}) < NOW() - INTERVAL '${intervalFromConfig(config)}' THEN 1 ELSE 0 END AS violations FROM ${table}`
  }
  if (rec.monitor_type === 'value_range' && column) {
    const clauses = []
    if (config.min_value != null && config.min_value !== '') clauses.push(`${column} < ${Number(config.min_value)}`)
    if (config.max_value != null && config.max_value !== '' && String(config.max_value).toUpperCase() !== 'NOW()') clauses.push(`${column} > ${Number(config.max_value)}`)
    if (String(config.max_value).toUpperCase() === 'NOW()') clauses.push(`${column} > NOW()`)
    if (clauses.length === 0) return ''
    return `SELECT COUNT(*) AS violations FROM ${table} WHERE ${clauses.join(' OR ')}`
  }
  return ''
}

function AIMonitorRecommender({ tableId, sourceId, tableName, hasMonitors, onMonitorSaved }) {
  const [recs, setRecs] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dismissed, setDismissed] = useState(false)
  const [applying, setApplying] = useState({})
  const [applied, setApplied] = useState({})
  const dismissKey = `dw_rec_dismissed_${tableId}`

  // Auto-trigger when no monitors exist and not previously dismissed this session
  // Guard: only run once sourceId is resolved (table data has loaded)
  useEffect(() => {
    if (!sourceId) return
    if (hasMonitors) return
    if (sessionStorage.getItem(dismissKey)) return
    run()
  }, [tableId, sourceId, hasMonitors])

  const run = async () => {
    if (!sourceId) return
    setLoading(true); setError(''); setRecs(null)
    try {
      const r = await recommendMonitors(sourceId, {
        table_name: tableName.split('.')[1] || tableName,
        schema_name: tableName.split('.')[0] || 'public',
      })
      setRecs(r.data.recommendations || [])
    } catch (e) {
      setError(friendlyRecommendError(e))
    } finally { setLoading(false) }
  }

  const dismiss = () => {
    setDismissed(true)
    sessionStorage.setItem(dismissKey, '1')
  }

  const applyRec = async (rec, index) => {
    setApplying((prev) => ({ ...prev, [index]: true }))
    try {
      const sql = recommendationSql(rec, tableName)
      if (!sql) {
        notify.err('This recommendation needs manual setup before it can be saved as a SQL monitor.')
        return
      }
      await createCustomMonitor(tableId, {
        name: rec.name || `${rec.monitor_type} monitor`,
        description: rec.rationale || `AI recommended ${rec.monitor_type} monitor`,
        sql_query: sql,
        severity: rec.severity || 'P3',
        run_on_profile: true,
      })
      setApplied((prev) => ({ ...prev, [index]: true }))
      onMonitorSaved?.()
      notify.ok('Monitor added', rec.name)
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Failed to add monitor'
      notify.err(msg)
    } finally {
      setApplying((prev) => { const next = { ...prev }; delete next[index]; return next })
    }
  }

  if (dismissed && !recs && !loading) return null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          AI Monitor Recommendations
        </CardTitle>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={run} disabled={loading}>
            {loading ? <Loader2 className="size-3.5 animate-spin" /> : (recs ? 'Regenerate' : 'Generate')}
          </Button>
          <Button size="icon" variant="ghost" onClick={dismiss} aria-label="Dismiss recommendations">
            <X className="size-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="flex flex-col gap-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 animate-pulse rounded-lg border bg-muted/40" />
            ))}
          </div>
        )}
        {!loading && error && (
          <p className="text-sm text-muted-foreground">{error}</p>
        )}
        {!loading && !recs && !error && (
          <p className="text-sm text-muted-foreground">Click "Generate" to let AI analyze your table schema and suggest monitors.</p>
        )}
        {!loading && recs?.length === 0 && (
          <p className="text-sm text-muted-foreground">No recommendations generated for this table.</p>
        )}
        {!loading && recs && recs.length > 0 && (
          <div className="flex flex-col gap-2">
            {recs.map((r, i) => (
              <div key={i} className="rounded-lg border bg-muted/20 px-3 py-2.5 flex flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold ${SEVERITY_COLORS[r.severity] || ''}`}>{r.severity}</span>
                  <span className="text-sm font-medium">{r.name}</span>
                  <span className="rounded-full border px-2 py-0.5 text-xs font-mono">{r.monitor_type}</span>
                  <div className="ml-auto">
                    {applied[i] ? (
                      <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="size-3.5" /> Added
                      </span>
                    ) : (
                      <Button size="sm" variant="outline" disabled={applying[i]} onClick={() => applyRec(r, i)}>
                        {applying[i] ? <Loader2 className="size-3.5 animate-spin" /> : 'Add monitor'}
                      </Button>
                    )}
                  </div>
                </div>
                {r.rationale && <p className="text-xs text-muted-foreground">{r.rationale}</p>}
                {r.column_name && <p className="text-xs text-muted-foreground">Column: <code className="text-primary">{r.column_name}</code></p>}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Natural Language Rule Builder ─────────────────────────────────────────────

const SEVERITY_BADGE_CLASSES = {
  P1: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  P2: 'border-orange-600/25 bg-orange-600/10 text-orange-700 dark:text-orange-300',
  P3: 'border-yellow-600/25 bg-yellow-600/10 text-yellow-700 dark:text-yellow-300',
}

function NLRuleBuilder({ tableId, tableName, onMonitorSaved }) {
  const [rule, setRule] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showSaveForm, setShowSaveForm] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [sqlDraft, setSqlDraft] = useState('')
  const [severityDraft, setSeverityDraft] = useState('P3')
  const [lastTestedSql, setLastTestedSql] = useState('')

  const generate = async (e) => {
    e.preventDefault()
    if (!rule.trim()) return
    setLoading(true); setError(''); setResult(null); setTestResult(null); setShowSaveForm(false); setSqlDraft(''); setLastTestedSql('')
    try {
      const r = await nlRule(tableId, { rule, table_name: tableName })
      setResult(r.data)
      setSqlDraft(r.data.sql || '')
      setSeverityDraft(r.data.severity || 'P3')
      setSaveName(rule)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to generate SQL — LLM key may not be configured.')
    } finally { setLoading(false) }
  }

  const testSql = async () => {
    const sql = sqlDraft.trim()
    if (!sql) return
    setTesting(true); setTestResult(null)
    try {
      const r = await runCustomCheck(tableId, { sql, name: rule, severity: severityDraft })
      setTestResult(r.data)
      setLastTestedSql(sql)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test run failed')
    } finally { setTesting(false) }
  }

  const saveAsMonitor = async () => {
    const sql = sqlDraft.trim()
    if (!sql || !saveName.trim() || lastTestedSql !== sql || !testResult) return
    setSaving(true)
    try {
      await createCustomMonitor(tableId, {
        name: saveName.trim(),
        sql_query: sql,
        severity: severityDraft,
        description: [rule, result?.explanation].filter(Boolean).join(' — '),
        run_on_profile: true,
      })
      toast.success('Monitor saved successfully')
      setShowSaveForm(false)
      setResult(null)
      setRule('')
      setTestResult(null)
      setSqlDraft('')
      setLastTestedSql('')
      onMonitorSaved?.()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to save monitor')
    } finally { setSaving(false) }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2"><Wand2 className="size-4 text-primary" />Natural Language Rule Builder</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">Describe a business rule in plain English. AI converts it to a SQL check that counts violations.</p>
        <form onSubmit={generate} className="flex gap-2">
          <input
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
            placeholder="e.g. Paid orders must have a payment reference"
            value={rule}
            onChange={e => setRule(e.target.value)}
          />
          <Button type="submit" size="sm" disabled={loading || !rule.trim()}>
            {loading ? <><Loader2 className="size-3.5 animate-spin mr-1" />Generating…</> : 'Generate'}
          </Button>
        </form>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {result?.sql && (
          <div className="flex flex-col gap-3">
            <div className="rounded-lg bg-muted/60 border p-3">
              <div className="flex items-center gap-2 mb-2">
                <Code2 className="size-3.5 text-muted-foreground" />
                <label htmlFor="nl-generated-sql" className="text-xs text-muted-foreground font-semibold uppercase tracking-wide">Generated SQL (violation count)</label>
              </div>
              <textarea
                id="nl-generated-sql"
                aria-label="Generated SQL"
                className="min-h-[96px] w-full resize-y rounded-md border bg-background px-3 py-2 text-xs font-mono leading-relaxed text-foreground outline-none focus:ring-1 focus:ring-primary"
                value={sqlDraft}
                onChange={(e) => {
                  setSqlDraft(e.target.value)
                  setTestResult(null)
                  setLastTestedSql('')
                }}
              />
            </div>
            {result.explanation && <p className="text-sm text-muted-foreground">{result.explanation}</p>}
            <div className="flex items-center gap-3 flex-wrap">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                Severity
                <select
                  className="rounded-md border bg-background px-2 py-1 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
                  value={severityDraft}
                  onChange={(e) => setSeverityDraft(e.target.value)}
                >
                  <option value="P1">P1</option>
                  <option value="P2">P2</option>
                  <option value="P3">P3</option>
                </select>
              </label>
              <Badge variant="outline" className={SEVERITY_BADGE_CLASSES[severityDraft] || ''}>
                {severityDraft}
              </Badge>
              {result.estimated_impact && (
                <span className="text-xs text-muted-foreground">Impact: {result.estimated_impact}</span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Button size="sm" variant="outline" onClick={testSql} disabled={testing || !sqlDraft.trim()}>
                {testing ? <Loader2 className="size-3.5 animate-spin mr-1" /> : <Play className="size-3.5 mr-1" />}
                Test SQL
              </Button>
              {testResult != null && (
                <span className={`text-sm font-medium flex items-center gap-1 ${testResult.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-orange-600 dark:text-orange-400'}`}>
                  {testResult.passed
                    ? <><CheckCircle2 className="size-4" /> 0 violations</>
                    : <><AlertTriangle className="size-4" /> {testResult.violation_count} violation{testResult.violation_count !== 1 ? 's' : ''} found</>
                  }
                </span>
              )}
              <Button size="sm" variant="outline" onClick={() => setShowSaveForm((v) => !v)}>
                <PlusCircle className="size-3.5 mr-1" />
                Save as Monitor
              </Button>
            </div>
            {showSaveForm && (
              <div className="rounded-lg border bg-muted/20 p-3 flex flex-col gap-2">
                <p className="text-xs font-medium text-muted-foreground">Monitor name</p>
                <div className="flex gap-2">
                  <input
                    className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                    value={saveName}
                    onChange={e => setSaveName(e.target.value)}
                    placeholder="Monitor name"
                  />
                  <Button size="sm" onClick={saveAsMonitor} disabled={saving || !saveName.trim() || lastTestedSql !== sqlDraft.trim() || !testResult}>
                    {saving ? <Loader2 className="size-3.5 animate-spin" /> : 'Save'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowSaveForm(false)}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Custom Monitors ───────────────────────────────────────────────────────────

function CustomMonitors({ tableId, refreshKey = 0 }) {
  const [monitors, setMonitors] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [runningId, setRunningId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [togglingId, setTogglingId] = useState(null)

  // Add form state
  const [addName, setAddName] = useState('')
  const [addDescription, setAddDescription] = useState('')
  const [addSql, setAddSql] = useState('')
  const [addSeverity, setAddSeverity] = useState('P3')
  const [addRunOnProfile, setAddRunOnProfile] = useState(true)
  const [addSaving, setAddSaving] = useState(false)
  const [addTesting, setAddTesting] = useState(false)
  const [addTestResult, setAddTestResult] = useState(null)
  const [addLastTestedSql, setAddLastTestedSql] = useState('')

  // Edit form state
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editSql, setEditSql] = useState('')
  const [editSeverity, setEditSeverity] = useState('P3')
  const [editRunOnProfile, setEditRunOnProfile] = useState(true)
  const [editSaving, setEditSaving] = useState(false)

  const load = async () => {
    try {
      const r = await getCustomMonitors(tableId)
      setMonitors(r.data)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to load custom monitors')
    } finally { setLoading(false) }
  }

  useEffect(() => { setLoading(true); load() }, [tableId, refreshKey])

  const resetAddForm = () => {
    setAddName(''); setAddDescription(''); setAddSql(''); setAddSeverity('P3'); setAddRunOnProfile(true)
    setAddTestResult(null); setAddLastTestedSql('')
    setShowAddForm(false)
  }

  const handleAddSqlChange = (value) => {
    setAddSql(value)
    setAddTestResult(null)
    setAddLastTestedSql('')
  }

  const addSqlTested = addSql.trim() && addLastTestedSql === addSql.trim() && addTestResult

  const testAddSql = async () => {
    const sql = addSql.trim()
    if (!sql) return
    setAddTesting(true)
    setAddTestResult(null)
    try {
      const r = await runCustomCheck(tableId, { sql, name: addName.trim() || 'Custom SQL monitor', severity: addSeverity })
      setAddTestResult(r.data)
      setAddLastTestedSql(sql)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test run failed')
    } finally {
      setAddTesting(false)
    }
  }

  const handleAdd = async (e) => {
    e.preventDefault()
    if (!addName.trim() || !addSql.trim() || !addSqlTested) return
    setAddSaving(true)
    try {
      await createCustomMonitor(tableId, {
        name: addName.trim(),
        description: addDescription.trim() || undefined,
        sql_query: addSql.trim(),
        severity: addSeverity,
        run_on_profile: addRunOnProfile,
      })
      toast.success('Monitor created')
      resetAddForm()
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to create monitor')
    } finally { setAddSaving(false) }
  }

  const startEdit = (m) => {
    setEditingId(m.id)
    setEditName(m.name)
    setEditDescription(m.description || '')
    setEditSql(m.sql_query)
    setEditSeverity(m.severity)
    setEditRunOnProfile(m.run_on_profile)
  }

  const handleEdit = async (e, monitorId) => {
    e.preventDefault()
    setEditSaving(true)
    try {
      await updateCustomMonitor(tableId, monitorId, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
        sql_query: editSql.trim(),
        severity: editSeverity,
        run_on_profile: editRunOnProfile,
      })
      toast.success('Monitor updated')
      setEditingId(null)
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to update monitor')
    } finally { setEditSaving(false) }
  }

  const handleToggle = async (m) => {
    setTogglingId(m.id)
    try {
      await updateCustomMonitor(tableId, m.id, { is_active: !m.is_active })
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to update monitor')
    } finally { setTogglingId(null) }
  }

  const handleRunNow = async (m) => {
    setRunningId(m.id)
    try {
      const r = await runCustomMonitorNow(tableId, m.id)
      const d = r.data
      if (d.error) {
        toast.error(`Run error: ${d.error}`)
      } else if (d.passed) {
        toast.success(`${m.name}: 0 violations`)
      } else {
        toast.warning(`${m.name}: ${d.violation_count} violation${d.violation_count !== 1 ? 's' : ''} found`)
      }
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Run failed')
    } finally { setRunningId(null) }
  }

  const handleDelete = async (m) => {
    if (!window.confirm(`Delete monitor "${m.name}"? This cannot be undone.`)) return
    setDeletingId(m.id)
    try {
      await deleteCustomMonitor(tableId, m.id)
      toast.success('Monitor deleted')
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to delete monitor')
    } finally { setDeletingId(null) }
  }

  const renderLastResult = (m) => {
    if (!m.last_run_at) return <span className="text-xs text-muted-foreground">Never run</span>
    if (m.last_result == null) return <span className="text-xs text-muted-foreground">—</span>
    const passed = m.last_result?.passed ?? (m.last_result?.violation_count === 0)
    const count = m.last_result?.violation_count ?? 0
    return passed
      ? <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400"><CheckCircle2 className="size-3.5" />passed</span>
      : <span className="inline-flex items-center gap-1 text-xs text-orange-600 dark:text-orange-400"><AlertTriangle className="size-3.5" />{count} violations</span>
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <Code2 className="size-4 text-primary" />
          Custom SQL Monitors
        </CardTitle>
        <Button size="sm" variant="outline" onClick={() => { setShowAddForm((v) => !v); setEditingId(null) }}>
          <PlusCircle className="size-3.5 mr-1" />
          Add monitor
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {showAddForm && (
          <form onSubmit={handleAdd} className="rounded-lg border bg-muted/20 p-4 flex flex-col gap-3">
            <p className="text-sm font-medium">New custom monitor</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">Name *</label>
                <input
                  className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                  value={addName} onChange={e => setAddName(e.target.value)}
                  placeholder="e.g. Paid orders without reference" required
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground font-medium">Severity</label>
                <select
                  className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                  value={addSeverity} onChange={e => setAddSeverity(e.target.value)}
                >
                  <option value="P1">P1 — Critical</option>
                  <option value="P2">P2 — High</option>
                  <option value="P3">P3 — Medium</option>
                </select>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground font-medium">Description (optional)</label>
              <input
                className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                value={addDescription} onChange={e => setAddDescription(e.target.value)}
                placeholder="What does this check detect?"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground font-medium">SQL query * (must return a count of violations)</label>
              <textarea
                className="rounded-md border bg-background px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-primary min-h-[80px] resize-y"
                value={addSql} onChange={e => handleAddSqlChange(e.target.value)}
                placeholder="SELECT COUNT(*) FROM orders WHERE status = 'paid' AND payment_reference IS NULL"
                required
              />
            </div>
            {addTestResult && (
              <span className={`text-sm font-medium flex items-center gap-1 ${addTestResult.passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-orange-600 dark:text-orange-400'}`}>
                {addTestResult.passed
                  ? <><CheckCircle2 className="size-4" /> 0 violations</>
                  : <><AlertTriangle className="size-4" /> {addTestResult.violation_count} violation{addTestResult.violation_count !== 1 ? 's' : ''} found</>
                }
              </span>
            )}
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={addRunOnProfile} onChange={e => setAddRunOnProfile(e.target.checked)} className="rounded" />
              Run on every profile
            </label>
            <div className="flex gap-2">
              <Button type="button" size="sm" variant="outline" onClick={testAddSql} disabled={addTesting || !addSql.trim()}>
                {addTesting ? <Loader2 className="size-3.5 animate-spin" /> : 'Test SQL'}
              </Button>
              <Button type="submit" size="sm" disabled={addSaving || !addName.trim() || !addSql.trim() || !addSqlTested}>
                {addSaving ? <Loader2 className="size-3.5 animate-spin" /> : 'Save monitor'}
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={resetAddForm}>Cancel</Button>
            </div>
          </form>
        )}

        {loading && <div className="flex flex-col gap-2">{[1, 2].map(i => <div key={i} className="h-12 animate-pulse rounded-lg border bg-muted/40" />)}</div>}

        {!loading && monitors.length === 0 && !showAddForm && (
          <p className="text-sm text-muted-foreground">No custom SQL monitors yet. Click "Add monitor" to create one.</p>
        )}

        {!loading && monitors.length > 0 && (
          <div className="flex flex-col gap-2">
            {monitors.map((m) => (
              <div key={m.id} className="rounded-lg border bg-muted/10">
                {editingId === m.id ? (
                  <form onSubmit={(e) => handleEdit(e, m.id)} className="p-4 flex flex-col gap-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-muted-foreground font-medium">Name *</label>
                        <input
                          className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                          value={editName} onChange={e => setEditName(e.target.value)} required
                        />
                      </div>
                      <div className="flex flex-col gap-1">
                        <label className="text-xs text-muted-foreground font-medium">Severity</label>
                        <select
                          className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                          value={editSeverity} onChange={e => setEditSeverity(e.target.value)}
                        >
                          <option value="P1">P1 — Critical</option>
                          <option value="P2">P2 — High</option>
                          <option value="P3">P3 — Medium</option>
                        </select>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs text-muted-foreground font-medium">Description (optional)</label>
                      <input
                        className="rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary"
                        value={editDescription} onChange={e => setEditDescription(e.target.value)}
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs text-muted-foreground font-medium">SQL query *</label>
                      <textarea
                        className="rounded-md border bg-background px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-primary min-h-[80px] resize-y"
                        value={editSql} onChange={e => setEditSql(e.target.value)} required
                      />
                    </div>
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                      <input type="checkbox" checked={editRunOnProfile} onChange={e => setEditRunOnProfile(e.target.checked)} className="rounded" />
                      Run on every profile
                    </label>
                    <div className="flex gap-2">
                      <Button type="submit" size="sm" disabled={editSaving}>
                        {editSaving ? <Loader2 className="size-3.5 animate-spin" /> : 'Update'}
                      </Button>
                      <Button type="button" size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                    </div>
                  </form>
                ) : (
                  <div className="px-3 py-2.5 flex flex-col gap-1.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant="outline" className={SEVERITY_BADGE_CLASSES[m.severity] || ''}>
                        {m.severity}
                      </Badge>
                      <span className="text-sm font-medium">{m.name}</span>
                      {m.description && <span className="text-xs text-muted-foreground hidden sm:inline">— {m.description}</span>}
                      <div className="ml-auto flex items-center gap-2">
                        {renderLastResult(m)}
                        <button
                          type="button"
                          onClick={() => handleToggle(m)}
                          disabled={togglingId === m.id}
                          className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${m.is_active
                            ? 'border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-600/20'
                            : 'border-stone-500/30 bg-stone-500/10 text-stone-600 dark:text-stone-400 hover:bg-stone-500/20'
                          }`}
                        >
                          {togglingId === m.id ? '…' : m.is_active ? 'active' : 'inactive'}
                        </button>
                        <Button size="sm" variant="ghost" onClick={() => handleRunNow(m)} disabled={runningId === m.id} className="h-7 px-2">
                          {runningId === m.id ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => startEdit(m)} className="h-7 px-2">
                          <Edit3 className="size-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleDelete(m)} disabled={deletingId === m.id} className="h-7 px-2 text-destructive hover:text-destructive">
                          {deletingId === m.id ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                        </Button>
                      </div>
                    </div>
                    {m.last_run_at && (
                      <p className="text-xs text-muted-foreground">Last run: {formatDateTime(m.last_run_at)}</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

const NULL_RATE_STYLES = {
  good: 'border-emerald-600/25 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300',
  warning: 'border-amber-600/25 bg-amber-500/12 text-amber-700 dark:text-amber-300',
  bad: 'border-red-600/25 bg-red-600/10 text-red-700 dark:text-red-300',
  unknown: 'border-stone-500/25 bg-stone-500/10 text-stone-700 dark:text-stone-300',
}

function formatPercent(value, digits = 1) {
  return value == null ? '-' : `${(Number(value) * 100).toFixed(digits)}%`
}

function formatMetricValue(value) {
  if (value == null || value === '') return '-'
  if (typeof value === 'number') return Number.isInteger(value) ? formatNumber(value) : value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return String(value)
}

function nullRateTone(value) {
  if (value == null) return 'unknown'
  if (value < 0.01) return 'good'
  if (value <= 0.05) return 'warning'
  return 'bad'
}

function inferTypeHint(metric = {}) {
  if (['mean', 'stddev', 'p25', 'p50', 'p75', 'p95', 'zero_rate', 'negative_rate'].some((key) => metric[key] != null)) return 'numeric'
  if (metric.range_seconds != null) return 'timestamp'
  if (['min_len', 'max_len', 'avg_len', 'empty_rate'].some((key) => metric[key] != null)) return 'text'
  const values = [metric.min, metric.max].filter(Boolean)
  if (values.some((value) => !Number.isNaN(Date.parse(value)))) return 'timestamp'
  return 'text'
}

function formatTopValues(metric = {}) {
  const values = metric.top_values ?? metric.top_values_count ?? metric.value_counts ?? metric.most_common
  if (!values) return '-'
  if (Array.isArray(values)) {
    return values
      .slice(0, 3)
      .map((item) => {
        if (Array.isArray(item)) return `${formatMetricValue(item[0])} (${formatNumber(item[1])})`
        if (item && typeof item === 'object') return `${formatMetricValue(item.value ?? item.key)} (${formatNumber(item.count ?? item.frequency)})`
        return formatMetricValue(item)
      })
      .join(', ')
  }
  if (typeof values === 'object') {
    return Object.entries(values)
      .slice(0, 3)
      .map(([value, count]) => `${formatMetricValue(value)} (${formatNumber(count)})`)
      .join(', ')
  }
  return formatMetricValue(values)
}

function StatCard({ label, value, detail, trend }) {
  const TrendIcon = trend?.direction === 'up' ? ArrowUp : trend?.direction === 'down' ? ArrowDown : ArrowRight

  return (
    <Card size="sm">
      <CardContent className="flex min-h-28 flex-col justify-between gap-3">
        <div className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</div>
        <div>
          <div className="break-words text-xl font-semibold tabular-nums text-foreground">{value}</div>
          {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
        </div>
        {trend && (
          <div className={trend.className}>
            <TrendIcon className="size-3.5" />
            <span>{trend.label}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function TableDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [table, setTable] = useState(null)
  const [sources, setSources] = useState([])
  const [profiles, setProfiles] = useState([])
  const [checks, setChecks] = useState([])
  const [incidents, setIncidents] = useState([])
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(true)
  const [interval, setInterval_] = useState(15000)
  const [customMonitorsRefreshKey, setCustomMonitorsRefreshKey] = useState(0)

  const loadData = async () => {
    const [tableResponse, sourcesResponse, profilesResponse, checksResponse, incidentsResponse] = await Promise.all([
      getTable(id),
      getSources(),
      getTableProfiles(id, { limit: 30 }),
      getTableCheckResults(id, { limit: 100 }),
      getIncidents({ table_id: id, limit: 100 }),
    ])
    setTable(tableResponse.data)
    setSources(sourcesResponse.data)
    setProfiles(profilesResponse.data)
    setChecks(checksResponse.data)
    setIncidents(incidentsResponse.data)
    setLoading(false)
  }

  const { isRefreshing, lastRefreshed, refresh } = useAutoRefresh(loadData, interval, { enabled: interval > 0 })

  const handleRun = async () => {
    const clickedAt = new Date()
    setRunning(true)
    try {
      await runTable(id)
      // Poll for completion every 2s
      const poll = setInterval(async () => {
        try {
          const res = await getTableProfiles(id, { limit: 1 })
          const latest = res.data?.[0]
          if (latest && new Date(latest.collected_at) > clickedAt) {
            clearInterval(poll)
            setRunning(false)
            await loadData()
            notify.ok('Profile complete — data updated')
          }
        } catch (_) { /* ignore poll errors */ }
      }, 2000)
      // Safety timeout after 90s
      setTimeout(() => { clearInterval(poll); setRunning(false) }, 90000)
    } catch (_) {
      setRunning(false)
    }
  }

  const profileSeries = useMemo(
    () => [...profiles].sort((a, b) => new Date(a.collected_at) - new Date(b.collected_at)),
    [profiles]
  )
  const profilesDesc = useMemo(
    () => [...profiles].sort((a, b) => new Date(b.collected_at) - new Date(a.collected_at)),
    [profiles]
  )

  if (loading) return <LoadingState label="Loading table detail" />
  if (!table) return <div className="dw-page text-destructive">Table not found</div>

  const latestProfile = table.latest_profile
  const source = sources.find((item) => item.id === table.source_id)
  const sourceName = table.source_name || table.source?.name || source?.name || table.source_id
  const columnMetrics = latestProfile?.column_metrics || {}
  const columnRows = Object.entries(columnMetrics)
    .map(([name, metric]) => ({ name, metric: metric || {}, nullRate: metric?.null_rate ?? null }))
    .sort((a, b) => (b.nullRate ?? -1) - (a.nullRate ?? -1))
  const nullRates = columnRows.map((row) => row.nullRate).filter((value) => value != null)
  const avgNullRate = nullRates.length ? nullRates.reduce((sum, value) => sum + Number(value), 0) / nullRates.length : null
  const activeIncidents = incidents.filter((incident) => incident.status !== 'resolved')
  const anomalousProfileIds = new Set(checks.filter((check) => check.status === 'failed').map((check) => check.profile_id))
  const anomalousDots = profileSeries.filter((profile) => anomalousProfileIds.has(profile.id))
  const previousProfile = profilesDesc.find((profile) => profile.id !== latestProfile?.id && profile.row_count != null)
  const rowDelta = latestProfile?.row_count != null && previousProfile?.row_count != null ? latestProfile.row_count - previousProfile.row_count : null
  const rowDeltaPct = rowDelta != null && previousProfile.row_count !== 0 ? rowDelta / previousProfile.row_count : null
  const latestChecks = checks
    .filter((check) => !latestProfile?.id || check.profile_id === latestProfile.id)
    .slice(0, 10)
  const rowTrend = rowDelta == null ? null : {
    direction: rowDelta > 0 ? 'up' : rowDelta < 0 ? 'down' : 'flat',
    label: `${rowDelta > 0 ? '+' : ''}${formatNumber(rowDelta)} (${rowDeltaPct == null ? '-' : formatPercent(rowDeltaPct)}) vs previous`,
    className: rowDelta > 0
      ? 'inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-300'
      : rowDelta < 0
        ? 'inline-flex items-center gap-1 text-xs text-red-700 dark:text-red-300'
        : 'inline-flex items-center gap-1 text-xs text-muted-foreground',
  }

  return (
    <div className="dw-page">
      <Button type="button" variant="ghost" className="w-fit" onClick={() => nav(-1)}>
        <ArrowLeft data-icon="inline-start" />
        Back
      </Button>

      <PageHeader
        title={`${table.schema_name}.${table.table_name}`}
        description={`${sourceName} - Every ${table.check_interval_minutes}m${latestProfile ? ` - Last profiled ${formatDateTime(table.last_profiled_at || latestProfile.collected_at)}` : ''}`}
        actions={
          <>
            <RefreshBar
              isRefreshing={isRefreshing}
              lastRefreshed={lastRefreshed}
              onRefresh={refresh}
              interval={interval}
              onIntervalChange={setInterval_}
            />
            <HealthBadge status={table.is_active ? 'healthy' : 'paused'} size="lg" />
            <Button type="button" onClick={handleRun} disabled={running}>
              <Play data-icon="inline-start" />
              {running ? 'Profiling…' : 'Run now'}
            </Button>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Row Count" value={formatNumber(latestProfile?.row_count)} detail="Latest profile" trend={rowTrend} />
        <StatCard label="Freshness" value={formatDateTime(table.last_profiled_at || latestProfile?.collected_at)} detail="Last profiled at" />
        <StatCard label="Null Rate" value={formatPercent(avgNullRate)} detail={`Average across ${formatNumber(columnRows.length)} columns`} />
        <StatCard label="Active Incidents" value={formatNumber(activeIncidents.length)} detail={`${formatNumber(incidents.length)} total incidents`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Row count, 30 profiles</CardTitle>
          </CardHeader>
          <CardContent>
            <MetricChart data={profileSeries} dataKey="row_count" anomalies={anomalousDots} label="rows" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Profile history</CardTitle>
          </CardHeader>
          <CardContent>
            <MetricChart data={profileSeries} dataKey="freshness_seconds" color="hsl(var(--chart-2))" label="seconds" />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Column metrics</CardTitle>
        </CardHeader>
        <CardContent>
          {columnRows.length === 0 ? (
            <EmptyState title="No column metrics yet" description="The latest profile has not captured column-level metrics." />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Column Name</TableHead>
                    <TableHead>Type hint</TableHead>
                    <TableHead>Null Rate</TableHead>
                    <TableHead>Distinct Count</TableHead>
                    <TableHead>Top Values</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {columnRows.map(({ name, metric, nullRate }) => (
                    <TableRow key={name}>
                      <TableCell className="font-mono text-xs">{name}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">{inferTypeHint(metric)}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={NULL_RATE_STYLES[nullRateTone(nullRate)]}>
                          {formatPercent(nullRate)}
                        </Badge>
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">{formatNumber(metric.distinct_count)}</TableCell>
                      <TableCell className="max-w-[28rem] truncate text-muted-foreground">{formatTopValues(metric)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Check results</CardTitle>
        </CardHeader>
        <CardContent>
          {latestChecks.length === 0 ? (
            <EmptyState title="No check results for the latest profile" description="Checks have not completed for this profile yet." />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Check</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Observed Value</TableHead>
                    <TableHead>Checked At</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {latestChecks.map((check) => (
                    <TableRow key={check.id}>
                      <TableCell className="font-mono text-xs">{check.check_name}</TableCell>
                      <TableCell><HealthBadge status={check.status} /></TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">{formatMetricValue(check.observed_value)}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTime(check.checked_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── AI: Monitor Recommender ── */}
      <AIMonitorRecommender
        tableId={id}
        sourceId={table.source_id}
        tableName={`${table.schema_name}.${table.table_name}`}
        hasMonitors={checks.length > 0}
        onMonitorSaved={() => setCustomMonitorsRefreshKey((key) => key + 1)}
      />

      {/* ── NL Rule Builder ── */}
      <NLRuleBuilder
        tableId={id}
        tableName={`${table.schema_name}.${table.table_name}`}
        onMonitorSaved={() => setCustomMonitorsRefreshKey((key) => key + 1)}
      />

      {/* ── Custom SQL Monitors ── */}
      <CustomMonitors tableId={id} refreshKey={customMonitorsRefreshKey} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Incident history</CardTitle>
        </CardHeader>
        <CardContent>
          {incidents.length === 0 ? (
            <EmptyState title="No incidents for this table" description="Profiles have not created incidents for this table yet." />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Severity</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {incidents.map((incident) => (
                    <TableRow key={incident.id} className="cursor-pointer" onClick={() => nav(`/incidents/${incident.id}`)}>
                      <TableCell><SeverityBadge severity={incident.severity} /></TableCell>
                      <TableCell className="font-medium">{incident.title}</TableCell>
                      <TableCell><HealthBadge status={incident.status} /></TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTime(incident.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
