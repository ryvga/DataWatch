import { useEffect, useRef, useState } from 'react'
import { PayPalButtons, PayPalScriptProvider } from '@paypal/react-paypal-js'
import { notify } from '@/lib/notify'
import {
  AlertCircle,
  Bell,
  CheckCircle2,
  CreditCard,
  Database,
  Info,
  KeyRound,
  Lock,
  Loader2,
  MoreHorizontal,
  Pencil,
  Play,
  Plus,
  Send,
  Table2,
  Trash2,
  User,
  Users,
  XCircle,
} from 'lucide-react'
import {
  cancelBillingSubscription,
  captureBillingSubscription,
  changePassword,
  createAlert,
  createBillingSubscription,
  createInvite,
  createSource,
  createTable,
  deleteAlert,
  deleteSource,
  deleteTable,
  discoverSource,
  getAlerts,
  getAlertChannels,
  getBillingStatus,
  getConnectorTypes,
  getInvites,
  getMe,
  getOrgMembers,
  getSources,
  getSourceTableSchema,
  getTableProfiles,
  getTables,
  revokeInvite,
  runTable,
  testAlert,
  testSource,
  testSourceConfig,
  updateProfile,
  updateSource,
  updateTable,
  getNotificationPrefs,
  updateNotificationPrefs,
} from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import { EmptyState, PageHeader } from '../components/app-ui'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { storage } from '@/lib/storage'
import { FALLBACK_CONNECTORS, castFieldValue, defaultConfigFor, extractColumnsFromDDL, freshnessCandidates, normalizeConnector } from '@/lib/connectorConfig'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import SourceConnectionDialog from '@/components/SourceConnectionDialog'
import TableSetupDialog from '@/components/TableSetupDialog'

const SOURCE_TYPES = ['postgres', 'mysql', 'mongodb', 'cassandra', 'redshift', 'bigquery', 'snowflake', 'clickhouse', 'sqlserver', 'databricks', 'trino', 'duckdb', 'sqlite']

const SOURCE_TYPE_LABELS = {
  postgres: 'PostgreSQL',
  mysql: 'MySQL / MariaDB',
  mongodb: 'MongoDB',
  cassandra: 'Cassandra',
  redshift: 'Amazon Redshift',
  bigquery: 'Google BigQuery',
  snowflake: 'Snowflake',
  clickhouse: 'ClickHouse',
  sqlserver: 'SQL Server',
  databricks: 'Databricks',
  trino: 'Trino / Presto',
  duckdb: 'DuckDB',
  sqlite: 'SQLite',
}
const SOURCE_CONFIG_TEMPLATES = {
  postgres: '{\n  "host": "localhost",\n  "port": 5432,\n  "database": "mydb",\n  "username": "user",\n  "password": ""\n}',
  mysql: '{\n  "host": "localhost",\n  "port": 3306,\n  "database": "mydb",\n  "username": "root",\n  "password": ""\n}',
  redshift: '{\n  "host": "cluster.region.redshift.amazonaws.com",\n  "port": 5439,\n  "database": "dev",\n  "username": "awsuser",\n  "password": ""\n}',
  bigquery: '{\n  "project_id": "my-gcp-project",\n  "credentials_json": null\n}',
  snowflake: '{\n  "account": "xy12345.us-east-1",\n  "user": "MYUSER",\n  "password": "",\n  "database": "MYDB",\n  "warehouse": "COMPUTE_WH"\n}',
  mongodb: '{\n  "uri": "mongodb://user:pass@localhost:27017",\n  "database": "mydb"\n}',
  cassandra: '{\n  "hosts": "node1.cassandra.io,node2.cassandra.io",\n  "port": 9042,\n  "keyspace": "my_keyspace",\n  "username": "cassandra",\n  "password": ""\n}',
  sqlserver: '{\n  "host": "localhost",\n  "port": 1433,\n  "database": "MyDB",\n  "username": "sa",\n  "password": ""\n}',
  clickhouse: '{\n  "host": "localhost",\n  "port": 8123,\n  "database": "default",\n  "username": "default",\n  "password": ""\n}',
  databricks: '{\n  "server_hostname": "adb-xxx.azuredatabricks.net",\n  "http_path": "/sql/1.0/warehouses/xxx",\n  "access_token": "dapi...",\n  "catalog": "hive_metastore"\n}',
  trino: '{\n  "host": "localhost",\n  "port": 8080,\n  "user": "trino",\n  "catalog": "tpch",\n  "schema": "tiny",\n  "http_scheme": "http"\n}',
  duckdb: '{\n  "path": ":memory:"\n}',
  sqlite: '{\n  "path": "/data/mydb.sqlite"\n}',
}

// Full channel list — availability is determined at runtime from /api/v1/alerts/channels
// This fallback is used only when the API call fails.
// All plans: email=free, slack/webhook=starter, pagerduty/teams/discord/opsgenie=growth
const FALLBACK_ALERT_CHANNELS = [
  {
    id: 'email',
    label: 'Email',
    available: true,
    required_plan: 'free',
    description: 'Send incidents to one or more email recipients.',
    fields: [
      { name: 'to', label: 'Recipients', type: 'email_list', required: true },
      { name: 'min_severity', label: 'Minimum severity', type: 'severity', required: false },
    ],
  },
  {
    id: 'slack',
    label: 'Slack',
    available: true,
    required_plan: 'starter',
    description: 'Post incident cards into a Slack channel via incoming webhook.',
    fields: [
      { name: 'webhook_url', label: 'Webhook URL', type: 'url', required: true, secret: true },
      { name: 'min_severity', label: 'Minimum severity', type: 'severity', required: false },
    ],
  },
  {
    id: 'webhook',
    label: 'Generic webhook',
    available: true,
    required_plan: 'starter',
    description: 'POST a signed JSON payload to your incident automation endpoint.',
    fields: [
      { name: 'url', label: 'Endpoint URL', type: 'url', required: true },
      { name: 'secret', label: 'Signing secret', type: 'text', required: false, secret: true },
      { name: 'min_severity', label: 'Minimum severity', type: 'severity', required: false },
    ],
  },
  {
    id: 'pagerduty',
    label: 'PagerDuty',
    available: true,
    required_plan: 'growth',
    description: 'Trigger PagerDuty Events API incidents for urgent Panopta incidents.',
    fields: [
      { name: 'routing_key', label: 'Routing key', type: 'password', required: true, secret: true },
      { name: 'min_severity', label: 'Minimum severity', type: 'severity', required: false },
    ],
  },
  {
    id: 'teams',
    label: 'Microsoft Teams',
    available: true,
    required_plan: 'growth',
    description: 'Post incident cards to a Teams incoming webhook.',
    fields: [
      { name: 'webhook_url', label: 'Webhook URL', type: 'url', required: true, secret: true },
      { name: 'min_severity', label: 'Minimum severity', type: 'severity', required: false },
    ],
  },
  {
    id: 'discord',
    label: 'Discord',
    available: true,
    required_plan: 'growth',
    description: 'Post incident embeds to a Discord webhook.',
    fields: [
      { name: 'webhook_url', label: 'Webhook URL', type: 'url', required: true, secret: true },
      { name: 'min_severity', label: 'Minimum severity', type: 'severity', required: false },
    ],
  },
  {
    id: 'opsgenie',
    label: 'OpsGenie',
    available: true,
    required_plan: 'growth',
    description: 'Create OpsGenie alerts for incident response teams.',
    fields: [
      { name: 'api_key', label: 'API key', type: 'password', required: true, secret: true },
      { name: 'min_severity', label: 'Minimum severity', type: 'severity', required: false },
    ],
  },
]

function defaultAlertFields(channel) {
  const fields = { min_severity: 'P3' }
  for (const field of channel?.fields || []) {
    if (field.name === 'min_severity') fields.min_severity = 'P3'
    else if (field.type === 'email_list') fields[field.name] = storage.getItem('dw_user_email') || ''
    else fields[field.name] = ''
  }
  return fields
}

function alertPayloadFields(fields, channel) {
  const payload = {}
  for (const field of channel?.fields || []) {
    const value = fields[field.name]
    if (field.type === 'email_list') {
      payload[field.name] = String(value || '').split(',').map((item) => item.trim()).filter(Boolean)
    } else if (field.name === 'min_severity') {
      payload[field.name] = value || 'P3'
    } else if (value || field.required) {
      payload[field.name] = value
    }
  }
  return payload
}

function alertDestination(alert) {
  const config = alert.config || {}
  if (alert.channel === 'email') return Array.isArray(config.to) ? config.to.join(', ') : 'Email recipients'
  if (alert.channel === 'webhook') return config.url || 'Webhook endpoint'
  if (['slack', 'teams', 'discord'].includes(alert.channel)) return config.webhook_url || 'Webhook URL saved'
  if (alert.channel === 'pagerduty') return 'Routing key saved'
  if (alert.channel === 'opsgenie') return 'API key saved'
  return 'Configured'
}

