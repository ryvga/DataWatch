import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getTables, getSources, runTable } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'

export default function Tables() {
  const nav = useNavigate()
  const [tables, setTables] = useState([])
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [running, setRunning] = useState({})

  useEffect(() => {
    Promise.all([getTables(), getSources()])
      .then(([t, s]) => { setTables(t.data); setSources(s.data) })
      .catch((err) => setError(err.response?.data?.detail || 'Failed to load tables'))
      .finally(() => setLoading(false))
  }, [])

  const sourceMap = Object.fromEntries(sources.map((s) => [s.id, s]))

  const handleRun = async (e, id) => {
    e.stopPropagation()
    setRunning((p) => ({ ...p, [id]: true }))
    try { await runTable(id) } catch (_) {}
    setTimeout(() => setRunning((p) => { const n = { ...p }; delete n[id]; return n }), 2000)
  }

  if (loading) return <div className="p-8 text-gray-500">Loading…</div>

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Tables</h1>
          <p className="text-sm text-gray-500 mt-1">{tables.length} monitored</p>
        </div>
        <button onClick={() => nav('/settings')} className="btn-primary text-sm">
          + Add Table
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {tables.length === 0 && !error ? (
        <div className="card text-center py-16 space-y-3">
          <p className="text-gray-400 font-medium">No tables monitored yet</p>
          <p className="text-sm text-gray-600">Add a data source and configure tables in Settings.</p>
          <button onClick={() => nav('/settings')} className="btn-primary text-sm mt-2">
            Go to Settings
          </button>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Table</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Source</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Rows</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Last Profile</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Interval</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {tables.map((t) => (
                <tr
                  key={t.id}
                  className="table-row cursor-pointer"
                  onClick={() => nav(`/tables/${t.id}`)}
                >
                  <td className="px-4 py-3 font-mono text-gray-200">
                    {t.schema_name}.{t.table_name}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {sourceMap[t.source_id]?.name ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {t.latest_profile?.row_count?.toLocaleString() ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {t.last_profiled_at ? new Date(t.last_profiled_at).toLocaleString() : 'Never'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{t.check_interval_minutes}m</td>
                  <td className="px-4 py-3">
                    <HealthBadge status={t.latest_profile?.error ? 'error' : t.is_active ? 'healthy' : 'paused'} />
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={(e) => handleRun(e, t.id)}
                      disabled={!!running[t.id]}
                      className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors disabled:opacity-50"
                    >
                      {running[t.id] ? 'Queued…' : '▶ Run'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
