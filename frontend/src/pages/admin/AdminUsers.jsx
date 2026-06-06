import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, Loader2, MoreHorizontal, Search, UserCheck, UserX } from 'lucide-react'
import { toast } from 'sonner'
import { adminChangeUserRole, adminDeactivateUser, adminGetAllUsers, adminGetOrgs, adminReactivateUser } from '../../api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge, USER_ROLES, clientFilterUsers, formatDate, getUserActive, unwrapList } from './adminUtils.jsx'

function RoleDialog({ user, open, onOpenChange, onSaved }) {
  const [role, setRole] = useState('member')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (user) setRole(user.role || 'member')
  }, [user])

  const save = async () => {
    if (!user) return
    setSaving(true)
    try {
      await adminChangeUserRole(user.id, { role })
      toast.success('Role updated')
      onOpenChange(false)
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update role')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change user role</DialogTitle>
          <DialogDescription>{user?.email} will receive the selected organization role.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label>Role</Label>
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>{USER_ROLES.map((item) => <SelectItem key={item} value={item} className="capitalize">{item}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            Save role
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [orgs, setOrgs] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [roleUser, setRoleUser] = useState(null)
  const [filters, setFilters] = useState({ search: '', org: 'all', role: 'all', active: 'all' })

  const load = async () => {
    setLoading(true)
    const [usersResult, orgsResult] = await Promise.allSettled([
      adminGetAllUsers({
        search: filters.search || undefined,
        org: filters.org === 'all' ? undefined : filters.org,
        role: filters.role === 'all' ? undefined : filters.role,
        active: filters.active === 'all' ? undefined : filters.active === 'active',
      }),
      adminGetOrgs(),
    ])

    if (usersResult.status === 'fulfilled') {
      setUsers(unwrapList(usersResult.value.data).items)
    } else {
      toast.error(usersResult.reason?.response?.data?.detail || 'Failed to load users')
    }

    if (orgsResult.status === 'fulfilled') setOrgs(unwrapList(orgsResult.value.data).items)
    setLoading(false)
  }

  useEffect(() => { load() }, [filters.search, filters.org, filters.role, filters.active])

  const filtered = useMemo(() => clientFilterUsers(users, filters), [users, filters])
  const orgBySlug = useMemo(() => new Map(orgs.map((org) => [org.slug, org])), [orgs])
  const activeCount = users.filter(getUserActive).length

  const setFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value }))

  const toggleUser = async (user) => {
    setSavingId(user.id)
    try {
      if (getUserActive(user)) {
        await adminDeactivateUser(user.id)
        toast.success('User deactivated')
      } else {
        await adminReactivateUser(user.id)
        toast.success('User reactivated')
      }
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update user status')
    } finally {
      setSavingId(null)
    }
  }

  if (loading && users.length === 0) {
    return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground">{users.length} users · {activeCount} active · {filtered.length} matching filters</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          {loading && <Loader2 className="size-4 animate-spin" />}
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="grid gap-3 p-4 xl:grid-cols-[minmax(260px,1fr)_220px_160px_170px_auto]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" placeholder="Search email or name" value={filters.search} onChange={(event) => setFilter('search', event.target.value)} />
          </div>
          <Select value={filters.org} onValueChange={(value) => setFilter('org', value)}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All organizations</SelectItem>
              {orgs.map((org) => <SelectItem key={org.id} value={org.slug}>{org.slug}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filters.role} onValueChange={(value) => setFilter('role', value)}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All roles</SelectItem>
              {USER_ROLES.map((role) => <SelectItem key={role} value={role} className="capitalize">{role}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filters.active} onValueChange={(value) => setFilter('active', value)}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="inactive">Inactive</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={() => setFilters({ search: '', org: 'all', role: 'all', active: 'all' })}>Clear</Button>
        </CardContent>
      </Card>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Full name</TableHead>
                <TableHead>Org</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Last login</TableHead>
                <TableHead>Joined</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((user) => {
                const active = getUserActive(user)
                const org = orgBySlug.get(user.org_slug)
                return (
                  <TableRow key={user.id}>
                    <TableCell className="font-mono text-sm">{user.email}</TableCell>
                    <TableCell>{user.full_name || '-'}</TableCell>
                    <TableCell>
                      <span className="rounded-md border bg-muted/50 px-2 py-1 font-mono text-xs">{user.org_slug || '-'}</span>
                    </TableCell>
                    <TableCell><Badge variant="outline" className="capitalize">{user.role}</Badge></TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDate(user.last_login_at)}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDate(user.joined_at || user.created_at)}</TableCell>
                    <TableCell><StatusBadge status={active ? 'active' : 'inactive'} /></TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm" disabled={savingId === user.id}>
                            {savingId === user.id ? <Loader2 className="size-4 animate-spin" /> : <MoreHorizontal className="size-4" />}
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onSelect={() => toggleUser(user)}>
                            {active ? <UserX className="size-4" /> : <UserCheck className="size-4" />}
                            {active ? 'Deactivate user' : 'Reactivate user'}
                          </DropdownMenuItem>
                          <DropdownMenuItem onSelect={() => setRoleUser(user)}>Change role</DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem asChild disabled={!org}>
                            <Link to={org ? `/orgs/${org.id}` : '/orgs'}>
                              <ExternalLink className="size-4" />View org
                            </Link>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                )
              })}
              {filtered.length === 0 && (
                <TableRow><TableCell colSpan={8} className="py-10 text-center text-sm text-muted-foreground">No users match these filters.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>

      <RoleDialog user={roleUser} open={!!roleUser} onOpenChange={(open) => !open && setRoleUser(null)} onSaved={load} />
    </div>
  )
}
