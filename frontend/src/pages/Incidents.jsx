import { useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { getIncidents } from '../api/endpoints'
import IncidentCard from '../components/IncidentCard'
import { EmptyState, LoadingState, PageHeader } from '../components/app-ui'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

export default function Incidents() {
  const [incidents, setIncidents] = useState([])
  const [status, setStatus] = useState('all')
  const [severity, setSeverity] = useState('all')
  const [loading, setLoading] = useState(true)

  const load = (nextStatus = status, nextSeverity = severity) => {
    const params = { limit: 100 }
    if (nextStatus !== 'all') params.status = nextStatus
    if (nextSeverity !== 'all') params.severity = nextSeverity
    getIncidents(params).then((response) => setIncidents(response.data)).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  if (loading) return <LoadingState label="Loading incidents" />

  return (
    <div className="dw-page">
      <PageHeader
        title="Incidents"
        description={`${incidents.length} incidents in the current view`}
        actions={
          <>
            <Select value={status} onValueChange={(value) => { setStatus(value); load(value, severity) }}>
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="open">Open</SelectItem>
                  <SelectItem value="acknowledged">Acknowledged</SelectItem>
                  <SelectItem value="resolved">Resolved</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <Select value={severity} onValueChange={(value) => { setSeverity(value); load(status, value) }}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">All severities</SelectItem>
                  <SelectItem value="P1">P1</SelectItem>
                  <SelectItem value="P2">P2</SelectItem>
                  <SelectItem value="P3">P3</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </>
        }
      />

      <Card>
        <CardContent className="pt-6">
          {incidents.length === 0 ? (
            <EmptyState icon={AlertTriangle} title="No incidents found" description="Adjust filters or wait for anomaly checks to create incidents." />
          ) : (
            <div className="overflow-hidden rounded-lg border">
              {incidents.map((incident) => <IncidentCard key={incident.id} incident={incident} />)}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
