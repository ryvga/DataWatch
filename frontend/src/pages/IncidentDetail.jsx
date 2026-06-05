import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { notify } from '@/lib/notify'
import { ArrowLeft, Check, Circle, CircleCheck, Clock } from 'lucide-react'
import { acknowledgeIncident, getIncident, resolveIncident } from '../api/endpoints'
import HealthBadge from '../components/HealthBadge'
import NarrationPanel from '../components/NarrationPanel'
import SeverityBadge from '../components/SeverityBadge'
import { LoadingState, PageHeader, formatDateTime } from '../components/app-ui'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

function TimelineStep({ label, ts, active }) {
  const Icon = active ? CircleCheck : Circle
  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-3">
      <Icon className={active ? 'mt-0.5 size-4 text-primary' : 'mt-0.5 size-4 text-muted-foreground'} />
      <div>
        <p className={active ? 'text-sm font-medium text-foreground' : 'text-sm text-muted-foreground'}>{label}</p>
        {ts && <p className="text-xs text-muted-foreground">{formatDateTime(ts)}</p>}
      </div>
    </div>
  )
}

export default function IncidentDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [incident, setIncident] = useState(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    getIncident(id).then((response) => setIncident(response.data)).finally(() => setLoading(false))
  }, [id])

  const doAck = async () => {
    setUpdating(true)
    try {
      const response = await acknowledgeIncident(id)
      setIncident(response.data)
      notify.incident.acknowledged(incident.title)
    } finally {
      setUpdating(false)
    }
  }

  const doResolve = async () => {
    setUpdating(true)
    try {
      const response = await resolveIncident(id)
      setIncident(response.data)
      notify.incident.resolved(incident.title)
    } finally {
      setUpdating(false)
    }
  }

  if (loading) return <LoadingState label="Loading incident" />
  if (!incident) return <div className="dw-page text-destructive">Incident not found</div>

  return (
    <div className="dw-page">
      <Button type="button" variant="ghost" className="w-fit" onClick={() => nav(-1)}>
        <ArrowLeft data-icon="inline-start" />
        Back
      </Button>

      <PageHeader
        title={incident.title}
        description={`Detected ${formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}`}
        actions={
          <>
            <SeverityBadge severity={incident.severity} />
            <HealthBadge status={incident.status} />
            {incident.status === 'open' && (
              <Button type="button" variant="outline" onClick={doAck} disabled={updating}>
                <Clock data-icon="inline-start" />
                Acknowledge
              </Button>
            )}
            {incident.status !== 'resolved' && (
              <Button type="button" onClick={doResolve} disabled={updating}>
                <Check data-icon="inline-start" />
                Resolve
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex flex-col gap-5">
          <NarrationPanel incidentId={id} initialNarration={incident.llm_narration} />

          {incident.fired_checks?.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Fired checks</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="dw-table-wrap">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Check</TableHead>
                        <TableHead>Column</TableHead>
                        <TableHead>Observed</TableHead>
                        <TableHead>Score</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {incident.fired_checks.map((check, index) => (
                        <TableRow key={index}>
                          <TableCell className="font-mono text-xs text-destructive">{check.check_name}</TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">{check.column_name ?? '—'}</TableCell>
                          <TableCell>{check.observed_value ?? '—'}</TableCell>
                          <TableCell className="text-muted-foreground">
                            {check.deviation_score != null ? Number(check.deviation_score).toFixed(2) : '—'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <aside className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Timeline</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <TimelineStep label="Detected" ts={incident.created_at} active />
              <TimelineStep label="Acknowledged" ts={incident.acknowledged_at} active={!!incident.acknowledged_at} />
              <TimelineStep label="Resolved" ts={incident.resolved_at} active={!!incident.resolved_at} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Incident facts</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">Severity</span>
                <SeverityBadge severity={incident.severity} />
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">Status</span>
                <HealthBadge status={incident.status} />
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground">Checks fired</span>
                <span className="font-medium">{incident.fired_checks?.length ?? 0}</span>
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  )
}
