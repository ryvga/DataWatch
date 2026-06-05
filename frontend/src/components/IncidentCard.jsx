import { formatDistanceToNow } from 'date-fns'
import { ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import SeverityBadge from './SeverityBadge'
import HealthBadge from './HealthBadge'

export default function IncidentCard({ incident }) {
  const nav = useNavigate()

  return (
    <button
      type="button"
      className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 border-b px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-muted/60"
      onClick={() => nav(`/incidents/${incident.id}`)}
    >
      <SeverityBadge severity={incident.severity} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium text-foreground">{incident.title}</span>
        <span className="block text-xs text-muted-foreground">
          {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
        </span>
      </span>
      <HealthBadge status={incident.status} />
      <ChevronRight className="size-4 text-muted-foreground" aria-hidden="true" />
    </button>
  )
}
