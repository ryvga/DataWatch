import { useState, useEffect } from 'react'
import { notify } from '@/lib/notify'
import {
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  Users,
  UserPlus,
  Clock,
  AlertTriangle,
  Table2,
  UserX,
  Shield,
} from 'lucide-react'
import {
  getTeams,
  createTeam,
  updateTeam,
  deleteTeam,
  getTeamMembers,
  addTeamMember,
  removeTeamMember,
  updateTeamMemberRole,
  getOncall,
  getCurrentOncall,
  addOncallSlot,
  deleteOncallSlot,
  getIncidents,
  getTables,
} from '../api/endpoints'
import { EmptyState, PageHeader } from '../components/app-ui'
import IncidentCard from '../components/IncidentCard'
import UserPicker from '../components/UserPicker'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import HealthBadge from '../components/HealthBadge'

// ── Constants ──────────────────────────────────────────────────────────────

const TEAM_COLORS = [
  { value: '#3b82f6', label: 'Blue' },
  { value: '#10b981', label: 'Green' },
  { value: '#f59e0b', label: 'Amber' },
  { value: '#ef4444', label: 'Red' },
  { value: '#8b5cf6', label: 'Purple' },
  { value: '#06b6d4', label: 'Cyan' },
  { value: '#f43f5e', label: 'Rose' },
]

// ── Helper components ──────────────────────────────────────────────────────

function TeamColorDot({ color, size = 'size-3' }) {
  if (!color) return null
  return (
    <span
      className={cn('inline-block rounded-full shrink-0', size)}
      style={{ background: color }}
    />
  )
}

function TeamRoleBadge({ role }) {
  return (
    <Badge variant={role === 'lead' ? 'default' : 'outline'} className="capitalize">
      {role || 'member'}
    </Badge>
  )
}

function OrgRoleBadge({ role }) {
  const variants = {
    owner: 'default',
    admin: 'secondary',
    member: 'outline',
  }
  return (
    <Badge variant={variants[role] || 'outline'} className="capitalize">
      {role || 'member'}
    </Badge>
  )
}

function getApiError(err, fallback) {
  const detail = err.response?.data?.detail || err.response?.data?.error || err.message
  if (Array.isArray(detail)) return detail.map((item) => item.msg || item.message || String(item)).join(', ')
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail)
  return detail || fallback
}

// ── Team sheet (create / edit) ─────────────────────────────────────────────

