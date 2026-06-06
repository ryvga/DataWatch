import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Building2, ChevronLeft, ChevronRight, ExternalLink, Loader2, MoreHorizontal, Search, ShieldOff, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { adminDeleteOrg, adminGetOrgs, adminSuspendOrg, adminUnsuspendOrg, adminUpdatePlan } from '../../api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  BooleanBadge,
  PAGE_SIZE,
  PLANS,
  PlanBadge,
  StatusBadge,
  SUBSCRIPTION_STATUSES,
  clientFilterOrgs,
  compactNumber,
  estimateMrr,
  formatDate,
  formatMoney,
  getOrgMembersCount,
  getOrgSourcesCount,
  getOrgTablesCount,
  unwrapList,
} from './adminUtils.jsx'

function StatCell({ label, value, detail }) {
  return (
    <Card>
      <CardHeader className="px-4 pb-1 pt-4">
        <CardTitle className="text-xs font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
      </CardContent>
    </Card>
  )
}

function PlanModal({ org, open, onOpenChange, onSaved }) {
  const [plan, setPlan] = useState('free')
  const [status, setStatus] = useState('trialing')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (org) {
      setPlan(org.plan || 'free')
      setStatus(org.subscription_status || 'trialing')
    }
  }, [org])

  const save = async () => {
    if (!org) return
    setSaving(true)
    try {
      await adminUpdatePlan(org.id, { plan, subscription_status: status })
      toast.success('Plan updated')
      onOpenChange(false)
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update plan')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change plan</DialogTitle>
          <DialogDescription>{org?.name} will use the selected plan and billing status immediately.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label>Plan</Label>
            <Select value={plan} onValueChange={setPlan}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{PLANS.map((item) => <SelectItem key={item} value={item} className="capitalize">{item}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label>Status</Label>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{SUBSCRIPTION_STATUSES.map((item) => <SelectItem key={item} value={item} className="capitalize">{item.replaceAll('_', ' ')}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function AdminOrgs() {
  const [searchParams] = useSearchParams()
  const [orgs, setOrgs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({
    search: searchParams.get('slug') || searchParams.get('search') || '',
    plan: 'all',
    status: 'all',
  })
  const [planOrg, setPlanOrg] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const response = await adminGetOrgs({
        search: filters.search || undefined,
        plan: filters.plan === 'all' ? undefined : filters.plan,
        subscription_status: filters.status === 'all' ? undefined : filters.status,
        page,
        per_page: PAGE_SIZE,
      })
      const parsed = unwrapList(response.data)
      setOrgs(parsed.items)
      setTotal(parsed.total)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load organizations')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filters.search, filters.plan, filters.status, page])

  const filtered = useMemo(() => clientFilterOrgs(orgs, filters), [orgs, filters])
  const planCounts = useMemo(() => {
    return PLANS.reduce((acc, plan) => ({ ...acc, [plan]: orgs.filter((org) => org.plan === plan).length }), {})
  }, [orgs])
  const statusCounts = useMemo(() => {
    return orgs.reduce((acc, org) => ({ ...acc, [org.subscription_status]: (acc[org.subscription_status] || 0) + 1 }), {})
  }, [orgs])
  const visibleTotal = total || filtered.length
  const pageCount = Math.max(1, Math.ceil(visibleTotal / PAGE_SIZE))
  const serverPaginated = total > orgs.length
  const visible = serverPaginated ? filtered.slice(0, PAGE_SIZE) : filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const setFilter = (key, value) => {
    setPage(1)
    setFilters((current) => ({ ...current, [key]: value }))
  }

  const suspend = async (org) => {
    setSavingId(org.id)
    try {
      if (org.subscription_status === 'suspended') {
        await adminUnsuspendOrg(org.id)
        toast.success('Organization unsuspended')
      } else {
        await adminSuspendOrg(org.id)
        toast.success('Organization suspended')
      }
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update organization status')
    } finally {
      setSavingId(null)
    }
  }

  const remove = async (org) => {
    if (!confirm(`Delete ${org.name}? This performs the backend soft delete/suspend action.`)) return
    setSavingId(org.id)
    try {
      await adminDeleteOrg(org.id)
      toast.success('Organization deleted')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete organization')
    } finally {
      setSavingId(null)
    }
  }

  if (loading && orgs.length === 0) {
    return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Organizations</h1>
          <p className="text-sm text-muted-foreground">Manage workspaces, billing state, limits, and high-risk account actions.</p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          {loading && <Loader2 className="size-4 animate-spin" />}
          Refresh
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCell label="Total orgs" value={compactNumber(total || orgs.length)} detail={`${compactNumber(filtered.length)} matching current filters`} />
        <StatCell label="Estimated MRR" value={formatMoney(estimateMrr(orgs))} detail="Active and trialing plans" />
        <StatCell label="Plan mix" value={`${planCounts.free || 0} / ${planCounts.starter || 0} / ${planCounts.growth || 0} / ${planCounts.agency || 0}`} detail="free / starter / growth / agency" />
        <StatCell label="Subscription status" value={Object.values(statusCounts).reduce((sum, count) => sum + count, 0)} detail={Object.entries(statusCounts).map(([key, count]) => `${key}: ${count}`).join(' · ') || 'No subscriptions'} />
      </div>

      <Card>
        <CardContent className="grid gap-3 p-4 lg:grid-cols-[minmax(260px,1fr)_180px_220px_auto]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" placeholder="Search name or slug" value={filters.search} onChange={(event) => setFilter('search', event.target.value)} />
          </div>
          <Select value={filters.plan} onValueChange={(value) => setFilter('plan', value)}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Plan" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All plans</SelectItem>
              {PLANS.map((item) => <SelectItem key={item} value={item} className="capitalize">{item}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filters.status} onValueChange={(value) => setFilter('status', value)}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {SUBSCRIPTION_STATUSES.map((item) => <SelectItem key={item} value={item} className="capitalize">{item.replaceAll('_', ' ')}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={() => { setPage(1); setFilters({ search: '', plan: 'all', status: 'all' }) }}>Clear</Button>
        </CardContent>
      </Card>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-64">Name</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Members</TableHead>
                <TableHead className="text-right">Tables</TableHead>
                <TableHead className="text-right">Sources</TableHead>
                <TableHead>LLM key</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((org) => (
                <TableRow key={org.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Building2 className="size-4 text-muted-foreground" />
                      <div>
                        <div className="font-medium">{org.name}</div>
                        <div className="font-mono text-xs text-muted-foreground">{org.slug}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell><PlanBadge plan={org.plan} /></TableCell>
                  <TableCell><StatusBadge status={org.subscription_status} /></TableCell>
                  <TableCell className="text-right font-mono text-sm">{getOrgMembersCount(org)}</TableCell>
                  <TableCell className="text-right font-mono text-sm">{getOrgTablesCount(org)}</TableCell>
                  <TableCell className="text-right font-mono text-sm">{getOrgSourcesCount(org)}</TableCell>
                  <TableCell><BooleanBadge value={org.has_llm_key} trueLabel="Set" falseLabel="No" /></TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDate(org.created_at)}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" disabled={savingId === org.id}>
                          {savingId === org.id ? <Loader2 className="size-4 animate-spin" /> : <MoreHorizontal className="size-4" />}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem asChild>
                          <Link to={`/orgs/${org.id}`}><ExternalLink className="size-4" />View details</Link>
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setPlanOrg(org)}>Change plan</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => suspend(org)}>
                          <ShieldOff className="size-4" />{org.subscription_status === 'suspended' ? 'Unsuspend' : 'Suspend'}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem variant="destructive" onSelect={() => remove(org)}>
                          <Trash2 className="size-4" />Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
              {visible.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="py-10 text-center text-sm text-muted-foreground">No organizations match these filters.</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>Page {page} of {pageCount} · 50 per page</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1}>
            <ChevronLeft className="size-4" />Previous
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={page >= pageCount}>
            Next<ChevronRight className="size-4" />
          </Button>
        </div>
      </div>

      <PlanModal org={planOrg} open={!!planOrg} onOpenChange={(open) => !open && setPlanOrg(null)} onSaved={load} />
    </div>
  )
}