function NotificationsTab() {
  const [prefs, setPrefs] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    getNotificationPrefs()
      .then(r => setPrefs(r.data))
      .catch(() => setPrefs({ notify_assigned: true, notify_team: true, notify_status_change: true, daily_digest: false, digest_hour: 8 }))
      .finally(() => setLoading(false))
  }, [])

  const update = (key, value) => setPrefs(prev => ({ ...prev, [key]: value }))

  const save = async () => {
    if (!prefs) return
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      await updateNotificationPrefs(prefs)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save preferences')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="text-gray-500 text-sm">Loading…</div>

  const PREF_ROWS = [
    { key: 'notify_assigned', label: 'Incident assigned to me', desc: 'Email when an incident is directly assigned to you.' },
    { key: 'notify_team', label: 'Team incident assigned', desc: 'Email when an incident is assigned to one of your teams.' },
    { key: 'notify_status_change', label: 'Incident status changes', desc: 'Email when an incident you are involved with changes status.' },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
        🔔 Email Notifications
      </h2>
      <p className="text-xs text-gray-500">Choose which events trigger email notifications to you.</p>

      <div className="card space-y-4">
        {PREF_ROWS.map(({ key, label, desc }) => (
          <div key={key} className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-200">{label}</p>
              <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
            </div>
            <label className="flex items-center cursor-pointer shrink-0">
              <input
                type="checkbox"
                className="sr-only"
                checked={prefs?.[key] ?? true}
                onChange={e => update(key, e.target.checked)}
              />
              <div className={`relative w-9 h-5 rounded-full transition-colors ${
                prefs?.[key] ? 'bg-blue-600' : 'bg-gray-700'
              }`}>
                <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                  prefs?.[key] ? 'translate-x-4' : ''
                }`} />
              </div>
            </label>
          </div>
        ))}

        <div className="border-t border-gray-800 pt-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-200">Daily digest email</p>
              <p className="text-xs text-gray-500 mt-0.5">Receive a morning summary of open incidents and resolved issues.</p>
            </div>
            <label className="flex items-center cursor-pointer shrink-0">
              <input
                type="checkbox"
                className="sr-only"
                checked={prefs?.daily_digest ?? false}
                onChange={e => update('daily_digest', e.target.checked)}
              />
              <div className={`relative w-9 h-5 rounded-full transition-colors ${
                prefs?.daily_digest ? 'bg-blue-600' : 'bg-gray-700'
              }`}>
                <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                  prefs?.daily_digest ? 'translate-x-4' : ''
                }`} />
              </div>
            </label>
          </div>
          {prefs?.daily_digest && (
            <div className="mt-3 flex items-center gap-3">
              <label className="text-sm text-gray-500 shrink-0">Send at (UTC hour):</label>
              <select
                className="input w-36"
                value={String(prefs?.digest_hour ?? 8)}
                onChange={e => update('digest_hour', parseInt(e.target.value))}
              >
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={String(i)}>
                    {String(i).padStart(2, '0')}:00 UTC
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {prefs?.mute_until && new Date(prefs.mute_until) > new Date() && (
          <div className="flex items-center gap-3 rounded-lg border border-yellow-700/40 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-400">
            ⚠️ All notifications muted until {new Date(prefs.mute_until).toLocaleString()}.
            <button
              type="button"
              className="ml-auto text-xs underline hover:no-underline"
              onClick={() => update('mute_until', null)}
            >
              Unmute
            </button>
          </div>
        )}

        {error && <p className="text-xs text-red-400">{error}</p>}
        {saved && <p className="text-xs text-green-400">Preferences saved.</p>}

        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="btn-primary text-xs w-fit"
        >
          {saving ? 'Saving…' : 'Save preferences'}
        </button>
      </div>
    </div>
  )
}

// ── API Keys Tab ──────────────────────────────────────────────────────────────

const SETTINGS_SECTIONS = [
  {
    value: 'profile',
    label: 'Profile',
    description: 'Account details and password',
    icon: User,
    Component: ProfileTab,
  },
  {
    value: 'sources',
    label: 'Data sources',
    description: 'Warehouse credentials and connection checks',
    icon: Database,
    Component: SourcesTab,
  },
  {
    value: 'tables',
    label: 'Tables',
    description: 'Profiling cadence and monitored objects',
    icon: Table2,
    Component: TablesTab,
  },
  {
    value: 'alerts',
    label: 'Alerts',
    description: 'Slack, email, PagerDuty, webhook, and Teams routing',
    icon: Bell,
    Component: AlertsTab,
  },
  {
    value: 'team',
    label: 'Team',
    description: 'Members and invitations',
    icon: Users,
    Component: TeamTab,
  },
  {
    value: 'billing',
    label: 'Billing',
    description: 'Plan and payment details',
    icon: CreditCard,
    Component: BillingTab,
  },
  {
    value: 'notifications',
    label: 'Notifications',
    description: 'Email notification preferences',
    icon: Bell,
    Component: NotificationsTab,
  },
]

function parseJson(value, label) {
  try {
    return [JSON.parse(value), '']
  } catch (err) {
    return [null, `${label} must be valid JSON: ${err.message}`]
  }
}

function getApiError(err, fallback) {
  const detail = err.response?.data?.detail || err.response?.data?.error || err.message
  if (Array.isArray(detail)) return detail.map((item) => item.msg || item.message || String(item)).join(', ')
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail)
  return detail || fallback
}

function SourceForm({ open, onOpenChange, onCreated }) {
  const [form, setForm] = useState({ name: '', type: 'postgres', connection_config: SOURCE_CONFIG_TEMPLATES['postgres'] })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    const [config, parseError] = parseJson(form.connection_config, 'Connection config')
    if (parseError) {
      setError(parseError)
      return
    }
    setSaving(true)
    setError('')
    try {
      const response = await createSource({ name: form.name, type: form.type, connection_config: config })
      onCreated(response.data)
      setForm({ name: '', type: 'postgres', connection_config: SOURCE_CONFIG_TEMPLATES['postgres'] })
      onOpenChange(false)
      notify.source.connected(form.name)
    } catch (err) {
      const message = err.response?.data?.detail || 'Failed to create source'
      setError(message)
      notify.err(message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Add data source</SheetTitle>
          <SheetDescription>Store encrypted connection details for a warehouse connector.</SheetDescription>
        </SheetHeader>
        <form onSubmit={submit} className="flex flex-1 flex-col">
          <div className="flex flex-1 flex-col gap-4 px-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="source-name">Name</Label>
              <Input id="source-name" value={form.name} onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))} required />
            </div>
            <div className="flex flex-col gap-2">
              <Label>Type</Label>
              <Select value={form.type} onValueChange={(type) => setForm((prev) => ({ ...prev, type, connection_config: SOURCE_CONFIG_TEMPLATES[type] || '{}' }))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {SOURCE_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>{SOURCE_TYPE_LABELS[type] || type}</SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="connection-config">Connection config</Label>
              <Textarea
                id="connection-config"
                className="min-h-52 font-mono text-xs"
                value={form.connection_config}
                onChange={(e) => setForm((prev) => ({ ...prev, connection_config: e.target.value }))}
              />
              <p className="text-xs text-muted-foreground">Credentials are encrypted with HKDF per-org keys.</p>
              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          </div>
          <SheetFooter>
            <Button type="submit" disabled={saving}>{saving ? 'Creating...' : 'Create source'}</Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}

function TableForm({ open, onOpenChange, sources, onCreated }) {
  const [schemas, setSchemas] = useState([])
  const [discovering, setDiscovering] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    source_id: sources[0]?.id || '',
    schema_name: '',
    table_name: '',
    freshness_column: '',
    check_interval_minutes: 60,
    sensitivity: 3.0,
  })

  useEffect(() => {
    if (!form.source_id && sources[0]?.id) setForm((prev) => ({ ...prev, source_id: sources[0].id }))
  }, [form.source_id, sources])

  const discover = async (sourceId) => {
    if (!sourceId) return
    setDiscovering(true)
    try {
      const response = await discoverSource(sourceId)
      setSchemas(response.data.schemas || [])
    } catch (_) {
      setSchemas([])
      notify.err('Schema discovery failed', 'Could not reach the warehouse — check source credentials.')
    } finally {
      setDiscovering(false)
    }
  }

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const response = await createTable({
        ...form,
        check_interval_minutes: Number(form.check_interval_minutes),
        sensitivity: Number(form.sensitivity),
      })
      onCreated(response.data)
      onOpenChange(false)
      notify.table.added(form.schema_name + '.' + form.table_name)
    } catch (err) {
      const message = err.response?.data?.detail || 'Failed to add table'
      setError(message)
      notify.err(message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Add monitored table</SheetTitle>
          <SheetDescription>Choose a warehouse table and the profiling cadence for scheduled checks.</SheetDescription>
        </SheetHeader>
        <form onSubmit={submit} className="flex flex-1 flex-col">
          <div className="flex flex-1 flex-col gap-4 px-4">
            <div className="flex flex-col gap-2">
              <Label>Source</Label>
              <Select
                value={String(form.source_id)}
                onValueChange={(source_id) => {
                  setForm((prev) => ({ ...prev, source_id }))
                  discover(source_id)
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select source" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {sources.map((source) => (
                      <SelectItem key={source.id} value={String(source.id)}>{source.name}</SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <Button type="button" variant="outline" size="sm" onClick={() => discover(form.source_id)} disabled={!form.source_id || discovering}>
                {discovering ? 'Discovering...' : 'Discover schemas'}
              </Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label>Schema</Label>
                {schemas.length > 0 ? (
                  <Select value={form.schema_name} onValueChange={(schema_name) => setForm((prev) => ({ ...prev, schema_name }))}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select schema" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {schemas.map((schema) => (
                          <SelectItem key={schema.name} value={schema.name}>{schema.name}</SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                ) : (
                  <Input value={form.schema_name} placeholder="public" onChange={(e) => setForm((prev) => ({ ...prev, schema_name: e.target.value }))} />
                )}
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="table-name">Table name</Label>
                <Input id="table-name" value={form.table_name} onChange={(e) => setForm((prev) => ({ ...prev, table_name: e.target.value }))} required />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="freshness-column">Freshness column</Label>
                <Input id="freshness-column" value={form.freshness_column} placeholder="updated_at" onChange={(e) => setForm((prev) => ({ ...prev, freshness_column: e.target.value }))} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="interval">Interval minutes</Label>
                <Input id="interval" type="number" min={1} value={form.check_interval_minutes} onChange={(e) => setForm((prev) => ({ ...prev, check_interval_minutes: e.target.value }))} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="sensitivity">Sensitivity</Label>
                <Input id="sensitivity" type="number" step="0.1" min={1} value={form.sensitivity} onChange={(e) => setForm((prev) => ({ ...prev, sensitivity: e.target.value }))} />
              </div>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <SheetFooter>
            <Button type="submit" disabled={saving || !form.source_id}>{saving ? 'Adding...' : 'Add table'}</Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}

function AlertForm({ open, onOpenChange, onCreated, channels = FALLBACK_ALERT_CHANNELS, tables = [] }) {
  const firstAvailable = channels.find((channel) => channel.available) || channels[0] || FALLBACK_ALERT_CHANNELS[0]
  const [form, setForm] = useState({ channel: firstAvailable.id, table_id: 'workspace', fields: defaultAlertFields(firstAvailable) })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    const available = channels.find((channel) => channel.available) || channels[0] || FALLBACK_ALERT_CHANNELS[0]
    setForm({ channel: available.id, table_id: 'workspace', fields: defaultAlertFields(available) })
    setError('')
  }, [open, channels])

  const selectedChannel = channels.find((channel) => channel.id === form.channel) || firstAvailable

  const submit = async (event) => {
    event.preventDefault()
    if (!selectedChannel.available) {
      const message = selectedChannel.locked_reason || `${selectedChannel.label} is not available on your current plan.`
      setError(message)
      notify.warn('Alert channel locked', message)
      return
    }

    setSaving(true)
    setError('')
    try {
      const config = alertPayloadFields(form.fields, selectedChannel)
      const response = await createAlert({
        channel: form.channel,
        table_id: form.table_id === 'workspace' ? null : form.table_id,
        config,
      })
      onCreated(response.data)
      onOpenChange(false)
      notify.alert.created(selectedChannel.label || form.channel)
    } catch (err) {
      const message = getApiError(err, 'Failed to create alert')
      setError(message)
      notify.err(message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add alert route</DialogTitle>
          <DialogDescription>Configure where incident notifications are sent and which incidents should trigger this route.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label>Channel</Label>
            <Select
              value={form.channel}
              onValueChange={(channelId) => {
                const nextChannel = channels.find((channel) => channel.id === channelId) || channels[0]
                setForm({ channel: channelId, table_id: 'workspace', fields: defaultAlertFields(nextChannel) })
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {channels.map((channel) => (
                    <SelectItem key={channel.id} value={channel.id} disabled={!channel.available}>
                      {channel.label}{!channel.available ? ` - ${channel.required_plan?.toUpperCase()}+` : ''}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{selectedChannel.description}</p>
          </div>

          {!selectedChannel.available && (
            <Alert>
              <Lock className="size-4" />
              <AlertDescription>{selectedChannel.locked_reason}</AlertDescription>
            </Alert>
          )}

          <div className="flex flex-col gap-2">
            <Label>Route scope</Label>
            <Select value={form.table_id} onValueChange={(table_id) => setForm((prev) => ({ ...prev, table_id }))}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="workspace">All workspace incidents</SelectItem>
                {tables.map((table) => (
                  <SelectItem key={table.id} value={table.id}>
                    {table.schema_name}.{table.table_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">Workspace routes catch every incident. Table routes only fire for that table.</p>
          </div>

          {(selectedChannel.fields || []).map((field) => (
            <div key={field.name} className="flex flex-col gap-2">
              <Label htmlFor={`alert-${field.name}`}>{field.label}</Label>
              {field.type === 'severity' ? (
                <Select value={form.fields[field.name] || 'P3'} onValueChange={(value) => setForm((prev) => ({ ...prev, fields: { ...prev.fields, [field.name]: value } }))}>
                  <SelectTrigger id={`alert-${field.name}`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="P1">P1 only</SelectItem>
                    <SelectItem value="P2">P1 and P2</SelectItem>
                    <SelectItem value="P3">P1, P2, and P3</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id={`alert-${field.name}`}
                  type={field.type === 'password' ? 'password' : field.type === 'email_list' ? 'text' : field.type === 'url' ? 'url' : 'text'}
                  value={form.fields[field.name] || ''}
                  onChange={(e) => setForm((prev) => ({ ...prev, fields: { ...prev.fields, [field.name]: e.target.value } }))}
                  placeholder={field.type === 'email_list' ? 'ops@company.com, data@company.com' : ''}
                  required={field.required}
                />
              )}
              {field.type === 'email_list' && <p className="text-xs text-muted-foreground">Separate multiple recipients with commas.</p>}
              {field.name === 'secret' && <p className="text-xs text-muted-foreground">Used for HMAC-SHA256 signature verification.</p>}
            </div>
          ))}

          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="submit" disabled={saving || !selectedChannel.available}>{saving ? 'Creating...' : 'Create alert'}</Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ConfirmDelete({ label, onConfirm, children }) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{children}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {label}?</AlertDialogTitle>
          <AlertDialogDescription>This action updates Panopta configuration and cannot be undone from this screen.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function SourceStatusDot({ status }) {
  if (status === 'connected') return <span className="inline-block size-2 rounded-full bg-emerald-500" title="Connected" />
  if (status === 'error') return <span className="inline-block size-2 rounded-full bg-destructive" title="Connection error" />
  return <span className="inline-block size-2 rounded-full bg-muted-foreground/40" title="Unknown" />
}

function cleanConfigFields(config) {
  return Object.fromEntries(
    Object.entries(config).filter(([, value]) => value !== '' && value !== null && value !== undefined)
  )
}

function allFieldsEmpty(fields) {
  return Object.values(fields).every((v) => v === '' || v === null || v === undefined)
}

function allFieldsFilled(connector, fields) {
  return connector.fields.filter((f) => f.required).every((f) => {
    const v = fields[f.name]
    return v !== '' && v !== null && v !== undefined
  })
}

function EditSourceDialog({ source, open, onOpenChange, onUpdated }) {
  const [connectors, setConnectors] = useState(FALLBACK_CONNECTORS.map(normalizeConnector))
  const [name, setName] = useState(source?.name || '')
  const [mode, setMode] = useState('fields')
  const [fields, setFields] = useState({})
  const [rawJson, setRawJson] = useState('{}')
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [testResult, setTestResult] = useState(null)

  const connector = connectors.find((c) => c.type === source?.type) || connectors[0]

  useEffect(() => {
    if (!open) return
    getConnectorTypes()
      .then((response) => setConnectors(response.data.map(normalizeConnector)))
      .catch(() => setConnectors(FALLBACK_CONNECTORS.map(normalizeConnector)))
  }, [open])

  useEffect(() => {
    if (open && source) {
      setName(source.name)
      // Start with empty fields — raw config is encrypted on server
      const emptyFields = defaultConfigFor(connector)
      const cleared = Object.fromEntries(Object.keys(emptyFields).map((k) => [k, '']))
      setFields(cleared)
      setRawJson('{}')
      setError('')
      setTestResult(null)
      setMode('fields')
    }
  }, [open, source])

  const updateField = (field, value) => {
    setFields((prev) => {
      const next = { ...prev, [field.name]: castFieldValue(field, value) }
      if (mode === 'fields') setRawJson(JSON.stringify(cleanConfigFields(next), null, 2))
      return next
    })
    setTestResult(null)
  }

  const buildConfig = () => {
    if (mode === 'json') {
      const [config, parseError] = parseJson(rawJson, 'Connection JSON')
      if (parseError) return [null, parseError]
      return [cleanConfigFields(config), '']
    }
    return [cleanConfigFields(fields), '']
  }

  const isConfigEmpty = () => {
    if (mode === 'json') return rawJson.trim() === '' || rawJson.trim() === '{}'
    return allFieldsEmpty(fields)
  }

  const hasPartialFill = () => {
    if (isConfigEmpty()) return false
    if (mode === 'json') return false
    return !allFieldsFilled(connector, fields)
  }

  const runTest = async () => {
    const [connection_config, parseError] = buildConfig()
    if (parseError) { setError(parseError); return }
    setTesting(true); setError(''); setTestResult(null)
    try {
      const response = await testSourceConfig({ type: source.type, connection_config })
      setTestResult(response.data)
      if (response.data.connected) notify.ok('Connection test passed', `Responded in ${response.data.latency_ms}ms.`)
      else notify.err('Connection test failed', response.data.error)
    } catch (err) {
      const message = err.response?.data?.detail || 'Connection test failed'
      setError(message)
      setTestResult({ connected: false, error: message, latency_ms: 0 })
      notify.err('Connection test failed', message)
    } finally {
      setTesting(false)
    }
  }

  const submit = async (event) => {
    event.preventDefault()
    setError('')

    if (hasPartialFill()) {
      setError('Fill in all required fields to replace credentials, or leave all fields empty to keep existing credentials.')
      return
    }

    const payload = {}
    if (name.trim() !== source?.name) payload.name = name.trim()

    if (!isConfigEmpty()) {
      if (!testResult?.connected) {
        setError('Run a successful connection test before saving new credentials.')
        return
      }
      const [config, parseError] = buildConfig()
      if (parseError) { setError(parseError); return }
      payload.connection_config = config
    }

    if (Object.keys(payload).length === 0) {
      onOpenChange(false)
      return
    }

    setSaving(true)
    try {
      const response = await updateSource(source.id, payload)
      onUpdated(response.data)
      notify.ok('Source updated', `${response.data.name} saved successfully.`)
      onOpenChange(false)
    } catch (err) {
      const message = getApiError(err, 'Failed to update source')
      setError(message)
      notify.err(message)
    } finally {
      setSaving(false)
    }
  }

  const configIsEmpty = isConfigEmpty()
  const configPartial = hasPartialFill()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-hidden p-0 sm:max-w-3xl">
        <form onSubmit={submit} className="flex max-h-[92vh] flex-col">
          <DialogHeader className="border-b px-5 py-4">
            <DialogTitle>Edit source</DialogTitle>
            <DialogDescription>
              Update name or replace credentials for this{' '}
              <span className="font-medium text-foreground">{SOURCE_TYPE_LABELS[source?.type] || source?.type}</span> source.
            </DialogDescription>
          </DialogHeader>

          <div className="grid min-h-0 flex-1 overflow-hidden lg:grid-cols-[240px_minmax(0,1fr)]">
            <aside className="border-b bg-muted/25 p-4 lg:border-b-0 lg:border-r">
              <div className="space-y-3">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="edit-source-name">Source name</Label>
                  <Input
                    id="edit-source-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>Connector type</Label>
                  <div className="flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-sm">
                    <Database className="size-3.5 shrink-0 text-muted-foreground" />
                    <span>{SOURCE_TYPE_LABELS[source?.type] || source?.type}</span>
                  </div>
                </div>
                <div className="rounded-md border bg-amber-500/10 px-3 py-2.5 text-xs text-amber-700 dark:text-amber-300">
                  Existing credentials are encrypted on the server and cannot be shown. Leave all config fields empty to keep them, or fill all required fields to replace.
                </div>
              </div>
            </aside>

            <div className="min-h-0 overflow-y-auto p-5">
              <Tabs value={mode} onValueChange={(v) => { setMode(v); setTestResult(null) }}>
                <TabsList>
                  <TabsTrigger value="fields">Form fields</TabsTrigger>
                  <TabsTrigger value="json">Advanced JSON</TabsTrigger>
                </TabsList>

                <TabsContent value="fields" className="mt-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    {connector.fields.map((field) => (
                      <div key={field.name} className={cn('flex flex-col gap-2', field.input_type === 'textarea' && 'sm:col-span-2')}>
                        <Label htmlFor={`edit-field-${field.name}`}>
                          {field.label}
                          {field.required && <span className="text-destructive"> *</span>}
                        </Label>
                        {field.input_type === 'textarea' ? (
                          <Textarea
                            id={`edit-field-${field.name}`}
                            className="min-h-28 font-mono text-xs"
                            value={typeof fields[field.name] === 'string' ? fields[field.name] : JSON.stringify(fields[field.name] || {}, null, 2)}
                            onChange={(e) => updateField(field, e.target.value)}
                            placeholder={field.placeholder || ''}
                          />
                        ) : field.input_type === 'select' && field.options?.length ? (
                          <Select value={String(fields[field.name] || '')} onValueChange={(v) => updateField(field, v)}>
                            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectGroup>
                                {field.options.map((option) => (
                                  <SelectItem key={option} value={option}>{option}</SelectItem>
                                ))}
                              </SelectGroup>
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input
                            id={`edit-field-${field.name}`}
                            type={field.input_type === 'number' ? 'number' : field.secret ? 'password' : 'text'}
                            value={fields[field.name] ?? ''}
                            onChange={(e) => updateField(field, e.target.value)}
                            placeholder={field.placeholder || (field.required ? 'Required to replace' : 'Leave blank to keep')}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                  {configPartial && (
                    <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                      Fill in all required fields (*) to replace credentials, or clear all fields to keep existing.
                    </p>
                  )}
                  {configIsEmpty && (
                    <p className="mt-3 text-xs text-muted-foreground">
                      All fields are empty — existing credentials will be kept.
                    </p>
                  )}
                </TabsContent>

                <TabsContent value="json" className="mt-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="edit-source-json">New connection JSON (leave empty to keep existing)</Label>
                    <Textarea
                      id="edit-source-json"
                      className="min-h-[280px] font-mono text-xs"
                      value={rawJson}
                      onChange={(e) => { setRawJson(e.target.value); setTestResult(null) }}
                      placeholder="{}"
                    />
                  </div>
                </TabsContent>
              </Tabs>

              <div className="mt-4 space-y-3">
                {testResult && (
                  <Alert variant={testResult.connected ? 'default' : 'destructive'}>
                    {testResult.connected ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}
                    <AlertDescription>
                      {testResult.connected
                        ? `Connection passed in ${testResult.latency_ms}ms.`
                        : testResult.error || 'Connection failed.'}
                    </AlertDescription>
                  </Alert>
                )}
                {error && (
                  <Alert variant="destructive">
                    <XCircle className="size-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}
              </div>
            </div>
          </div>

          <DialogFooter className="border-t px-5 py-3">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            {!configIsEmpty && (
              <Button type="button" variant="outline" onClick={runTest} disabled={testing || configPartial}>
                {testing ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Send data-icon="inline-start" />}
                {testing ? 'Testing...' : 'Test connection'}
              </Button>
            )}
            <Button type="submit" disabled={saving || (!configIsEmpty && !testResult?.connected && !configPartial)}>
              {saving && <Loader2 data-icon="inline-start" className="animate-spin" />}
              {saving ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function SourcesTab() {
  const [sources, setSources] = useState([])
  const [open, setOpen] = useState(false)
  const [editSource, setEditSource] = useState(null)
  const [testing, setTesting] = useState({})

  useEffect(() => {
    getSources().then((response) => setSources(response.data))
  }, [])

  const test = async (id) => {
    const source = sources.find((item) => item.id === id)
    setTesting((prev) => ({ ...prev, [id]: 'testing' }))
    try {
      const response = await testSource(id)
      setTesting((prev) => ({ ...prev, [id]: response.data.connected ? 'ok' : 'fail' }))
      // Update status in list after test
      setSources((prev) => prev.map((s) => s.id === id ? { ...s, status: response.data.connected ? 'connected' : 'error' } : s))
      if (response.data.connected) notify.ok('Connection succeeded', `${source?.name || 'Source'} responded in ${response.data.latency_ms}ms.`)
      else notify.source.failed(source?.name || 'Source', response.data.error)
    } catch (_) {
      setTesting((prev) => ({ ...prev, [id]: 'fail' }))
      notify.source.failed(source?.name || 'Source', 'Could not reach the warehouse.')
    }
    setTimeout(() => setTesting((prev) => { const next = { ...prev }; delete next[id]; return next }), 3000)
  }

  const remove = async (id) => {
    const source = sources.find((item) => item.id === id)
    try {
      await deleteSource(id)
      setSources((prev) => prev.filter((source) => source.id !== id))
      notify.source.deleted(source?.name || 'Source')
    } catch (err) {
      notify.err(err.response?.data?.detail || 'Failed to delete source')
    }
  }

  const handleUpdated = (updated) => {
    setSources((prev) => prev.map((s) => s.id === updated.id ? updated : s))
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-medium">Data sources</h2>
            <p className="text-sm text-muted-foreground">Warehouse connectors available to monitored tables.</p>
          </div>
          <Button type="button" onClick={() => setOpen(true)}>
            <Plus data-icon="inline-start" />
            Add source
          </Button>
        </div>
        {sources.length === 0 ? (
          <EmptyState icon={Database} title="No data sources" description="Add a connector before configuring table monitoring." />
        ) : (
          <div className="dw-table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.map((source) => (
                  <TableRow key={source.id}>
                    <TableCell>
                      <span className="flex items-center gap-2 font-medium">
                        <SourceStatusDot status={source.status} />
                        {source.name}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{source.type}</TableCell>
                    <TableCell><HealthBadge status={source.status} /></TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button type="button" variant="ghost" size="icon-sm" aria-label={`Actions for ${source.name}`}>
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuGroup>
                            <DropdownMenuItem onClick={() => setEditSource(source)}>
                              <Pencil data-icon="inline-start" />
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => test(source.id)}>
                              {testing[source.id] === 'ok' ? <CheckCircle2 data-icon="inline-start" /> : testing[source.id] === 'fail' ? <XCircle data-icon="inline-start" /> : <Send data-icon="inline-start" />}
                              {testing[source.id] === 'testing' ? 'Testing...' : 'Test connection'}
                            </DropdownMenuItem>
                            <ConfirmDelete label={source.name} onConfirm={() => remove(source.id)}>
                              <DropdownMenuItem onSelect={(event) => event.preventDefault()} variant="destructive">
                                <Trash2 data-icon="inline-start" />
                                Delete
                              </DropdownMenuItem>
                            </ConfirmDelete>
                          </DropdownMenuGroup>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <SourceConnectionDialog open={open} onOpenChange={setOpen} onCreated={(source) => setSources((prev) => [...prev, source])} />
        {editSource && (
          <EditSourceDialog
            source={editSource}
            open={Boolean(editSource)}
            onOpenChange={(isOpen) => { if (!isOpen) setEditSource(null) }}
            onUpdated={handleUpdated}
          />
        )}
      </CardContent>
    </Card>
  )
}

const INTERVAL_OPTIONS = [
  { value: 15, label: '15 minutes' },
  { value: 30, label: '30 minutes' },
  { value: 60, label: '1 hour' },
  { value: 360, label: '6 hours' },
  { value: 1440, label: '24 hours' },
]

const SENSITIVITY_OPTIONS = [
  { value: 2.0, label: 'Low (2σ)' },
  { value: 3.0, label: 'Medium (3σ)' },
  { value: 4.0, label: 'High (4σ)' },
  { value: 5.0, label: 'Very High (5σ)' },
]

function EditTableDialog({ table, open, onOpenChange, onUpdated }) {
  const [form, setForm] = useState({
    interval_minutes: 60,
    sensitivity: 3.0,
    freshness_column: '',
    is_active: true,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [freshnessMode, setFreshnessMode] = useState('select') // 'select' | 'manual'
  const [freshnessSelect, setFreshnessSelect] = useState('none')
  const [candidateColumns, setCandidateColumns] = useState([])
  const [loadingColumns, setLoadingColumns] = useState(false)

  useEffect(() => {
    if (open && table) {
      setForm({
        interval_minutes: table.check_interval_minutes || 60,
        sensitivity: table.sensitivity || 3.0,
        freshness_column: table.freshness_column || '',
        is_active: table.is_active !== false,
      })
      setError('')
      setCandidateColumns([])
      setFreshnessMode('select')

      // Fetch schema to get timestamp columns
      if (table.source_id && table.schema_name && table.table_name) {
        setLoadingColumns(true)
        getSourceTableSchema(table.source_id, {
          schema_name: table.schema_name,
          table_name: table.table_name,
        })
          .then((response) => {
            const ddl = response.data?.ddl || ''
            const cols = freshnessCandidates(extractColumnsFromDDL(ddl))
            setCandidateColumns(cols)
            const existingCol = table.freshness_column || ''
            if (!existingCol) {
              setFreshnessSelect('none')
            } else if (cols.some((c) => c.name === existingCol)) {
              setFreshnessSelect(existingCol)
            } else {
              // Current column not in candidates — fall back to manual input
              setFreshnessMode('manual')
              setFreshnessSelect('none')
            }
          })
          .catch(() => {
            // If schema fetch fails, fall back to manual input
            setFreshnessMode('manual')
            if (table.freshness_column) {
              setFreshnessSelect('none')
            }
          })
          .finally(() => setLoadingColumns(false))
      }
    }
  }, [open, table])

  const effectiveFreshnessColumn = freshnessMode === 'select'
    ? (freshnessSelect === 'none' ? '' : freshnessSelect)
    : form.freshness_column

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const response = await updateTable(table.id, {
        check_interval_minutes: Number(form.interval_minutes),
        sensitivity: Number(form.sensitivity),
        freshness_column: effectiveFreshnessColumn.trim() || null,
        is_active: form.is_active,
      })
      onUpdated(response.data)
      notify.ok('Table monitoring settings updated')
      onOpenChange(false)
    } catch (err) {
      const message = getApiError(err, 'Failed to update table')
      setError(message)
      notify.err(message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit monitoring settings</DialogTitle>
          <DialogDescription>
            Adjust profiling cadence and anomaly sensitivity for{' '}
            <span className="font-mono text-foreground">{table?.schema_name}.{table?.table_name}</span>.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label>Monitoring interval</Label>
            <Select
              value={String(form.interval_minutes)}
              onValueChange={(v) => setForm((prev) => ({ ...prev, interval_minutes: Number(v) }))}
            >
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {INTERVAL_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={String(opt.value)}>{opt.label}</SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label>Sensitivity</Label>
            <Select
              value={String(form.sensitivity)}
              onValueChange={(v) => setForm((prev) => ({ ...prev, sensitivity: Number(v) }))}
            >
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {SENSITIVITY_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={String(opt.value)}>{opt.label}</SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">Higher values reduce false positives but may miss subtle anomalies.</p>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Freshness column (optional)</Label>
              {loadingColumns && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
            </div>
            {freshnessMode === 'select' ? (
              <>
                <Select
                  value={freshnessSelect}
                  onValueChange={(v) => {
                    if (v === '__manual__') { setFreshnessMode('manual') } else { setFreshnessSelect(v) }
                  }}
                  disabled={loadingColumns}
                >
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="none">None (disable freshness)</SelectItem>
                      {candidateColumns.map((col) => (
                        <SelectItem key={col.name} value={col.name}>{col.name}</SelectItem>
                      ))}
                      <SelectItem value="__manual__">Other (type manually)</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">Select "None" to disable freshness monitoring for this table.</p>
              </>
            ) : (
              <>
                <div className="flex gap-2">
                  <Input
                    id="edit-freshness-column"
                    value={form.freshness_column}
                    onChange={(e) => setForm((prev) => ({ ...prev, freshness_column: e.target.value }))}
                    placeholder="e.g. created_at, updated_at"
                    className="flex-1"
                  />
                  {candidateColumns.length > 0 && (
                    <Button type="button" variant="outline" size="sm" onClick={() => { setFreshnessMode('select'); setFreshnessSelect('none') }}>
                      Use list
                    </Button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">Leave blank to disable freshness monitoring for this table.</p>
              </>
            )}
          </div>

          <div className="flex items-center gap-3 rounded-md border px-3 py-2.5">
            <Checkbox
              id="edit-table-active"
              checked={form.is_active}
              onCheckedChange={(checked) => setForm((prev) => ({ ...prev, is_active: Boolean(checked) }))}
            />
            <div>
              <Label htmlFor="edit-table-active" className="text-sm font-medium cursor-pointer">Active monitoring</Label>
              <p className="text-xs text-muted-foreground">Uncheck to pause scheduled profiling without deleting the table.</p>
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <DialogFooter>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 data-icon="inline-start" className="animate-spin" />}
              {saving ? 'Saving...' : 'Save settings'}
            </Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function TablesTab() {
  const [sources, setSources] = useState([])
  const [tables, setTables] = useState([])
  const [open, setOpen] = useState(false)
  const [editTable, setEditTable] = useState(null)
  const [running, setRunning] = useState({})

  useEffect(() => {
    Promise.all([getSources(), getTables()]).then(([sourcesResponse, tablesResponse]) => {
      setSources(sourcesResponse.data)
      setTables(tablesResponse.data)
    })
  }, [])

  const remove = async (id) => {
    const table = tables.find((item) => item.id === id)
    try {
      await deleteTable(id)
      setTables((prev) => prev.filter((table) => table.id !== id))
      notify.table.removed(table ? `${table.schema_name}.${table.table_name}` : 'Table')
    } catch (err) {
      notify.err(err.response?.data?.detail || 'Failed to remove table')
    }
  }

  const handleRun = async (id) => {
    const clickedAt = new Date()
    setRunning((prev) => ({ ...prev, [id]: true }))
    try {
      await runTable(id)
      // Poll for completion every 2s
      const poll = setInterval(async () => {
        try {
          const res = await getTableProfiles(id, { limit: 1 })
          const latest = res.data?.[0]
          if (latest && new Date(latest.collected_at) > clickedAt) {
            clearInterval(poll)
            setRunning((prev) => { const next = { ...prev }; delete next[id]; return next })
            const [sourcesResponse, tablesResponse] = await Promise.all([getSources(), getTables()])
            setSources(sourcesResponse.data)
            setTables(tablesResponse.data)
            notify.ok('Profile complete — data updated')
          }
        } catch (_) { /* ignore poll errors */ }
      }, 2000)
      // Safety timeout after 90s
      setTimeout(() => {
        clearInterval(poll)
        setRunning((prev) => { const next = { ...prev }; delete next[id]; return next })
      }, 90000)
    } catch (err) {
      notify.err(err.response?.data?.detail || 'Failed to trigger profile')
      setRunning((prev) => { const next = { ...prev }; delete next[id]; return next })
    }
  }

  const handleUpdated = (updated) => {
    setTables((prev) => prev.map((t) => t.id === updated.id ? updated : t))
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-medium">Monitored tables</h2>
            <p className="text-sm text-muted-foreground">Tables scheduled for profiling and anomaly checks.</p>
          </div>
          <Button type="button" onClick={() => setOpen(true)} disabled={sources.length === 0}>
            <Plus data-icon="inline-start" />
            Add table
          </Button>
        </div>
        {tables.length === 0 ? (
          <EmptyState icon={Table2} title="No monitored tables" description="Add a table after connecting a source." />
        ) : (
          <div className="dw-table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Table</TableHead>
                  <TableHead>Interval</TableHead>
                  <TableHead>Sensitivity</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {tables.map((table) => (
                  <TableRow key={table.id}>
                    <TableCell className="font-mono text-xs">{table.schema_name}.{table.table_name}</TableCell>
                    <TableCell className="text-muted-foreground">{table.check_interval_minutes}m</TableCell>
                    <TableCell className="text-muted-foreground">{table.sensitivity}</TableCell>
                    <TableCell><HealthBadge status={table.is_active ? 'healthy' : 'paused'} /></TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button type="button" variant="ghost" size="icon-sm" aria-label={`Actions for ${table.schema_name}.${table.table_name}`}>
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuGroup>
                            <DropdownMenuItem onClick={() => setEditTable(table)}>
                              <Pencil data-icon="inline-start" />
                              Edit settings
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleRun(table.id)} disabled={running[table.id]}>
                              {running[table.id]
                                ? <Loader2 data-icon="inline-start" className="animate-spin" />
                                : <Play data-icon="inline-start" />}
                              {running[table.id] ? 'Queued...' : 'Run now'}
                            </DropdownMenuItem>
                            <ConfirmDelete label={`${table.schema_name}.${table.table_name}`} onConfirm={() => remove(table.id)}>
                              <DropdownMenuItem onSelect={(event) => event.preventDefault()} variant="destructive">
                                <Trash2 data-icon="inline-start" />
                                Delete
                              </DropdownMenuItem>
                            </ConfirmDelete>
                          </DropdownMenuGroup>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <TableSetupDialog open={open} onOpenChange={setOpen} sources={sources} onCreated={(table) => setTables((prev) => [...prev, table])} />
        {editTable && (
          <EditTableDialog
            table={editTable}
            open={Boolean(editTable)}
            onOpenChange={(isOpen) => { if (!isOpen) setEditTable(null) }}
            onUpdated={handleUpdated}
          />
        )}
      </CardContent>
    </Card>
  )
}

function AlertsTab() {
  const [alerts, setAlerts] = useState([])
  const [channels, setChannels] = useState(FALLBACK_ALERT_CHANNELS)
  const [tables, setTables] = useState([])
  const [open, setOpen] = useState(false)
  const [testing, setTesting] = useState({})
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    Promise.all([getAlerts(), getAlertChannels(), getTables()])
      .then(([alertsResponse, channelsResponse, tablesResponse]) => {
        setAlerts(alertsResponse.data)
        setChannels(channelsResponse.data?.channels?.length ? channelsResponse.data.channels : FALLBACK_ALERT_CHANNELS)
        setTables(tablesResponse.data || [])
      })
      .catch((err) => setLoadError(getApiError(err, 'Could not load alert settings')))
  }, [])

  const test = async (id) => {
    const alert = alerts.find((item) => item.id === id)
    setTesting((prev) => ({ ...prev, [id]: 'testing' }))
    try {
      const response = await testAlert(id)
      setTesting((prev) => ({ ...prev, [id]: 'ok' }))
      notify.alert.testSent(response.data?.message || alert?.channel || 'alert')
    } catch (err) {
      setTesting((prev) => ({ ...prev, [id]: 'fail' }))
      notify.err('Alert test failed', getApiError(err, `Could not send ${alert?.channel || 'alert'} test`))
    }
    setTimeout(() => setTesting((prev) => { const next = { ...prev }; delete next[id]; return next }), 3000)
  }

  const remove = async (id) => {
    const alert = alerts.find((item) => item.id === id)
    try {
      await deleteAlert(id)
      setAlerts((prev) => prev.filter((alert) => alert.id !== id))
      notify.alert.deleted(alert?.channel || 'alert')
    } catch (err) {
      notify.err(err.response?.data?.detail || 'Failed to delete alert')
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-medium">Alert routes</h2>
            <p className="text-sm text-muted-foreground">Workspace and table-specific delivery rules for incident notifications.</p>
          </div>
          <Button type="button" onClick={() => setOpen(true)}>
            <Plus data-icon="inline-start" />
            Add alert
          </Button>
        </div>
        {loadError && (
          <Alert variant="destructive">
            <AlertCircle className="size-4" />
            <AlertDescription>{loadError}</AlertDescription>
          </Alert>
        )}
        <div className="grid gap-2 md:grid-cols-3">
          {channels.map((channel) => (
            <div key={channel.id} className={cn('rounded-md border p-3', channel.available ? 'bg-card' : 'bg-muted/40 text-muted-foreground')}>
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium">{channel.label}</div>
                {channel.available ? <Badge variant="outline">Available</Badge> : <Badge variant="secondary"><Lock className="mr-1 size-3" />{channel.required_plan?.toUpperCase()}+</Badge>}
              </div>
              <p className="mt-1 text-xs leading-5">{channel.available ? channel.description : channel.locked_reason}</p>
            </div>
          ))}
        </div>
        {alerts.length === 0 ? (
          <EmptyState icon={Bell} title="No alert routes" description="Create a route before relying on incident notifications." />
        ) : (
          <div className="dw-table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Channel</TableHead>
                  <TableHead>Destination</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Minimum severity</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((alert) => (
                  <TableRow key={alert.id}>
                    <TableCell className="capitalize">{channels.find((channel) => channel.id === alert.channel)?.label || alert.channel}</TableCell>
                    <TableCell className="max-w-xs truncate text-muted-foreground">{alertDestination(alert)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {alert.table_id
                        ? tables.find((table) => table.id === alert.table_id)
                          ? `${tables.find((table) => table.id === alert.table_id).schema_name}.${tables.find((table) => table.id === alert.table_id).table_name}`
                          : 'Table-specific'
                        : 'All workspace incidents'}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{alert.min_severity || alert.config?.min_severity || 'P3'}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button type="button" variant="ghost" size="icon-sm" aria-label={`Actions for ${alert.channel}`}>
                            <MoreHorizontal />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuGroup>
                            <DropdownMenuItem onClick={() => test(alert.id)}>
                              {testing[alert.id] === 'ok' ? <CheckCircle2 data-icon="inline-start" /> : testing[alert.id] === 'fail' ? <XCircle data-icon="inline-start" /> : <Send data-icon="inline-start" />}
                              {testing[alert.id] === 'testing' ? 'Sending...' : 'Send test'}
                            </DropdownMenuItem>
                            <ConfirmDelete label={`${alert.channel} route`} onConfirm={() => remove(alert.id)}>
                              <DropdownMenuItem onSelect={(event) => event.preventDefault()} variant="destructive">
                                <Trash2 data-icon="inline-start" />
                                Delete
                              </DropdownMenuItem>
                            </ConfirmDelete>
                          </DropdownMenuGroup>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <AlertForm open={open} onOpenChange={setOpen} onCreated={(alert) => setAlerts((prev) => [...prev, alert])} channels={channels} tables={tables} />
      </CardContent>
    </Card>
  )
}

function ProfileTab() {
  const [profile, setProfile] = useState(() => ({
    full_name: storage.getItem('dw_user_name') || '',
    email: storage.getItem('dw_user_email') || '',
  }))
  const [canChangeEmail, setCanChangeEmail] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '', confirm_password: '' })

  useEffect(() => {
    let active = true
    getMe()
      .then((response) => {
        if (!active) return
        const user = response.data || {}
        const nextProfile = {
          full_name: user.full_name || user.name || '',
          email: user.email || '',
        }
        setProfile(nextProfile)
        setCanChangeEmail(Boolean(user.can_update_email || user.can_change_email))
        if (nextProfile.full_name) storage.setItem('dw_user_name', nextProfile.full_name)
        if (nextProfile.email) storage.setItem('dw_user_email', nextProfile.email)
      })
      .catch((err) => {
        if (!profile.email && err.response?.status !== 404) {
          notify.err(getApiError(err, 'Could not load profile'))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  const submitProfile = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      const payload = { full_name: profile.full_name }
      if (canChangeEmail) payload.email = profile.email
      const response = await updateProfile(payload)
      const updated = response.data || profile
      const nextProfile = {
        full_name: updated.full_name || updated.name || profile.full_name,
        email: updated.email || profile.email,
      }
      setProfile(nextProfile)
      storage.setItem('dw_user_name', nextProfile.full_name)
      storage.setItem('dw_user_email', nextProfile.email)
      notify.ok('Profile updated')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to update profile'))
    } finally {
      setSaving(false)
    }
  }

  const submitPassword = async (event) => {
    event.preventDefault()
    if (passwords.new_password !== passwords.confirm_password) {
      notify.err('Passwords do not match')
      return
    }
    setPasswordSaving(true)
    try {
      await changePassword({
        current_password: passwords.current_password,
        new_password: passwords.new_password,
        confirm_password: passwords.confirm_password,
      })
      setPasswords({ current_password: '', new_password: '', confirm_password: '' })
      notify.ok('Password changed')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to change password'))
    } finally {
      setPasswordSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div>
            <h2 className="flex items-center gap-2 text-base font-medium"><User className="size-4 text-muted-foreground" />Profile</h2>
            <p className="mt-1 text-sm text-muted-foreground">Update the account details shown inside this workspace.</p>
          </div>
          <form onSubmit={submitProfile} className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="profile-full-name">Full name</Label>
              <Input
                id="profile-full-name"
                value={profile.full_name}
                onChange={(event) => setProfile((prev) => ({ ...prev, full_name: event.target.value }))}
                disabled={loading}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="profile-email">Email</Label>
              <Input
                id="profile-email"
                type="email"
                value={profile.email}
                readOnly={!canChangeEmail}
                disabled={loading}
                onChange={(event) => setProfile((prev) => ({ ...prev, email: event.target.value }))}
                className={!canChangeEmail ? 'bg-muted/50 text-muted-foreground' : undefined}
              />
              {!canChangeEmail && <p className="text-xs text-muted-foreground">Email changes are managed by your workspace administrator.</p>}
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={loading || saving}>
                {saving && <Loader2 data-icon="inline-start" className="animate-spin" />}
                {saving ? 'Saving...' : 'Save profile'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div>
            <h2 className="flex items-center gap-2 text-base font-medium"><KeyRound className="size-4 text-muted-foreground" />Change password</h2>
            <p className="mt-1 text-sm text-muted-foreground">Use a strong password that is not shared with other services.</p>
          </div>
          <form onSubmit={submitPassword} className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="current-password">Current password</Label>
              <Input
                id="current-password"
                type="password"
                value={passwords.current_password}
                onChange={(event) => setPasswords((prev) => ({ ...prev, current_password: event.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="new-password">New password</Label>
              <Input
                id="new-password"
                type="password"
                minLength={8}
                value={passwords.new_password}
                onChange={(event) => setPasswords((prev) => ({ ...prev, new_password: event.target.value }))}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="confirm-password">Confirm new password</Label>
              <Input
                id="confirm-password"
                type="password"
                minLength={8}
                value={passwords.confirm_password}
                onChange={(event) => setPasswords((prev) => ({ ...prev, confirm_password: event.target.value }))}
                required
              />
            </div>
            <div className="sm:col-span-3">
              <Button type="submit" variant="outline" disabled={passwordSaving}>
                {passwordSaving && <Loader2 data-icon="inline-start" className="animate-spin" />}
                {passwordSaving ? 'Changing...' : 'Change password'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

const ROLES = [
  { value: 'owner', label: 'Owner', desc: 'Full control including billing, staff management, and org deletion.' },
  { value: 'admin', label: 'Admin', desc: 'Full access to sources, tables, alerts, team settings, and billing.' },
  { value: 'member', label: 'Member', desc: 'Can use dashboards, monitored tables, incidents, alerts, and reports.' },
  { value: 'viewer', label: 'Viewer', desc: 'Read-only access to workspace health, incidents, and reports.' },
]

const ROLE_BADGE = {
  owner: 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30',
  admin: 'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30',
  member: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
  viewer: 'bg-muted text-muted-foreground border-border',
}

function RoleBadge({ role }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${ROLE_BADGE[role] || ROLE_BADGE.viewer}`}>
      {role}
    </span>
  )
}

function normalizeInvites(data) {
  if (Array.isArray(data)) return data
  return data?.invites || data?.items || []
}

function TeamTab() {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('member')
  const [members, setMembers] = useState([])
  const [invites, setInvites] = useState([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [revoking, setRevoking] = useState({})

  // Read current user role from storage to gate invite form
  const { storage: _s } = (() => { try { return { storage: window.localStorage } } catch { return { storage: null } } })()
  const currentUserRole = _s?.getItem('dw_user_role') || 'member'
  const canInvite = ['owner', 'admin'].includes(currentUserRole)

  const load = async () => {
    setLoading(true)
    try {
      const [inviteRes, membersRes] = await Promise.allSettled([
        getInvites(),
        getOrgMembers().catch(() => ({ data: [] })),
      ])
      if (inviteRes.status === 'fulfilled') setInvites(normalizeInvites(inviteRes.value.data))
      if (membersRes.status === 'fulfilled') {
        const raw = membersRes.value?.data
        setMembers(Array.isArray(raw) ? raw : raw?.items || raw?.members || [])
      }
    } catch (err) {
      notify.err(getApiError(err, 'Could not load team'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const invite = async (event) => {
    event.preventDefault()
    if (!email || !canInvite) return
    const invitedEmail = email.trim()
    setSending(true)
    try {
      const response = await createInvite({ email: invitedEmail, role })
      const created = response.data
      if (created?.id) setInvites((prev) => [created, ...prev])
      else await load()
      setEmail('')
      notify.ok(`Invite sent to ${invitedEmail}`)
    } catch (err) {
      notify.err(getApiError(err, 'Failed to send invite'))
    } finally {
      setSending(false)
    }
  }

  const revoke = async (invite) => {
    setRevoking((prev) => ({ ...prev, [invite.id]: true }))
    try {
      await revokeInvite(invite.id)
      setInvites((prev) => prev.filter((item) => item.id !== invite.id))
      notify.ok(`Invite revoked for ${invite.email}`)
    } catch (err) {
      notify.err(getApiError(err, 'Failed to revoke invite'))
    } finally {
      setRevoking((prev) => { const next = { ...prev }; delete next[invite.id]; return next })
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Current members */}
      <Card className="overflow-hidden p-0">
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-medium"><Users className="size-4 text-muted-foreground" />Team members</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">All active members of this workspace.</p>
          </div>
          <Badge variant="outline">{loading ? '…' : members.length}</Badge>
        </div>
        {loading ? (
          <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : members.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground">No members found.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name / Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Joined</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>
                    <div className="font-medium">{m.full_name || m.email}</div>
                    {m.full_name && <div className="text-xs text-muted-foreground">{m.email}</div>}
                  </TableCell>
                  <TableCell><RoleBadge role={m.role} /></TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {m.created_at ? new Date(m.created_at).toLocaleDateString() : '—'}
                  </TableCell>
                  <TableCell>
                    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${m.is_active !== false ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'border-border bg-muted text-muted-foreground'}`}>
                      {m.is_active !== false ? 'Active' : 'Inactive'}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Invite form — only shown to owner/admin */}
      {canInvite ? (
        <Card>
          <CardContent className="flex flex-col gap-4 pt-6">
            <div>
              <h2 className="flex items-center gap-2 text-base font-medium"><Send className="size-4 text-muted-foreground" />Invite team members</h2>
              <p className="mt-1 text-sm text-muted-foreground">Members are isolated to your workspace and cannot access other workspaces.</p>
            </div>
            <form onSubmit={invite} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_180px_auto]">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="colleague@company.com" required />
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {ROLES.filter((r) => r.value !== 'owner').map((item) => (
                      <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <Button type="submit" disabled={sending || !email}>
                {sending && <Loader2 data-icon="inline-start" className="animate-spin" />}
                {sending ? 'Sending…' : 'Send invite'}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Only workspace owners and admins can invite new members.</p>
          </CardContent>
        </Card>
      )}

      {/* Pending invites */}
      {canInvite && (
        <Card className="overflow-hidden p-0">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div>
              <h3 className="text-sm font-medium">Pending invites</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">Invites remain pending until accepted or expired.</p>
            </div>
            {invites.length > 0 && <Badge variant="outline">{invites.length}</Badge>}
          </div>
          {loading ? (
            <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading…</div>
          ) : invites.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground">No pending invites.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead className="w-24" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {invites.map((inv) => (
                  <TableRow key={inv.id || inv.email}>
                    <TableCell className="font-medium">{inv.email}</TableCell>
                    <TableCell><RoleBadge role={inv.role} /></TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {inv.expires_at ? new Date(inv.expires_at).toLocaleString() : 'Not set'}
                    </TableCell>
                    <TableCell>
                      <Button type="button" variant="ghost" size="sm" onClick={() => revoke(inv)} disabled={!inv.id || revoking[inv.id]}>
                        {revoking[inv.id] ? 'Revoking…' : 'Revoke'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>
      )}

      {/* Role permissions reference */}
      <Card className="overflow-hidden p-0">
        <div className="px-4 py-3 border-b">
          <h3 className="text-sm font-medium">Role permissions</h3>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Role</TableHead>
              <TableHead>Description</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROLES.map((item) => (
              <TableRow key={item.value}>
                <TableCell><RoleBadge role={item.value} /></TableCell>
                <TableCell className="text-muted-foreground">{item.desc}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}

const PLANS = [
  { id: 'free', name: 'Free', monthlyPrice: 0, limit: '1 source · 5 tables · 7-day history · Email alerts only' },
  { id: 'starter', name: 'Starter', monthlyPrice: 49, limit: '3 sources · 50 tables · 90-day history · Slack + webhook alerts' },
  { id: 'growth', name: 'Growth', monthlyPrice: 149, limit: 'Unlimited sources & tables · 1-year history · All alert channels · AI reports' },
  { id: 'agency', name: 'Agency', monthlyPrice: 299, limit: 'Everything in Growth · Multi-client workspaces · White-label reports · 15 members' },
]

function planPrice(plan, billingCycle) {
  if (plan.monthlyPrice === 0) return '$0'
  if (billingCycle === 'yearly') return `$${Math.round(plan.monthlyPrice * 12 * 0.8)}/yr`
  return `$${plan.monthlyPrice}/mo`
}

const PAYPAL_CLIENT_ID = import.meta.env.VITE_PAYPAL_CLIENT_ID || 'sb'

// PayPal hosted card buttons — no PayPal account required
function PayPalCardButtons({ plan, billingCycle, onSuccess }) {
  const pendingPlanRef = useRef(plan)
  const pendingPeriodRef = useRef(billingCycle)
  pendingPlanRef.current = plan
  pendingPeriodRef.current = billingCycle

  return (
    <PayPalScriptProvider
      options={{
        'client-id': PAYPAL_CLIENT_ID,
        vault: true,
        intent: 'subscription',
        components: 'buttons',
      }}
    >
      <PayPalButtons
        fundingSource="card"
        style={{ layout: 'vertical', label: 'subscribe', height: 40 }}
        createSubscription={async (_data, actions) => {
          try {
            const response = await createBillingSubscription({
              plan: pendingPlanRef.current.id,
              billing_period: pendingPeriodRef.current,
              return_url: `${window.location.origin}/settings?tab=billing&billing_return=paypal&plan=${pendingPlanRef.current.id}&billing_period=${pendingPeriodRef.current}`,
              cancel_url: `${window.location.origin}/settings?tab=billing`,
            })
            if (response.data?.plan_id) {
              return actions.subscription.create({ plan_id: response.data.plan_id })
            }
            // Fallback: redirect if backend doesn't return plan_id
            const approvalUrl = response.data?.approval_url
            if (approvalUrl) {
              storage.setItem('dw_billing_pending_plan', pendingPlanRef.current.id)
              storage.setItem('dw_billing_pending_period', pendingPeriodRef.current)
              window.location.assign(approvalUrl)
            }
          } catch (err) {
            notify.err('Could not start card checkout. Try PayPal account instead.')
          }
        }}
        onApprove={(data) => {
          const subscriptionId = data.subscriptionID
          if (!subscriptionId) return
          captureBillingSubscription({
            subscription_id: subscriptionId,
            plan: pendingPlanRef.current.id,
            billing_period: pendingPeriodRef.current,
          })
            .then((res) => onSuccess(res.data))
            .catch((err) => notify.err(getApiError(err, 'Failed to activate card subscription')))
        }}
        onError={(err) => {
          console.error('PayPal card error', err)
          notify.err('Card payment failed. Check card details or try PayPal account.')
        }}
      />
    </PayPalScriptProvider>
  )
}

function BillingTab() {
  const orgName = storage.getItem('dw_org_name') || 'Your workspace'
  const [billingCycle, setBillingCycle] = useState('monthly')
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [upgrading, setUpgrading] = useState('')
  const [canceling, setCanceling] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [selectedPlan, setSelectedPlan] = useState(null)
  const [paymentMethod, setPaymentMethod] = useState(null)

  const loadStatus = async () => {
    setLoading(true)
    try {
      const response = await getBillingStatus()
      setStatus(response.data)
      if (response.data?.plan) storage.setItem('dw_plan', response.data.plan)
    } catch (err) {
      notify.err(getApiError(err, 'Could not load billing status'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  // Handle PayPal redirect return (account flow)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const hasPayPalReturn = params.get('billing_return') === 'paypal' || params.has('subscription_id') || params.has('ba_token') || params.has('token')
    if (!hasPayPalReturn) return

    const pendingPlan = params.get('plan') || storage.getItem('dw_billing_pending_plan')
    const pendingPeriod = params.get('billing_period') || storage.getItem('dw_billing_pending_period')
    const subscriptionId = params.get('subscription_id') || params.get('subscriptionID') || params.get('subscriptionId')
    if (!subscriptionId || !pendingPlan) {
      notify.err('Failed to capture PayPal subscription', 'PayPal did not return enough subscription details.')
      return
    }

    setCapturing(true)
    captureBillingSubscription({
      subscription_id: subscriptionId,
      plan: pendingPlan,
      billing_period: pendingPeriod || undefined,
    })
      .then((response) => {
        setStatus(response.data)
        if (response.data?.plan) storage.setItem('dw_plan', response.data.plan)
        storage.removeItem('dw_billing_pending_plan')
        storage.removeItem('dw_billing_pending_period')
        notify.ok('Subscription activated')
        const cleanUrl = `${window.location.pathname}?tab=billing`
        window.history.replaceState(null, '', cleanUrl)
      })
      .catch((err) => notify.err(getApiError(err, 'Failed to capture PayPal subscription')))
      .finally(() => setCapturing(false))
  }, [])

  const currentPlan = (status?.plan || storage.getItem('dw_plan') || 'free').toLowerCase()
  const subscriptionStatus = status?.subscription_status || status?.status || (currentPlan === 'free' ? 'free' : 'unknown')
  const isPaymentIssue = ['SUSPENDED', 'FAILED', 'suspended', 'failed'].includes(subscriptionStatus)
  const isApprovalPending = ['APPROVAL_PENDING', 'approval_pending'].includes(subscriptionStatus)
  const isActive = ['ACTIVE', 'active', 'TRIALING', 'trialing', 'APPROVAL_PENDING', 'approval_pending'].includes(subscriptionStatus)
  const nextBillingDate = status?.next_billing_time || status?.next_billing_date || status?.current_period_end

  // Human-readable status label
  const statusLabel = isApprovalPending
    ? 'Pending activation'
    : subscriptionStatus === 'free' || currentPlan === 'free'
      ? 'Free tier'
      : subscriptionStatus.toLowerCase().replace('_', ' ')

  const upgradeWithPayPal = async (plan) => {
    setUpgrading(plan.id)
    try {
      const response = await createBillingSubscription({
        plan: plan.id,
        billing_period: billingCycle,
        return_url: `${window.location.origin}/settings?tab=billing&billing_return=paypal&plan=${plan.id}&billing_period=${billingCycle}`,
        cancel_url: `${window.location.origin}/settings?tab=billing`,
      })
      const approvalUrl = response.data?.approval_url
      if (!approvalUrl) throw new Error('PayPal approval URL was not returned')
      storage.setItem('dw_billing_pending_plan', plan.id)
      storage.setItem('dw_billing_pending_period', billingCycle)
      window.location.assign(approvalUrl)
    } catch (err) {
      notify.err(getApiError(err, 'Failed to start PayPal checkout'))
      setUpgrading('')
    }
  }

  const handleUpgradeClick = (plan) => {
    if (selectedPlan?.id === plan.id) {
      setSelectedPlan(null)
      setPaymentMethod(null)
    } else {
      setSelectedPlan(plan)
      setPaymentMethod(null)
    }
  }

  const handleCardSuccess = (data) => {
    setStatus(data)
    if (data?.plan) storage.setItem('dw_plan', data.plan)
    setSelectedPlan(null)
    setPaymentMethod(null)
    notify.ok('Subscription activated!')
  }

  const cancel = async () => {
    setCanceling(true)
    try {
      const response = await cancelBillingSubscription()
      setStatus(response.data || { ...(status || {}), subscription_status: 'canceled' })
      notify.ok('Subscription canceled')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to cancel subscription'))
    } finally {
      setCanceling(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Sandbox notice */}
      <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-300">
        <Info className="mt-0.5 size-4 shrink-0" />
        <div>
          <span className="font-medium">Sandbox mode</span> — Use PayPal sandbox credentials or test card{' '}
          <code className="rounded bg-blue-100 px-1 font-mono text-xs dark:bg-blue-900">4032034785726736</code>{' '}
          / expiry <code className="rounded bg-blue-100 px-1 font-mono text-xs dark:bg-blue-900">01/27</code>{' '}
          / CVV <code className="rounded bg-blue-100 px-1 font-mono text-xs dark:bg-blue-900">123</code>
        </div>
      </div>

      {/* Approval pending banner */}
      {isApprovalPending && !capturing && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          <Info className="mt-0.5 size-4 shrink-0" />
          <div>
            <span className="font-medium">Subscription pending activation.</span>{' '}
            Your <span className="font-semibold capitalize">{currentPlan}</span> plan is set up and all features are unlocked. PayPal may take a moment to confirm — your subscription will activate automatically.{' '}
            If this persists, try re-subscribing or contact support.
          </div>
        </div>
      )}

      {/* Payment issue banner */}
      {isPaymentIssue && (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div>
            <span className="font-medium">Payment issue detected.</span> Your subscription is {subscriptionStatus.toLowerCase()}.{' '}
            Please update your payment method by upgrading below.
          </div>
        </div>
      )}

      {/* Current plan card */}
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="flex items-center gap-2 text-base font-medium">
                <CreditCard className="size-4 text-muted-foreground" />Current plan
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">{orgName}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="capitalize">{loading ? 'Loading…' : currentPlan}</Badge>
              <Badge
                variant={isActive ? 'default' : isPaymentIssue ? 'destructive' : 'secondary'}
                className="capitalize"
              >
                {capturing ? 'activating…' : statusLabel}
              </Badge>
            </div>
          </div>

          {/* Next billing date */}
          {isActive && nextBillingDate && (
            <p className="text-sm text-muted-foreground">
              Next billing:{' '}
              <span className="font-medium text-foreground">
                {new Date(nextBillingDate).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}
              </span>
            </p>
          )}

          {currentPlan !== 'free' && (
            <Button type="button" variant="outline" className="w-fit" onClick={cancel} disabled={canceling}>
              {canceling ? 'Canceling…' : 'Cancel subscription'}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Plan entitlements summary */}
      {!loading && (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <h3 className="text-sm font-medium">What's included in your plan</h3>
            <div className="grid gap-2 sm:grid-cols-3">
              {[
                {
                  label: 'Data sources',
                  value: currentPlan === 'growth' || currentPlan === 'enterprise' || currentPlan === 'agency' ? 'Unlimited' : currentPlan === 'starter' ? '3 sources' : '1 source',
                  highlight: currentPlan !== 'free',
                },
                {
                  label: 'Monitored tables',
                  value: currentPlan === 'growth' || currentPlan === 'enterprise' || currentPlan === 'agency' ? 'Unlimited' : currentPlan === 'starter' ? 'Up to 50' : 'Up to 5',
                  highlight: currentPlan !== 'free',
                },
                {
                  label: 'Profile history',
                  value: currentPlan === 'enterprise' ? 'Forever' : currentPlan === 'growth' || currentPlan === 'agency' ? '1 year' : currentPlan === 'starter' ? '90 days' : '7 days',
                  highlight: currentPlan !== 'free',
                },
                {
                  label: 'Alert channels',
                  value: currentPlan === 'growth' || currentPlan === 'enterprise' || currentPlan === 'agency' ? 'All channels (Slack, PagerDuty, Teams…)' : currentPlan === 'starter' ? 'Email, Slack, webhook' : 'Email only',
                  highlight: currentPlan !== 'free',
                },
                {
                  label: 'AI incident reports',
                  value: currentPlan === 'free' ? 'Not included' : 'Included',
                  highlight: currentPlan !== 'free',
                },
                {
                  label: 'Team members',
                  value: currentPlan === 'growth' || currentPlan === 'enterprise' ? 'Unlimited' : currentPlan === 'agency' ? '15 members' : currentPlan === 'starter' ? '10 members' : '3 members',
                  highlight: currentPlan !== 'free',
                },
              ].map((item) => (
                <div key={item.label} className="rounded-md border bg-muted/20 px-3 py-2.5">
                  <div className="text-xs text-muted-foreground">{item.label}</div>
                  <div className={`mt-0.5 text-sm font-medium ${item.highlight ? 'text-foreground' : 'text-muted-foreground'}`}>{item.value}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Plans grid */}
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-medium">Available plans</h3>
              <p className="mt-1 text-sm text-muted-foreground">Pay with PayPal account or directly by card — no PayPal account needed.</p>
            </div>
            <div className="inline-flex w-fit rounded-md border bg-muted/30 p-1">
              {['monthly', 'yearly'].map((cycle) => (
                <button
                  key={cycle}
                  type="button"
                  onClick={() => setBillingCycle(cycle)}
                  className={cn(
                    'rounded-sm px-3 py-1.5 text-xs font-medium capitalize transition-colors',
                    billingCycle === cycle ? 'bg-background text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  {cycle === 'yearly' ? 'Yearly -20%' : 'Monthly'}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {PLANS.map((plan) => {
              const isCurrent = plan.id === currentPlan
              const isSelected = selectedPlan?.id === plan.id
              return (
                <div
                  key={plan.id}
                  className={cn(
                    'rounded-lg border p-4 transition-colors',
                    isCurrent ? 'border-2 border-primary bg-primary/5' : 'border-border',
                    isSelected && !isCurrent && 'border-primary/60 bg-primary/5',
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-sm">{plan.name}</span>
                      {isCurrent && (
                        <Badge variant="default" className="gap-1 text-xs">
                          <CheckCircle2 className="size-3" />Current
                        </Badge>
                      )}
                    </div>
                    <span className="text-sm font-bold shrink-0">{planPrice(plan, billingCycle)}</span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">{plan.limit}</p>

                  {!isCurrent && plan.id !== 'free' && (
                    <div className="mt-3 flex flex-col gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant={isSelected ? 'default' : 'outline'}
                        className="w-full"
                        onClick={() => handleUpgradeClick(plan)}
                      >
                        {isSelected ? 'Choose payment method ↓' : 'Upgrade'}
                      </Button>

                      {/* Payment method picker */}
                      {isSelected && (
                        <div className="flex flex-col gap-2 rounded-md border bg-muted/20 p-3">
                          <p className="text-xs font-medium text-muted-foreground">Pay with:</p>
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              size="sm"
                              variant={paymentMethod === 'paypal' ? 'default' : 'outline'}
                              className="flex-1 text-xs"
                              onClick={() => setPaymentMethod('paypal')}
                            >
                              PayPal account
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant={paymentMethod === 'card' ? 'default' : 'outline'}
                              className="flex-1 text-xs"
                              onClick={() => setPaymentMethod('card')}
                            >
                              Debit / Credit card
                            </Button>
                          </div>

                          {/* PayPal account — redirects to PayPal */}
                          {paymentMethod === 'paypal' && (
                            <Button
                              type="button"
                              size="sm"
                              className="w-full"
                              onClick={() => upgradeWithPayPal(plan)}
                              disabled={Boolean(upgrading)}
                            >
                              {upgrading === plan.id && <Loader2 data-icon="inline-start" className="animate-spin" />}
                              {upgrading === plan.id ? 'Opening PayPal…' : 'Continue to PayPal →'}
                            </Button>
                          )}

                          {/* Card — PayPal hosted card buttons (no redirect, no PayPal account) */}
                          {paymentMethod === 'card' && (
                            <div className="mt-1">
                              <PayPalCardButtons
                                plan={plan}
                                billingCycle={billingCycle}
                                onSuccess={handleCardSuccess}
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default function Settings() {
  const [active, setActive] = useState(() => {
    const tab = new URLSearchParams(window.location.search).get('tab')
    return SETTINGS_SECTIONS.some((section) => section.value === tab) ? tab : 'profile'
  })
  const activeSection = SETTINGS_SECTIONS.find((section) => section.value === active) || SETTINGS_SECTIONS[0]
  const ActiveComponent = activeSection.Component

  return (
    <div className="dw-page">
      <PageHeader title="Settings" description="Configure warehouse connectors, monitored tables, alert routing, team members, and billing." />
      <div className="grid min-w-0 gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="h-fit min-w-0 rounded-lg border bg-card p-2 shadow-xs">
          <nav className="flex max-w-full snap-x gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
            {SETTINGS_SECTIONS.map((section) => {
              const Icon = section.icon
              const selected = active === section.value
              return (
                <button
                  key={section.value}
                  type="button"
                  onClick={() => setActive(section.value)}
                  className={cn(
                    'dw-nav-link group/settings flex w-[min(78vw,260px)] shrink-0 snap-start items-start gap-3 rounded-md border px-3 py-2.5 text-left transition-colors lg:w-auto lg:min-w-0',
                    selected
                      ? 'border-primary/25 bg-primary/10 text-foreground shadow-xs'
                      : 'border-transparent text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground'
                  )}
                >
                  <span
                    className={cn(
                      'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border transition-colors',
                      selected ? 'border-primary/25 bg-primary text-primary-foreground' : 'border-border bg-card group-hover/settings:bg-card'
                    )}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{section.label}</span>
                    <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{section.description}</span>
                  </span>
                </button>
              )
            })}
          </nav>
        </aside>

        <section className="min-w-0">
          <ActiveComponent />
        </section>
      </div>
    </div>
  )
}
