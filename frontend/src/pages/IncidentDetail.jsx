import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import { getIncident, acknowledgeIncident, resolveIncident, assignIncident, getTeams, getOrgMembers } from '../api/endpoints'
import NarrationPanel from '../components/NarrationPanel'
import SeverityBadge from '../components/SeverityBadge'
import HealthBadge from '../components/HealthBadge'
import UserPicker from '../components/UserPicker'

function TimelineStep({ label, ts, active }) {
  return (
    <div className={`flex items-center gap-3 ${active ? 'text-gray-200' : 'text-gray-600'}`}>
      <div className={`w-2.5 h-2.5 rounded-full border-2 flex-shrink-0 ${
        active ? 'border-blue-500 bg-blue-500' : 'border-gray-700'
      }`} />
      <div>
        <p className="text-xs font-medium">{label}</p>
        {ts && <p className="text-xs opacity-60">{new Date(ts).toLocaleString()}</p>}
      </div>
    </div>
  )
}

function AssignmentCard({ incident, teams, orgMembers, onAssigned }) {
  const [assigneeId, setAssigneeId] = useState(incident?.assignee_id || '')
  const [teamId, setTeamId] = useState(incident?.assigned_team_id || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const assigneeName = incident?.assignee_name ||
    orgMembers.find(m => m.id === incident?.assignee_id)?.full_name ||
    orgMembers.find(m => m.id === incident?.assignee_id)?.email

  const teamName = incident?.assigned_team_name ||
    teams.find(t => t.id === incident?.assigned_team_id)?.name

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      await assignIncident(incident.id, {
        assignee_id: assigneeId || null,
        assigned_team_id: teamId || null,
      })
      onAssigned?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update assignment')
    } finally {
      setSaving(false)
    }
  }

  const changed = assigneeId !== (incident?.assignee_id || '') ||
    teamId !== (incident?.assigned_team_id || '')

  return (
    <div className="card space-y-4">
      <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
        <span>👤</span> Assignment
      </h3>

      {/* Current assignment chips */}
      {(incident?.assignee_id || incident?.assigned_team_id) && (
        <div className="flex flex-wrap gap-2">
          {incident.assignee_id && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-700 bg-gray-800/50 px-2.5 py-1 text-xs font-medium text-gray-300">
              👤 {assigneeName || 'Assigned user'}
            </span>
          )}
          {incident.assigned_team_id && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-700/40 bg-blue-600/10 px-2.5 py-1 text-xs font-medium text-blue-400">
              👥 {teamName || 'Assigned team'}
            </span>
          )}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label className="label">Assignee</label>
          <UserPicker
            value={assigneeId}
            onChange={setAssigneeId}
            placeholder="Assign to user…"
            members={orgMembers}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="label">Team</label>
          <select
            className="input"
            value={teamId}
            onChange={e => setTeamId(e.target.value)}
          >
            <option value="">No team</option>
            {teams.map(t => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Acknowledged by / Resolved by info */}
      {(incident?.acknowledged_by_id || incident?.resolved_by_id) && (
        <div className="flex flex-wrap gap-4 text-xs text-gray-500 border-t border-gray-800 pt-3">
          {incident.acknowledged_by_id && (
            <span>Acknowledged by <strong className="text-gray-300">{
              orgMembers.find(m => m.id === incident.acknowledged_by_id)?.full_name ||
              orgMembers.find(m => m.id === incident.acknowledged_by_id)?.email ||
              'a team member'
            }</strong></span>
          )}
          {incident.resolved_by_id && (
            <span>Resolved by <strong className="text-gray-300">{
              orgMembers.find(m => m.id === incident.resolved_by_id)?.full_name ||
              orgMembers.find(m => m.id === incident.resolved_by_id)?.email ||
              'a team member'
            }</strong></span>
          )}
        </div>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}

      {changed && (
        <button
          type="button"
          className="btn-primary text-xs w-fit"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Saving…' : 'Save assignment'}
        </button>
      )}
    </div>
  )
}

export default function IncidentDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [incident, setIncident] = useState(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)
  const [teams, setTeams] = useState([])
  const [orgMembers, setOrgMembers] = useState([])

  useEffect(() => {
    getIncident(id).then(r => setIncident(r.data)).finally(() => setLoading(false))
    getTeams().then(r => setTeams(r.data || [])).catch(() => {})
    getOrgMembers().then(r => {
      const raw = r.data
      setOrgMembers(Array.isArray(raw) ? raw : raw?.items || raw?.members || [])
    }).catch(() => {})
  }, [id])

  const doAck = async () => {
    setUpdating(true)
    const r = await acknowledgeIncident(id)
    setIncident(r.data)
    setUpdating(false)
  }

  const doResolve = async () => {
    setUpdating(true)
    const r = await resolveIncident(id)
    setIncident(r.data)
    setUpdating(false)
  }

  if (loading) return <div className="p-8 text-gray-500">Loading…</div>
  if (!incident) return <div className="p-8 text-red-400">Incident not found</div>

  return (
    <div className="p-8 max-w-4xl space-y-6">
      {/* Header */}
      <div>
        <button onClick={() => nav(-1)} className="text-xs text-gray-500 hover:text-gray-300 mb-3 flex items-center gap-1">
          ← Back
        </button>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 flex-wrap">
            <SeverityBadge severity={incident.severity} />
            <HealthBadge status={incident.status} />
            <h1 className="text-lg font-semibold text-white">{incident.title}</h1>
          </div>
          <div className="flex gap-2 flex-shrink-0">
            {incident.status === 'open' && (
              <button onClick={doAck} disabled={updating} className="btn-secondary text-xs">
                Acknowledge
              </button>
            )}
            {incident.status !== 'resolved' && (
              <button onClick={doResolve} disabled={updating} className="btn-primary text-xs">
                Resolve
              </button>
            )}
          </div>
        </div>
        <p className="text-sm text-gray-500 mt-2">
          Detected {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main — narration + checks */}
        <div className="lg:col-span-2 space-y-5">
          <NarrationPanel incidentId={id} initialNarration={incident.llm_narration} />

          {/* Fired checks table */}
          {incident.fired_checks?.length > 0 && (
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Fired Checks</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-800">
                      {['Check', 'Column', 'Observed', 'Score'].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-gray-500 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {incident.fired_checks.map((c, i) => (
                      <tr key={i} className="table-row">
                        <td className="px-3 py-2 font-mono text-red-400">{c.check_name}</td>
                        <td className="px-3 py-2 text-gray-400 font-mono">{c.column_name ?? '—'}</td>
                        <td className="px-3 py-2 text-gray-300">{c.observed_value ?? '—'}</td>
                        <td className="px-3 py-2 text-gray-400">
                          {c.deviation_score != null ? Number(c.deviation_score).toFixed(2) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar — assignment + timeline */}
        <div className="space-y-5">
          <AssignmentCard
            incident={incident}
            teams={teams}
            orgMembers={orgMembers}
            onAssigned={() => getIncident(id).then(r => setIncident(r.data))}
          />

          <div className="card">
            <h3 className="text-sm font-semibold text-gray-300 mb-4">Timeline</h3>
            <div className="space-y-4">
              <TimelineStep label="Detected" ts={incident.created_at} active={true} />
              <TimelineStep
                label="Acknowledged"
                ts={incident.acknowledged_at}
                active={!!incident.acknowledged_at}
              />
              <TimelineStep
                label="Resolved"
                ts={incident.resolved_at}
                active={!!incident.resolved_at}
              />
            </div>
          </div>

          <div className="card text-xs text-gray-400 space-y-2">
            <div className="flex justify-between">
              <span>Severity</span>
              <SeverityBadge severity={incident.severity} />
            </div>
            <div className="flex justify-between">
              <span>Status</span>
              <HealthBadge status={incident.status} />
            </div>
            <div className="flex justify-between">
              <span>Checks fired</span>
              <span className="text-gray-300">{incident.fired_checks?.length ?? 0}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
