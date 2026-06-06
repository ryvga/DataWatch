import { useEffect, useState } from 'react'
import { notify } from '@/lib/notify'
import {
  Bell,
  CheckCircle2,
  CreditCard,
  Database,
  KeyRound,
  Loader2,
  MoreHorizontal,
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
  getBillingStatus,
  getInvites,
  getMe,
  getOrgMembers,
  getSources,
  getTables,
  revokeInvite,
  testAlert,
  testSource,
  updateProfile,
  updateSource,
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

const ALERT_EXAMPLES = {
  slack: '{\n  "webhook_url": "https://hooks.slack.com/...",\n  "min_severity": "P2"\n}',
  email: '{\n  "to": ["you@company.com"],\n  "min_severity": "P3"\n}',
  pagerduty: '{\n  "routing_key": "YOUR_KEY",\n  "min_severity": "P1"\n}',
  webhook: '{\n  "url": "https://example.com/webhook",\n  "secret": ""\n}',
  teams: '{\n  "webhook_url": "https://outlook.office.com/webhook/..."\n}',
  discord: '{\n  "webhook_url": "https://discord.com/api/webhooks/...",\n  "min_severity": "P2"\n}',
  opsgenie: '{\n  "api_key": "YOUR_OPSGENIE_KEY",\n  "min_severity": "P1"\n}',
}

const ALERT_FIELD_DEFAULTS = {
  webhook: { url: '', secret: '' },
  teams: { webhook_url: '' },
}

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

function AlertForm({ open, onOpenChange, onCreated }) {
  const [form, setForm] = useState({ channel: 'slack', config: ALERT_EXAMPLES.slack, fields: {} })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    let config = form.fields

    if (!ALERT_FIELD_DEFAULTS[form.channel]) {
      const [parsedConfig, parseError] = parseJson(form.config, 'Alert config')
      if (parseError) {
        setError(parseError)
        return
      }
      config = parsedConfig
    }

    setSaving(true)
    setError('')
    try {
      const response = await createAlert({ channel: form.channel, config })
      onCreated(response.data)
      onOpenChange(false)
      notify.alert.created(form.channel)
    } catch (err) {
      const message = err.response?.data?.detail || 'Failed to create alert'
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
          <DialogDescription>Configure where incident notifications are sent.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label>Channel</Label>
            <Select
              value={form.channel}
              onValueChange={(channel) => setForm({ channel, config: ALERT_EXAMPLES[channel], fields: ALERT_FIELD_DEFAULTS[channel] || {} })}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="slack">Slack</SelectItem>
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="discord">Discord</SelectItem>
                  <SelectItem value="pagerduty">PagerDuty</SelectItem>
                  <SelectItem value="opsgenie">OpsGenie</SelectItem>
                  <SelectItem value="webhook">Webhook (Generic)</SelectItem>
                  <SelectItem value="teams">Microsoft Teams</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          {form.channel === 'webhook' ? (
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="webhook-url">Webhook URL</Label>
                <Input
                  id="webhook-url"
                  type="text"
                  value={form.fields.url || ''}
                  onChange={(e) => setForm((prev) => ({ ...prev, fields: { ...prev.fields, url: e.target.value } }))}
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="webhook-secret">Signing secret (optional)</Label>
                <Input
                  id="webhook-secret"
                  type="text"
                  value={form.fields.secret || ''}
                  onChange={(e) => setForm((prev) => ({ ...prev, fields: { ...prev.fields, secret: e.target.value } }))}
                />
                <p className="text-xs text-muted-foreground">Used for HMAC-SHA256 signature verification</p>
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          ) : form.channel === 'teams' ? (
            <div className="flex flex-col gap-2">
              <Label htmlFor="teams-webhook-url">Teams Incoming Webhook URL</Label>
              <Input
                id="teams-webhook-url"
                type="text"
                value={form.fields.webhook_url || ''}
                onChange={(e) => setForm((prev) => ({ ...prev, fields: { ...prev.fields, webhook_url: e.target.value } }))}
                required
              />
              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <Label htmlFor="alert-config">Config</Label>
              <Textarea id="alert-config" className="min-h-36 font-mono text-xs" value={form.config} onChange={(e) => setForm((prev) => ({ ...prev, config: e.target.value }))} />
              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          )}
          <DialogFooter>
            <Button type="submit" disabled={saving}>{saving ? 'Creating...' : 'Create alert'}</Button>
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
          <AlertDialogDescription>This action updates DataWatch configuration and cannot be undone from this screen.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function SourcesTab() {
  const [sources, setSources] = useState([])
  const [open, setOpen] = useState(false)
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
                    <TableCell className="font-medium">{source.name}</TableCell>
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
      </CardContent>
    </Card>
  )
}

function TablesTab() {
  const [sources, setSources] = useState([])
  const [tables, setTables] = useState([])
  const [open, setOpen] = useState(false)

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
      </CardContent>
    </Card>
  )
}

function AlertsTab() {
  const [alerts, setAlerts] = useState([])
  const [open, setOpen] = useState(false)
  const [testing, setTesting] = useState({})

  useEffect(() => {
    getAlerts().then((response) => setAlerts(response.data))
  }, [])

  const test = async (id) => {
    const alert = alerts.find((item) => item.id === id)
    setTesting((prev) => ({ ...prev, [id]: 'testing' }))
    try {
      await testAlert(id)
      setTesting((prev) => ({ ...prev, [id]: 'ok' }))
      notify.alert.testSent(alert?.channel || 'alert')
    } catch (_) {
      setTesting((prev) => ({ ...prev, [id]: 'fail' }))
      notify.alert.testFailed(alert?.channel || 'alert')
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
            <p className="text-sm text-muted-foreground">Slack, email, PagerDuty, webhook, and Teams delivery rules for incidents.</p>
          </div>
          <Button type="button" onClick={() => setOpen(true)}>
            <Plus data-icon="inline-start" />
            Add alert
          </Button>
        </div>
        {alerts.length === 0 ? (
          <EmptyState icon={Bell} title="No alert routes" description="Create a route before relying on incident notifications." />
        ) : (
          <div className="dw-table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Channel</TableHead>
                  <TableHead>Minimum severity</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((alert) => (
                  <TableRow key={alert.id}>
                    <TableCell className="capitalize">{alert.channel}</TableCell>
                    <TableCell className="text-muted-foreground">{alert.config?.min_severity ?? 'P3'}</TableCell>
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
        <AlertForm open={open} onOpenChange={setOpen} onCreated={(alert) => setAlerts((prev) => [...prev, alert])} />
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
  { id: 'free', name: 'Free', monthlyPrice: 0, limit: '1 source, 5 tables, 7-day history' },
  { id: 'starter', name: 'Starter', monthlyPrice: 49, limit: '3 sources, 50 tables, 90-day history, Slack alerts' },
  { id: 'growth', name: 'Growth', monthlyPrice: 149, limit: 'Unlimited sources and tables, 1-year history, AI reports' },
  { id: 'agency', name: 'Agency', monthlyPrice: 299, limit: 'Multi-client workspaces, white-label reports, 15 members' },
]

function planPrice(plan, billingCycle) {
  if (plan.monthlyPrice === 0) return '$0'
  if (billingCycle === 'yearly') return `$${Math.round(plan.monthlyPrice * 12 * 0.8)}/yr`
  return `$${plan.monthlyPrice}/mo`
}

function BillingTab() {
  const orgName = storage.getItem('dw_org_name') || 'Your workspace'
  const [billingCycle, setBillingCycle] = useState('monthly')
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [upgrading, setUpgrading] = useState('')
  const [canceling, setCanceling] = useState(false)
  const [capturing, setCapturing] = useState(false)

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

  const upgrade = async (plan) => {
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
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="flex items-center gap-2 text-base font-medium"><CreditCard className="size-4 text-muted-foreground" />Current plan</h2>
              <p className="mt-1 text-sm text-muted-foreground">{orgName}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="capitalize">{loading ? 'Loading' : currentPlan}</Badge>
              <Badge variant={subscriptionStatus === 'active' ? 'default' : 'secondary'} className="capitalize">{capturing ? 'capturing' : subscriptionStatus}</Badge>
            </div>
          </div>
          {(status?.current_period_end || status?.next_billing_date) && (
            <p className="text-sm text-muted-foreground">
              Next billing date {new Date(status.current_period_end || status.next_billing_date).toLocaleDateString()}.
            </p>
          )}
          {currentPlan !== 'free' && (
            <Button type="button" variant="outline" className="w-fit" onClick={cancel} disabled={canceling}>
              {canceling ? 'Canceling...' : 'Cancel subscription'}
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-medium">Available plans</h3>
              <p className="mt-1 text-sm text-muted-foreground">PayPal checkout opens after you choose a plan.</p>
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
              return (
                <div key={plan.id} className={cn('rounded-lg border p-4', isCurrent && 'border-primary/40 bg-primary/5')}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <span className="font-medium text-sm">{plan.name}</span>
                      {isCurrent && <Badge variant="secondary" className="ml-2">Current</Badge>}
                    </div>
                    <span className="text-sm font-bold">{planPrice(plan, billingCycle)}</span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">{plan.limit}</p>
                  {!isCurrent && plan.id !== 'free' && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="mt-3 w-full"
                      onClick={() => upgrade(plan)}
                      disabled={Boolean(upgrading)}
                    >
                      {upgrading === plan.id && <Loader2 data-icon="inline-start" className="animate-spin" />}
                      {upgrading === plan.id ? 'Opening PayPal...' : 'Upgrade'}
                    </Button>
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
