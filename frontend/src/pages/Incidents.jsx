import { useEffect, useState } from 'react'
import { getIncidents } from '../api/endpoints'
import IncidentCard from '../components/IncidentCard'

export default function Incidents() {
  const [incidents, setIncidents] = useState([])
  const [status, setStatus] = useState('')
  const [severity, setSeverity] = useState('')
  const [assignedToMe, setAssignedToMe] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = (s = status, sev = severity, mine = assignedToMe) => {
    const params = { limit: 100 }
    if (s) params.status = s
    if (sev) params.severity = sev
    if (mine) params.assigned_to_me = true
    getIncidents(params).then(r => setIncidents(r.data)).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Incidents</h1>
        <div className="flex gap-2 flex-wrap">
          <select
            value={status}
            onChange={(e) => { setStatus(e.target.value); load(e.target.value, severity, assignedToMe) }}
            className="bg-gray-800 border border-gray-700 text-gray-300 rounded-lg px-3 py-1.5 text-sm"
          >
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>
          <select
            value={severity}
            onChange={(e) => { setSeverity(e.target.value); load(status, e.target.value, assignedToMe) }}
            className="bg-gray-800 border border-gray-700 text-gray-300 rounded-lg px-3 py-1.5 text-sm"
          >
            <option value="">All severities</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
          </select>
          <button
            type="button"
            onClick={() => {
              const next = !assignedToMe
              setAssignedToMe(next)
              load(status, severity, next)
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
              assignedToMe
                ? 'bg-blue-600/20 text-blue-400 border-blue-500/40'
                : 'bg-gray-800 text-gray-400 border-gray-700 hover:text-gray-200'
            }`}
          >
            👤 Mine
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-500 text-sm">Loading…</div>
      ) : incidents.length === 0 ? (
        <div className="card text-center text-gray-500 py-12">No incidents found</div>
      ) : (
        <div className="card p-0 overflow-hidden">
          {incidents.map(i => <IncidentCard key={i.id} incident={i} />)}
        </div>
      )}
    </div>
  )
}
