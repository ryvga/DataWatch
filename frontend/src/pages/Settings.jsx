import { useEffect, useState } from 'react'
import {
  getSources, createSource, testSource, deleteSource,
  getTables, createTable, discoverSource,
  getAlerts, createAlert, deleteAlert, testAlert,
} from '../api/endpoints'

const TABS = ['Data Sources', 'Tables', 'Alerts', 'API Keys']

// ── Data Sources Tab ──────────────────────────────────────────────────────────
function SourcesTab() {
  const [sources, setSources] = useState([])
  const [form, setForm] = useState({ name: '', type: 'postgres', connection_config: '{}' })
  const [adding, setAdding] = useState(false)
  const [testing, setTesting] = useState({})

  useEffect(() => { getSources().then(r => setSources(r.data)) }, [])

  const submit = async (e) => {
    e.preventDefault()
    try {
      const config = JSON.parse(form.connection_config)
      const r = await createSource({ name: form.name, type: form.type, connection_config: config })
      setSources(prev => [...prev, r.data])
      setAdding(false)
      setForm({ name: '', type: 'postgres', connection_config: '{}' })
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to create source')
    }
  }

  const test = async (id) => {
    setTesting(prev => ({ ...prev, [id]: 'testing' }))
    try {
      const r = await testSource(id)
      setTesting(prev => ({ ...prev, [id]: r.data.connected ? 'ok' : 'fail' }))
    } catch (_) { setTesting(prev => ({ ...prev, [id]: 'fail' })) }
    setTimeout(() => setTesting(prev => { const n = {...prev}; delete n[id]; return n }), 3000)
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-sm font-semibold text-gray-300">Data Sources</h2>
        <button onClick={() => setAdding(!adding)} className="btn-primary text-xs">+ Add Source</button>
      </div>

      {adding && (
        <form onSubmit={submit} className="card space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><label className="label">Name</label><input className="input" value={form.name} onChange={e => setForm(p => ({...p, name: e.target.value}))} required /></div>
            <div>
              <label className="label">Type</label>
              <select className="input" value={form.type} onChange={e => setForm(p => ({...p, type: e.target.value}))}>
                {['postgres', 'bigquery', 'duckdb', 'snowflake'].map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Connection Config (JSON)</label>
            <textarea
              className="input font-mono text-xs h-28"
              value={form.connection_config}
              onChange={e => setForm(p => ({...p, connection_config: e.target.value}))}
              placeholder={'{\n  "host": "localhost",\n  "port": 5432,\n  "database": "mydb",\n  "username": "user",\n  "password": "pass"\n}'}
            />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-xs">Create</button>
            <button type="button" onClick={() => setAdding(false)} className="btn-secondary text-xs">Cancel</button>
          </div>
        </form>
      )}

      <div className="card p-0 overflow-hidden">
        {sources.length === 0 ? (
          <p className="p-6 text-center text-gray-500 text-sm">No data sources yet</p>
        ) : sources.map(s => (
          <div key={s.id} className="flex items-center gap-3 px-4 py-3 table-row">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200">{s.name}</p>
              <p className="text-xs text-gray-500">{s.type} · {s.status}</p>
            </div>
            <button
              onClick={() => test(s.id)}
              className={`text-xs px-3 py-1 rounded-lg border transition-colors ${
                testing[s.id] === 'ok' ? 'border-green-500 text-green-400' :
                testing[s.id] === 'fail' ? 'border-red-500 text-red-400' :
                'border-gray-700 text-gray-400 hover:border-gray-500'
              }`}
            >
              {testing[s.id] === 'testing' ? '…' : testing[s.id] === 'ok' ? '✓ Connected' : testing[s.id] === 'fail' ? '✗ Failed' : 'Test'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tables Tab ────────────────────────────────────────────────────────────────
function TablesTab() {
  const [sources, setSources] = useState([])
  const [tables, setTables] = useState([])
  const [schemas, setSchemas] = useState([])
  const [form, setForm] = useState({ source_id: '', schema_name: '', table_name: '', freshness_column: '', check_interval_minutes: 60, sensitivity: 3.0 })
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    Promise.all([getSources(), getTables()]).then(([s, t]) => {
      setSources(s.data)
      setTables(t.data)
      if (s.data.length) setForm(p => ({...p, source_id: s.data[0].id}))
    })
  }, [])

  const discover = async (sourceId) => {
    try {
      const r = await discoverSource(sourceId)
      setSchemas(r.data.schemas)
    } catch (_) { setSchemas([]) }
  }

  const submit = async (e) => {
    e.preventDefault()
    try {
      const r = await createTable({
        ...form,
        check_interval_minutes: Number(form.check_interval_minutes),
        sensitivity: Number(form.sensitivity),
      })
      setTables(prev => [...prev, r.data])
      setAdding(false)
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-sm font-semibold text-gray-300">Monitored Tables</h2>
        <button onClick={() => setAdding(!adding)} className="btn-primary text-xs">+ Add Table</button>
      </div>

      {adding && (
        <form onSubmit={submit} className="card space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Source</label>
              <select className="input" value={form.source_id}
                onChange={e => { setForm(p => ({...p, source_id: e.target.value})); discover(e.target.value) }}>
                {sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Schema</label>
              {schemas.length > 0 ? (
                <select className="input" value={form.schema_name}
                  onChange={e => setForm(p => ({...p, schema_name: e.target.value}))}>
                  <option value="">Select schema…</option>
                  {schemas.map(s => <option key={s.name}>{s.name}</option>)}
                </select>
              ) : (
                <input className="input" value={form.schema_name} placeholder="public"
                  onChange={e => setForm(p => ({...p, schema_name: e.target.value}))} />
              )}
            </div>
            <div><label className="label">Table Name</label><input className="input" value={form.table_name} onChange={e => setForm(p => ({...p, table_name: e.target.value}))} required /></div>
            <div><label className="label">Freshness Column</label><input className="input" value={form.freshness_column} placeholder="updated_at" onChange={e => setForm(p => ({...p, freshness_column: e.target.value}))} /></div>
            <div><label className="label">Check Interval (min)</label><input className="input" type="number" min={1} value={form.check_interval_minutes} onChange={e => setForm(p => ({...p, check_interval_minutes: e.target.value}))} /></div>
            <div><label className="label">Sensitivity (z-score)</label><input className="input" type="number" step="0.1" min={1} value={form.sensitivity} onChange={e => setForm(p => ({...p, sensitivity: e.target.value}))} /></div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-xs">Add Table</button>
            <button type="button" onClick={() => setAdding(false)} className="btn-secondary text-xs">Cancel</button>
          </div>
        </form>
      )}

      <div className="card p-0 overflow-hidden">
        {tables.length === 0 ? (
          <p className="p-6 text-center text-gray-500 text-sm">No tables monitored yet</p>
        ) : tables.map(t => (
          <div key={t.id} className="flex items-center gap-3 px-4 py-3 table-row">
            <div className="flex-1">
              <p className="text-sm font-mono text-gray-200">{t.schema_name}.{t.table_name}</p>
              <p className="text-xs text-gray-500">every {t.check_interval_minutes}m · sensitivity {t.sensitivity}</p>
            </div>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${
              t.is_active ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-gray-500/10 text-gray-400 border-gray-500/20'
            }`}>{t.is_active ? 'active' : 'paused'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Alerts Tab ────────────────────────────────────────────────────────────────
function AlertsTab() {
  const [alerts, setAlerts] = useState([])
  const [form, setForm] = useState({ channel: 'slack', config: '{}' })
  const [adding, setAdding] = useState(false)
  const [testing, setTesting] = useState({})

  useEffect(() => { getAlerts().then(r => setAlerts(r.data)) }, [])

  const EXAMPLES = {
    slack: '{\n  "webhook_url": "https://hooks.slack.com/...",\n  "min_severity": "P2"\n}',
    email: '{\n  "to": ["you@company.com"],\n  "min_severity": "P3"\n}',
    pagerduty: '{\n  "routing_key": "YOUR_KEY",\n  "min_severity": "P1"\n}',
  }

  const submit = async (e) => {
    e.preventDefault()
    try {
      const r = await createAlert({ channel: form.channel, config: JSON.parse(form.config) })
      setAlerts(prev => [...prev, r.data])
      setAdding(false)
    } catch (err) { alert(err.response?.data?.detail || 'Failed') }
  }

  const test = async (id) => {
    setTesting(prev => ({...prev, [id]: 'testing'}))
    try {
      await testAlert(id)
      setTesting(prev => ({...prev, [id]: 'ok'}))
    } catch (_) { setTesting(prev => ({...prev, [id]: 'fail'})) }
    setTimeout(() => setTesting(prev => { const n = {...prev}; delete n[id]; return n }), 3000)
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-sm font-semibold text-gray-300">Alert Configs</h2>
        <button onClick={() => setAdding(!adding)} className="btn-primary text-xs">+ Add Alert</button>
      </div>

      {adding && (
        <form onSubmit={submit} className="card space-y-3">
          <div>
            <label className="label">Channel</label>
            <select className="input" value={form.channel}
              onChange={e => setForm(p => ({...p, channel: e.target.value, config: EXAMPLES[e.target.value]}))}>
              <option value="slack">Slack</option>
              <option value="email">Email</option>
              <option value="pagerduty">PagerDuty</option>
            </select>
          </div>
          <div>
            <label className="label">Config (JSON)</label>
            <textarea className="input font-mono text-xs h-28" value={form.config}
              onChange={e => setForm(p => ({...p, config: e.target.value}))} />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-xs">Create</button>
            <button type="button" onClick={() => setAdding(false)} className="btn-secondary text-xs">Cancel</button>
          </div>
        </form>
      )}

      <div className="card p-0 overflow-hidden">
        {alerts.length === 0 ? (
          <p className="p-6 text-center text-gray-500 text-sm">No alert configs yet</p>
        ) : alerts.map(a => (
          <div key={a.id} className="flex items-center gap-3 px-4 py-3 table-row">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200 capitalize">{a.channel}</p>
              <p className="text-xs text-gray-500">min severity: {a.config?.min_severity ?? 'P3'}</p>
            </div>
            <button onClick={() => test(a.id)} className={`text-xs px-3 py-1 rounded-lg border transition-colors ${
              testing[a.id] === 'ok' ? 'border-green-500 text-green-400' :
              testing[a.id] === 'fail' ? 'border-red-500 text-red-400' :
              'border-gray-700 text-gray-400 hover:border-gray-500'
            }`}>
              {testing[a.id] === 'testing' ? '…' : testing[a.id] === 'ok' ? '✓ Sent' : testing[a.id] === 'fail' ? '✗ Failed' : 'Test'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── API Keys Tab ──────────────────────────────────────────────────────────────
function ApiKeysTab() {
  const [key] = useState(localStorage.getItem('dw_api_key') || '')
  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-gray-300">API Keys</h2>
      <div className="card">
        <p className="text-xs text-gray-500 mb-2">Your current API key (stored locally)</p>
        <div className="flex items-center gap-3">
          <code className="flex-1 bg-gray-800 px-3 py-2 rounded text-sm font-mono text-green-400 truncate">
            {key ? key.slice(0, 10) + '•'.repeat(20) : 'Not set'}
          </code>
        </div>
        {!key && (
          <p className="mt-3 text-xs text-yellow-400">
            Set your API key: <code className="bg-gray-800 px-1 rounded">localStorage.setItem('dw_api_key', 'dw_...')</code>
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Settings() {
  const [tab, setTab] = useState(0)
  const COMPONENTS = [SourcesTab, TablesTab, AlertsTab, ApiKeysTab]
  const TabComponent = COMPONENTS[tab]

  return (
    <div className="p-8 space-y-6">
      <h1 className="text-2xl font-bold text-white">Settings</h1>
      <div className="flex gap-1 border-b border-gray-800">
        {TABS.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(i)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === i ? 'text-blue-400 border-b-2 border-blue-500' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      <TabComponent />
    </div>
  )
}