function TeamSheet({ open, onOpenChange, team, onSaved }) {
  const isEdit = Boolean(team)
  const [form, setForm] = useState({ name: '', description: '', color: TEAM_COLORS[0].value })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setForm({
        name: team?.name || '',
        description: team?.description || '',
        color: team?.color || TEAM_COLORS[0].value,
      })
    }
  }, [open, team])

  const submit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) return
    setSaving(true)
    try {
      const payload = { name: form.name.trim(), description: form.description.trim() || null, color: form.color }
      const res = isEdit
        ? await updateTeam(team.id, payload)
        : await createTeam(payload)
      onSaved(res.data)
      onOpenChange(false)
      notify.ok(isEdit ? 'Team updated' : 'Team created')
    } catch (err) {
      notify.err(getApiError(err, isEdit ? 'Failed to update team' : 'Failed to create team'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{isEdit ? 'Edit team' : 'New team'}</SheetTitle>
          <SheetDescription>
            {isEdit ? 'Update team details.' : 'Create a team to group members and assign on-call schedules.'}
          </SheetDescription>
        </SheetHeader>
        <form onSubmit={submit} className="flex flex-1 flex-col">
          <div className="flex flex-1 flex-col gap-4 px-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="team-name">Name <span className="text-destructive">*</span></Label>
              <Input
                id="team-name"
                value={form.name}
                onChange={(e) => setForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="e.g. Data Engineering"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="team-description">Description</Label>
              <Textarea
                id="team-description"
                value={form.description}
                onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Optional team description…"
                className="min-h-20 resize-none"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>Color</Label>
              <div className="flex flex-wrap gap-2">
                {TEAM_COLORS.map(c => (
                  <button
                    key={c.value}
                    type="button"
                    title={c.label}
                    onClick={() => setForm(prev => ({ ...prev, color: c.value }))}
                    className={cn(
                      'size-7 rounded-full border-2 transition-all',
                      form.color === c.value
                        ? 'border-foreground scale-110 shadow-md'
                        : 'border-transparent hover:border-muted-foreground'
                    )}
                    style={{ background: c.value }}
                    aria-label={c.label}
                    aria-pressed={form.color === c.value}
                  />
                ))}
              </div>
            </div>
          </div>
          <SheetFooter>
            <Button type="submit" disabled={saving || !form.name.trim()}>
              {saving && <Loader2 data-icon="inline-start" className="animate-spin" />}
              {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create team'}
            </Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}

// ── Members tab ────────────────────────────────────────────────────────────

function MembersTab({ team, userRole }) {
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(true)
  const [addUserId, setAddUserId] = useState('')
  const [addRole, setAddRole] = useState('member')
  const [adding, setAdding] = useState(false)

  const canManage = userRole === 'owner' || userRole === 'admin'

  useEffect(() => {
    if (!team) return
    setLoading(true)
    getTeamMembers(team.id)
      .then(r => setMembers(Array.isArray(r.data) ? r.data : r.data?.members || []))
      .catch(() => notify.err('Failed to load team members'))
      .finally(() => setLoading(false))
  }, [team])

  const handleAdd = async () => {
    if (!addUserId) return
    setAdding(true)
    try {
      const res = await addTeamMember(team.id, { user_id: addUserId, role: addRole })
      setMembers(prev => [...prev, res.data])
      setAddUserId('')
      setAddRole('member')
      notify.ok('Member added')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to add member'))
    } finally {
      setAdding(false)
    }
  }

  const handleRoleChange = async (userId, newRole) => {
    try {
      await updateTeamMemberRole(team.id, userId, { role: newRole })
      setMembers(prev => prev.map(m => m.user_id === userId || m.id === userId ? { ...m, team_role: newRole, role: newRole } : m))
      notify.ok('Role updated')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to update role'))
    }
  }

  const handleRemove = async (userId) => {
    try {
      await removeTeamMember(team.id, userId)
      setMembers(prev => prev.filter(m => m.user_id !== userId && m.id !== userId))
      notify.ok('Member removed')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to remove member'))
    }
  }

  const existingIds = members.map(m => m.user_id || m.id)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {members.length === 0 ? (
        <EmptyState icon={Users} title="No members yet" description="Add org members to this team." />
      ) : (
        <div className="dw-table-wrap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Member</TableHead>
                <TableHead>Org role</TableHead>
                <TableHead>Team role</TableHead>
                {canManage && <TableHead className="w-12" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map(m => {
                const userId = m.user_id || m.id
                const teamRole = m.team_role || m.role || 'member'
                const orgRole = m.org_role || m.user?.role || 'member'
                const displayName = m.full_name || m.user?.full_name || m.email || m.user?.email || userId
                const email = m.email || m.user?.email || ''
                return (
                  <TableRow key={userId}>
                    <TableCell>
                      <div>
                        <p className="text-sm font-medium">{displayName}</p>
                        {email && displayName !== email && (
                          <p className="text-xs text-muted-foreground">{email}</p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell><OrgRoleBadge role={orgRole} /></TableCell>
                    <TableCell>
                      {canManage ? (
                        <Select value={teamRole} onValueChange={(v) => handleRoleChange(userId, v)}>
                          <SelectTrigger className="h-7 w-28 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="lead">Lead</SelectItem>
                            <SelectItem value="member">Member</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <TeamRoleBadge role={teamRole} />
                      )}
                    </TableCell>
                    {canManage && (
                      <TableCell>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove member">
                              <UserX className="size-4 text-destructive" />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Remove member?</AlertDialogTitle>
                              <AlertDialogDescription>
                                {displayName} will be removed from this team. They will keep their org access.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleRemove(userId)}>Remove</AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </TableCell>
                    )}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {canManage && (
        <div className="rounded-lg border bg-muted/30 p-4">
          <p className="mb-3 text-sm font-medium">Add member</p>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <UserPicker
                value={addUserId}
                onChange={setAddUserId}
                placeholder="Select org member…"
                excludeIds={existingIds}
              />
            </div>
            <div className="w-32">
              <Select value={addRole} onValueChange={setAddRole}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="lead">Lead</SelectItem>
                  <SelectItem value="member">Member</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button type="button" onClick={handleAdd} disabled={!addUserId || adding}>
              {adding ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <UserPlus data-icon="inline-start" />}
              {adding ? 'Adding…' : 'Add'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── On-call tab ────────────────────────────────────────────────────────────

function OncallTab({ team }) {
  const [slots, setSlots] = useState([])
  const [current, setCurrent] = useState(null)
  const [loading, setLoading] = useState(true)
  const [members, setMembers] = useState([])
  const [form, setForm] = useState({ user_id: '', starts_at: '', ends_at: '' })
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    if (!team) return
    setLoading(true)
    Promise.all([
      getOncall(team.id).catch(() => ({ data: [] })),
      getCurrentOncall(team.id).catch(() => ({ data: null })),
      getTeamMembers(team.id).catch(() => ({ data: [] })),
    ]).then(([slotsRes, currentRes, membersRes]) => {
      setSlots(Array.isArray(slotsRes.data) ? slotsRes.data : [])
      setCurrent(currentRes.data)
      setMembers(Array.isArray(membersRes.data) ? membersRes.data : membersRes.data?.members || [])
    }).finally(() => setLoading(false))
  }, [team])

  const handleAdd = async () => {
    if (!form.user_id || !form.starts_at || !form.ends_at) return
    setAdding(true)
    try {
      const res = await addOncallSlot(team.id, {
        user_id: form.user_id,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
      })
      setSlots(prev => [...prev, res.data])
      setForm({ user_id: '', starts_at: '', ends_at: '' })
      notify.ok('On-call slot added')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to add on-call slot'))
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (slotId) => {
    try {
      await deleteOncallSlot(team.id, slotId)
      setSlots(prev => prev.filter(s => s.id !== slotId))
      notify.ok('Slot removed')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to remove slot'))
    }
  }

  const memberIds = members.map(m => m.user_id || m.id)

  const formatDt = (iso) => {
    if (!iso) return '—'
    try {
      return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    } catch {
      return iso
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const currentName = current?.user_name || current?.full_name || current?.user?.full_name || current?.user_email || current?.email || current?.user?.email

  return (
    <div className="flex flex-col gap-4">
      {/* Current on-call banner */}
      <div className={cn(
        'flex items-center gap-2 rounded-lg border px-4 py-3 text-sm',
        current ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-muted bg-muted/30'
      )}>
        <Shield className={cn('size-4 shrink-0', current ? 'text-emerald-600' : 'text-muted-foreground')} />
        {current ? (
          <span>Currently on-call: <span className="font-semibold text-emerald-700 dark:text-emerald-400">{currentName}</span></span>
        ) : (
          <span className="text-muted-foreground">No one is currently on-call</span>
        )}
      </div>

      {/* Slots table */}
      {slots.length === 0 ? (
        <EmptyState icon={Clock} title="No on-call slots" description="Schedule on-call coverage for team members." />
      ) : (
        <div className="dw-table-wrap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Member</TableHead>
                <TableHead>Starts</TableHead>
                <TableHead>Ends</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {slots.map(slot => {
                const name = slot.user_name || slot.full_name || slot.user?.full_name || slot.user_email || slot.email || slot.user?.email || slot.user_id
                return (
                  <TableRow key={slot.id}>
                    <TableCell className="font-medium">{name}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDt(slot.starts_at)}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDt(slot.ends_at)}</TableCell>
                    <TableCell>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove slot">
                            <Trash2 className="size-4 text-destructive" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Remove on-call slot?</AlertDialogTitle>
                            <AlertDialogDescription>
                              This will remove {name}'s on-call slot from {formatDt(slot.starts_at)} to {formatDt(slot.ends_at)}.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => handleDelete(slot.id)}>Remove</AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Add slot form */}
      <div className="rounded-lg border bg-muted/30 p-4">
        <p className="mb-3 text-sm font-medium">Add on-call slot</p>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Label className="text-xs text-muted-foreground mb-1">Team member</Label>
              <UserPicker
                value={form.user_id}
                onChange={(v) => setForm(prev => ({ ...prev, user_id: v }))}
                placeholder="Select team member…"
                excludeIds={[]}
              />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Start</Label>
              <Input
                type="datetime-local"
                value={form.starts_at}
                onChange={(e) => setForm(prev => ({ ...prev, starts_at: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">End</Label>
              <Input
                type="datetime-local"
                value={form.ends_at}
                onChange={(e) => setForm(prev => ({ ...prev, ends_at: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <Button
              type="button"
              onClick={handleAdd}
              disabled={!form.user_id || !form.starts_at || !form.ends_at || adding}
            >
              {adding ? <Loader2 data-icon="inline-start" className="animate-spin" /> : <Plus data-icon="inline-start" />}
              {adding ? 'Adding…' : 'Add slot'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Incidents tab ──────────────────────────────────────────────────────────

function IncidentsTab({ team }) {
  const [incidents, setIncidents] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!team) return
    setLoading(true)
    getIncidents({ assigned_team_id: team.id, status: 'open' })
      .then(r => setIncidents(Array.isArray(r.data) ? r.data : r.data?.items || []))
      .catch(() => setIncidents([]))
      .finally(() => setLoading(false))
  }, [team])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (incidents.length === 0) {
    return <EmptyState icon={AlertTriangle} title="No open incidents" description="This team has no open incidents." />
  }

  return (
    <div className="rounded-lg border overflow-hidden">
      {incidents.map(incident => (
        <IncidentCard key={incident.id} incident={incident} />
      ))}
    </div>
  )
}

// ── Tables tab ─────────────────────────────────────────────────────────────

function TablesTab({ team }) {
  const [tables, setTables] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!team) return
    setLoading(true)
    getTables({ owner_team_id: team.id })
      .then(r => setTables(Array.isArray(r.data) ? r.data : r.data?.items || []))
      .catch(() => setTables([]))
      .finally(() => setLoading(false))
  }, [team])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (tables.length === 0) {
    return <EmptyState icon={Table2} title="No tables assigned" description="No monitored tables are assigned to this team." />
  }

  return (
    <div className="dw-table-wrap">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Table</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tables.map(t => (
            <TableRow key={t.id}>
              <TableCell className="font-mono text-xs font-medium">{t.schema_name}.{t.table_name}</TableCell>
              <TableCell><HealthBadge status={t.is_active ? 'healthy' : 'paused'} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

// ── Team detail ────────────────────────────────────────────────────────────

function TeamDetail({ team, userRole }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="mb-4 flex items-center gap-2">
          <TeamColorDot color={team.color} size="size-4" />
          <h2 className="text-base font-semibold">{team.name}</h2>
          {team.description && (
            <span className="text-sm text-muted-foreground">— {team.description}</span>
          )}
        </div>
        <Tabs defaultValue="members">
          <TabsList>
            <TabsTrigger value="members">Members</TabsTrigger>
            <TabsTrigger value="oncall">On-call</TabsTrigger>
            <TabsTrigger value="incidents">Incidents</TabsTrigger>
            <TabsTrigger value="tables">Tables</TabsTrigger>
          </TabsList>
          <TabsContent value="members" className="mt-4">
            <MembersTab team={team} userRole={userRole} />
          </TabsContent>
          <TabsContent value="oncall" className="mt-4">
            <OncallTab team={team} />
          </TabsContent>
          <TabsContent value="incidents" className="mt-4">
            <IncidentsTab team={team} />
          </TabsContent>
          <TabsContent value="tables" className="mt-4">
            <TablesTab team={team} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function Teams() {
  const [teams, setTeams] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedTeam, setSelectedTeam] = useState(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [editTeam, setEditTeam] = useState(null)

  // Derive user role from storage (consistent with Settings.jsx pattern)
  const userRole = (() => {
    try { return localStorage.getItem('dw_user_role') || 'member' } catch { return 'member' }
  })()

  const canManage = userRole === 'owner' || userRole === 'admin'

  useEffect(() => {
    setLoading(true)
    getTeams()
      .then(r => setTeams(Array.isArray(r.data) ? r.data : r.data?.teams || []))
      .catch(() => notify.err('Failed to load teams'))
      .finally(() => setLoading(false))
  }, [])

  const handleSaved = (saved) => {
    setTeams(prev => {
      const idx = prev.findIndex(t => t.id === saved.id)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = saved
        if (selectedTeam?.id === saved.id) setSelectedTeam(saved)
        return next
      }
      return [...prev, saved]
    })
  }

  const handleDelete = async (id) => {
    try {
      await deleteTeam(id)
      setTeams(prev => prev.filter(t => t.id !== id))
      if (selectedTeam?.id === id) setSelectedTeam(null)
      notify.ok('Team deleted')
    } catch (err) {
      notify.err(getApiError(err, 'Failed to delete team'))
    }
  }

  const openCreate = () => {
    setEditTeam(null)
    setSheetOpen(true)
  }

  const openEdit = (team) => {
    setEditTeam(team)
    setSheetOpen(true)
  }

  return (
    <div className="dw-page">
      <PageHeader
        title="Teams"
        description="Manage teams, members, and on-call schedules."
        actions={
          canManage && (
            <Button type="button" onClick={openCreate}>
              <Plus data-icon="inline-start" />
              New team
            </Button>
          )
        }
      />

      {/* Teams list */}
      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : teams.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No teams yet"
              description="Create a team to group org members and schedule on-call rotations."
              action={canManage && (
                <Button type="button" onClick={openCreate}>
                  <Plus data-icon="inline-start" />
                  New team
                </Button>
              )}
            />
          ) : (
            <div className="dw-table-wrap">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Team</TableHead>
                    <TableHead>Members</TableHead>
                    <TableHead>On-call</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {teams.map(team => (
                    <TableRow
                      key={team.id}
                      className={cn('cursor-pointer', selectedTeam?.id === team.id && 'bg-muted/50')}
                      onClick={() => setSelectedTeam(prev => prev?.id === team.id ? null : team)}
                    >
                      <TableCell>
                        <span className="flex items-center gap-2">
                          <TeamColorDot color={team.color} />
                          <span className="font-medium">{team.name}</span>
                          {team.description && (
                            <span className="hidden text-xs text-muted-foreground sm:inline truncate max-w-[200px]">{team.description}</span>
                          )}
                        </span>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {team.member_count ?? '—'}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {team.current_oncall?.user_name || team.current_oncall?.full_name || team.current_oncall?.user_email || team.current_oncall?.email || '—'}
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Actions for ${team.name}`}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MoreHorizontal />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuGroup>
                              {canManage && (
                                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); openEdit(team) }}>
                                  <Pencil data-icon="inline-start" />
                                  Edit
                                </DropdownMenuItem>
                              )}
                              {canManage && (
                                <AlertDialog>
                                  <AlertDialogTrigger asChild>
                                    <DropdownMenuItem
                                      onSelect={(e) => e.preventDefault()}
                                      onClick={(e) => e.stopPropagation()}
                                      variant="destructive"
                                    >
                                      <Trash2 data-icon="inline-start" />
                                      Delete
                                    </DropdownMenuItem>
                                  </AlertDialogTrigger>
                                  <AlertDialogContent>
                                    <AlertDialogHeader>
                                      <AlertDialogTitle>Delete team?</AlertDialogTitle>
                                      <AlertDialogDescription>
                                        "{team.name}" will be permanently deleted. This cannot be undone.
                                      </AlertDialogDescription>
                                    </AlertDialogHeader>
                                    <AlertDialogFooter>
                                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                                      <AlertDialogAction onClick={() => handleDelete(team.id)}>Delete</AlertDialogAction>
                                    </AlertDialogFooter>
                                  </AlertDialogContent>
                                </AlertDialog>
                              )}
                            </DropdownMenuGroup>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Team detail panel */}
      {selectedTeam && (
        <TeamDetail key={selectedTeam.id} team={selectedTeam} userRole={userRole} />
      )}

      {/* Create / Edit sheet */}
      <TeamSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        team={editTeam}
        onSaved={handleSaved}
      />
    </div>
  )
}
