import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTable, getProfiles, getChecks, getIncidents, runTable } from '../api/endpoints'
import MetricChart from '../components/MetricChart'
import SeverityBadge from '../components/SeverityBadge'
import HealthBadge from '../components/HealthBadge'

export default function TableDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [table, setTable] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [checks, setChecks] = useState([])
  const [incidents, setIncidents] = useState([])
  const [selectedCol, setSelectedCol] = useState(null)
  const [running, setRunning] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getTable(id),
      getProfiles(id, { limit: 30 }),
      getChecks(id, { limit: 100 }),
      getIncidents({ table_id: id, limit: 20 }),
    ]).then(([t, p, c, i]) => {
      setTable(t.data)
      setProfiles(p.data)
      setChecks(c.data)
      setIncidents(i.data)
      // Default selected col from latest profile
      const cols = Object.keys(t.data.latest_profile?.column_metrics || {})
      if (cols.length) setSelectedCol(cols[0])
    }).finally(() => setLoading(false))
  }, [id])

  const handleRun = async () => {
    setRunning(true)
    try { await runTable(id) } catch (_) {}
    setTimeout(() => setRunning(false), 2000)
  }

  if (loading) return <div className="p-8 text-gray-500">Loading…</div>
  if (!table) return <div className="p-8 text-red-400">Table not found</div>

  const latestProfile = table.latest_profile
  const allCols = Object.keys(latestProfile?.column_metrics || {})

  // Find anomalous profiles (those with failed checks)
  const anomalousProfileIds = new Set(checks.filter(c => c.status === 'failed').map(c => c.profile_id))
  const anomalousDots = profiles.filter(p => anomalousProfileIds.has(p.id))

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button onClick={() => nav(-1)} className="text-xs text-gray-500 hover:text-gray-300 mb-2 flex items-center gap-1">
            ← Back
          </button>
          <h1 className="text-xl font-bold text-white font-mono">
            {table.schema_name}.{table.table_name}
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <HealthBadge status={table.is_active ? 'healthy' : 'paused'} />
            <span className="text-xs text-gray-500">every {table.check_interval_minutes}m</span>
            {latestProfile && (
              <span className="text-xs text-gray-500">
                · {latestProfile.row_count?.toLocaleString() ?? '?'} rows
              </span>
            )}
          </div>
        </div>
        <button onClick={handleRun} disabled={running} className="btn-primary">
          {running ? 'Queued…' : '▶ Run Now'}
        </button>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <p className="text-xs font-medium text-gray-500 mb-3">Row Count (30 days)</p>
          <MetricChart data={profiles} dataKey="row_count" anomalies={anomalousDots} label="rows" />
        </div>
        <div className="card">
          <p className="text-xs font-medium text-gray-500 mb-3">Freshness (seconds)</p>
          <MetricChart data={profiles} dataKey="freshness_seconds" color="#8b5cf6" label="seconds" />
        </div>
        {allCols.length > 0 && (
          <div className="card lg:col-span-2">
            <div className="flex items-center gap-3 mb-3">
              <p className="text-xs font-medium text-gray-500">Null Rate</p>
              <select
                value={selectedCol || ''}
                onChange={(e) => setSelectedCol(e.target.value)}
                className="bg-gray-800 border border-gray-700 text-gray-300 rounded px-2 py-1 text-xs"
              >
                {allCols.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <MetricChart
              data={profiles.map(p => ({
                ...p,
                null_rate: p.column_metrics?.[selectedCol]?.null_rate,
              }))}
              dataKey="null_rate"
              color="#f59e0b"
              label="null rate"
            />
          </div>
        )}
      </div>

      {/* Schema panel */}
      {latestProfile?.column_metrics && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Column Health</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  {['Column', 'Null Rate', 'Distinct', 'Min', 'Max', 'Mean'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-xs text-gray-500 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allCols.map((col) => {
                  const m = latestProfile.column_metrics[col] || {}
                  const nullRate = m.null_rate ?? null
                  const nullColor = nullRate === null ? '' : nullRate > 0.5 ? 'text-red-400' : nullRate > 0.1 ? 'text-yellow-400' : 'text-green-400'
                  return (
                    <tr key={col} className="table-row">
                      <td className="px-3 py-2 font-mono text-gray-200 text-xs">{col}</td>
                      <td className={`px-3 py-2 text-xs ${nullColor}`}>
                        {nullRate !== null ? (nullRate * 100).toFixed(1) + '%' : '—'}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">{m.distinct_count?.toLocaleString() ?? '—'}</td>
                      <td className="px-3 py-2 text-xs text-gray-400 truncate max-w-[120px]">{m.min ?? '—'}</td>
                      <td className="px-3 py-2 text-xs text-gray-400 truncate max-w-[120px]">{m.max ?? '—'}</td>
                      <td className="px-3 py-2 text-xs text-gray-400">{m.mean != null ? Number(m.mean).toFixed(2) : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Incident history */}
      {incidents.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Incident History</h2>
          <div className="space-y-2">
            {incidents.map(i => (
              <div
                key={i.id}
                className="flex items-center gap-3 p-3 bg-gray-800/50 rounded-lg cursor-pointer hover:bg-gray-800"
                onClick={() => nav(`/incidents/${i.id}`)}
              >
                <SeverityBadge severity={i.severity} />
                <span className="flex-1 text-sm text-gray-200 truncate">{i.title}</span>
                <HealthBadge status={i.status} />
                <span className="text-xs text-gray-600">
                  {new Date(i.created_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
