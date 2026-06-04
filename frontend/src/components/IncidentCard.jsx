import { formatDistanceToNow } from 'date-fns'
import { useNavigate } from 'react-router-dom'
import SeverityBadge from './SeverityBadge'
import HealthBadge from './HealthBadge'

export default function IncidentCard({ incident }) {
  const nav = useNavigate()
  return (
    <div
      className="flex items-center gap-3 px-4 py-3 table-row cursor-pointer"
      onClick={() => nav(`/incidents/${incident.id}`)}
    >
      <SeverityBadge severity={incident.severity} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-100 truncate">{incident.title}</p>
        <p className="text-xs text-gray-500 mt-0.5">
          {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
        </p>
      </div>
      <HealthBadge status={incident.status} />
    </div>
  )
}
