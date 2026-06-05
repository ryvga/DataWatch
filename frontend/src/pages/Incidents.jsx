import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Clock, Search } from 'lucide-react'
import { getIncidents, getIncidentStats } from '../api/endpoints'
import IncidentCard from '../components/IncidentCard'
import { EmptyState, LoadingState, PageHeader } from '../components/app-ui'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'

const STATUS_TABS = [
  { value: 'active', label: 'Active', statuses: ['open', 'acknowledged', 'investigating'] },
  { value: 'open', label: 'Open' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'all', label: 'All' },
]

export default function Incidents() {
  const [incidents, setIncidents] = useState([])
  const [stats, setStats] = useState(null)
  const [activeTab, setActiveTab] = useState('active')
  const [severity, setSeverity] = useState('all')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  const load = (tab = activeTab, sev = severity) => {
    const params = { limit: 200 }
    const tabObj = STATUS_TABS.find(t => t.value === tab)
    if (tab !== 'all') {
      if (tabObj?.statuses) params.statuses = tabObj.statuses.join(',')
      else params.status = tab
    }
    if (sev !== 'all') params.severity = sev
    getIncidents(params).then(r => setIncidents(r.data)).finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    getIncidentStats().then(r => setStats(r.data)).catch(() => {})
  }, [])

  const filtered = incidents.filter(i =>
    !search || i.title.toLowerCase().includes(search.toLowerCase())
  )

  // Sort: P1 open first, then P2, then by detected time
  const sorted = [...filtered].sort((a, b) => {
    const sevOrder = { P1: 0, P2: 1, P3: 2 }
    const statusOrder = { open: 0, investigating: 1, acknowledged: 2, resolved: 3, muted: 4, ignored: 5 }
    if (sevOrder[a.severity] !== sevOrder[b.severity]) return sevOrder[a.severity] - sevOrder[b.severity]
    if (statusOrder[a.status] !== statusOrder[b.status]) return statusOrder[a.status] - statusOrder[b.status]
    return new Date(b.created_at) - new Date(a.created_at)
  })

  if (loading) return <LoadingState label="Loading incidents" />

  return (
    <div className="dw-page">
      <PageHeader
        title="Incidents"
        description={`${sorted.length} incident${sorted.length !== 1 ? 's' : ''} in current view`}
      />

      {/* ── Stats strip ── */}
      {stats && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Open', n: stats.open, color: 'text-red-600 dark:text-red-400' },
            { label: 'Investigating', n: stats.investigating, color: 'text-amber-600 dark:text-amber-400' },
            { label: 'P1 open', n: stats.p1_open, color: 'text-red-700 dark:text-red-300 font-bold' },
            { label: 'Resolved 7d', n: stats.resolved_7d, color: 'text-emerald-600 dark:text-emerald-400' },
            { label: 'Muted', n: stats.muted || 0, color: 'text-muted-foreground' },
          ].map(s => (
            <div key={s.label} className="flex items-center gap-1.5 rounded-lg border bg-card px-3 py-1.5 text-sm">
              <span className="text-muted-foreground">{s.label}</span>
              <span className={`font-bold tabular-nums ${s.color}`}>{s.n}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Filters ── */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Status tabs */}
        <div className="flex rounded-lg border bg-card p-0.5 gap-0.5">
          {STATUS_TABS.map(tab => (
            <button key={tab.value} type="button"
              onClick={() => { setActiveTab(tab.value); load(tab.value, severity) }}
              className={cn(
                'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                activeTab === tab.value
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              )}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Severity */}
        <Select value={severity} onValueChange={v => { setSeverity(v); load(activeTab, v) }}>
          <SelectTrigger className="w-32 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">All severities</SelectItem>
              <SelectItem value="P1">P1 — Critical</SelectItem>
              <SelectItem value="P2">P2 — High</SelectItem>
              <SelectItem value="P3">P3 — Medium</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-2 size-3.5 text-muted-foreground" />
          <input
            className="h-8 rounded-md border bg-background pl-7 pr-3 text-xs outline-none focus:ring-1 focus:ring-primary w-48"
            placeholder="Search incidents…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
      </div>

      <Card>
        <CardContent className="pt-4">
          {sorted.length === 0 ? (
            <EmptyState
              icon={activeTab === 'resolved' ? CheckCircle2 : AlertTriangle}
              title={activeTab === 'active' ? 'No active incidents' : 'No incidents found'}
              description={activeTab === 'active'
                ? 'All tables are healthy. Anomaly checks are running.'
                : 'Adjust filters or wait for anomaly checks to create incidents.'}
            />
          ) : (
            <div className="overflow-hidden rounded-lg border divide-y">
              {sorted.map((incident) => <IncidentCard key={incident.id} incident={incident} />)}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
