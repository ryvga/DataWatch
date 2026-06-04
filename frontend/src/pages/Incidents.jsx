import { useEffect, useState } from 'react'
import { getIncidents } from '../api/endpoints'
import IncidentCard from '../components/IncidentCard'

export default function Incidents() {
  const [incidents, setIncidents] = useState([])
  const [status, setStatus] = useState('')
  const [severity, setSeverity] = useState('')
  const [loading, setLoading] = useState(true)

  const load = (s = status, sev = severity) => {
    const params = { limit: 100 }
    if (s) params.status = s
    if (sev) params.severity = sev
    getIncidents(params).then(r => setIncidents(r.data)).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Incidents</h1>
        <div className="flex gap-2">
          <select
            value={status}
            onChange={(e) => { setStatus(e.target.value); load(e.target.value, severity) }}
            className="bg-gray-800 border border-gray-700 text-gray-300 rounded-lg px-3 py-1.5 text-sm"
          >
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>
          <select
            value={severity}
            onChange={(e) => { setSeverity(e.target.value); load(status, e.target.value) }}
            className="bg-gray-800 border border-gray-700 text-gray-300 rounded-lg px-3 py-1.5 text-sm"
          >
            <option value="">All severities</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
          </select>
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
