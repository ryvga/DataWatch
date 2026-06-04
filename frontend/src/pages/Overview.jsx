import { useEffect, useState } from 'react'
import { getIncidents, getSources, getTables, getHealth } from '../api/endpoints'
import IncidentCard from '../components/IncidentCard'

function HealthCard({ source, tables }) {
  const healthy = tables.filter((t) => !t.latest_profile?.error).length
  const total = tables.length
  const pct = total ? Math.round((healthy / total) * 100) : 0
  const color = pct >= 90 ? 'text-green-400' : pct >= 70 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-gray-300 truncate">{source.name}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${
          source.status === 'connected'
            ? 'bg-green-500/10 text-green-400 border-green-500/20'
            : 'bg-red-500/10 text-red-400 border-red-500/20'
        }`}>{source.status}</span>
      </div>
      <div className={`text-3xl font-bold ${color}`}>{pct}%</div>
      <div className="text-xs text-gray-500 mt-1">{healthy}/{total} tables healthy</div>
    </div>
  )
}

export default function Overview() {
  const [sources, setSources] = useState([])
  const [tables, setTables] = useState([])
  const [incidents, setIncidents] = useState([])
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [s, t, i, h] = await Promise.all([
        getSources(), getTables(), getIncidents({ status: 'open', limit: 20 }), getHealth()
      ])
      setSources(s.data)
      setTables(t.data)
      setIncidents(i.data)
      setHealth(h.data)
    } catch (_) {}
    setLoading(false)
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 60000)
    return () => clearInterval(timer)
  }, [])

  if (loading) return <div className="p-8 text-gray-500">Loading…</div>

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Overview</h1>
          <p className="text-sm text-gray-500 mt-1">
            {tables.length} tables monitored · {incidents.length} open incidents
            {health && ` · ${health.scheduler_jobs} scheduler jobs`}
          </p>
        </div>
        <button onClick={load} className="btn-secondary">Refresh</button>
      </div>

      {/* Health cards */}
      {sources.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Data Sources</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {sources.map((s) => (
              <HealthCard key={s.id} source={s} tables={tables.filter((t) => t.source_id === s.id)} />
            ))}
          </div>
        </section>
      )}

      {/* Active incidents */}
      <section>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
          Active Incidents {incidents.length > 0 && `(${incidents.length})`}
        </h2>
        <div className="card p-0 overflow-hidden">
          {incidents.length === 0 ? (
            <div className="px-4 py-8 text-center text-gray-600 text-sm">
              ✅ No open incidents
            </div>
          ) : (
            incidents
              .sort((a, b) => {
                const sev = { P1: 0, P2: 1, P3: 2 }
                return (sev[a.severity] ?? 3) - (sev[b.severity] ?? 3)
              })
              .map((i) => <IncidentCard key={i.id} incident={i} />)
          )}
        </div>
      </section>

      {/* Recent tables */}
      {tables.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Monitored Tables</h2>
          <div className="card p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Table</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Rows</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Last Profile</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Status</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((t) => (
                  <tr key={t.id} className="table-row">
                    <td className="px-4 py-3 font-mono text-gray-200">
                      {t.schema_name}.{t.table_name}
                    </td>
                    <td className="px-4 py-3 text-gray-400">
                      {t.latest_profile?.row_count?.toLocaleString() ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {t.last_profiled_at
                        ? new Date(t.last_profiled_at).toLocaleString()
                        : 'Never'}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${
                        t.latest_profile?.error
                          ? 'bg-red-500/10 text-red-400 border-red-500/20'
                          : t.is_active
                            ? 'bg-green-500/10 text-green-400 border-green-500/20'
                            : 'bg-gray-500/10 text-gray-400 border-gray-500/20'
                      }`}>
                        {t.latest_profile?.error ? 'error' : t.is_active ? 'active' : 'paused'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
