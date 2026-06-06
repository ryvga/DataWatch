import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Database, Key, Loader2, Save, ShieldCheck, Trash2, UserCheck, UserX, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import {
  adminCancelOrgSubscription,
  adminChangeUserRole,
  adminCreateApiKey,
  adminDeactivateOrgUser,
  adminDeleteOrg,
  adminGetOrg,
  adminGetOrgSources,
  adminGetOrgUsage,
  adminGetOrgUsers,
  adminReactivateOrgUser,
  adminRemoveLLMKey,
  adminSetLLMKey,
  adminUpdatePlan,
} from '../../api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  BooleanBadge,
  PLANS,
  PlanBadge,
  StatusBadge,
  SUBSCRIPTION_STATUSES,
  USER_ROLES,
  formatDate,
  formatDateTime,
  getOrgMembersCount,
  getOrgSourcesCount,
  getOrgTablesCount,
  getUserActive,
  planDetails,
  unwrapList,
} from './adminUtils.jsx'

function InfoRow({ label, value, mono = false }) {
  return (
    <div className="grid gap-1 border-b py-3 last:border-b-0 sm:grid-cols-[180px_1fr]">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className={mono ? 'break-all font-mono text-sm' : 'text-sm'}>{value || '-'}</dd>
    </div>
  )
}

function UsageTile({ label, value, detail }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value ?? 0}</div>
      {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
    </div>
  )
}

export default function AdminOrgDetail() {
  const { id } = useParams()
  const [org, setOrg] = useState(null)
  const [users, setUsers] = useState([])
  const [usage, setUsage] = useState({})
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [plan, setPlan] = useState('free')
  const [subscriptionStatus, setSubscriptionStatus] = useState('trialing')
  const [llmKey, setLlmKey] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [newApiKeyResult, setNewApiKeyResult] = useState(null)

  const load = async () => {
    setLoading(true)
    const [orgResult, usersResult, usageResult, sourcesResult] = await Promise.allSettled([
      adminGetOrg(id),
      adminGetOrgUsers(id),
      adminGetOrgUsage(id, { window_days: 30 }),
      adminGetOrgSources(id),
    ])

    if (orgResult.status === 'fulfilled') {
      const nextOrg = orgResult.value.data
      setOrg(nextOrg)
      setPlan(nextOrg.plan || 'free')
      setSubscriptionStatus(nextOrg.subscription_status || 'trialing')
      setLlmModel(nextOrg.llm_model || '')
    } else {
      toast.error(orgResult.reason?.response?.data?.detail || 'Failed to load organization')
    }

    if (usersResult.status === 'fulfilled') setUsers(unwrapList(usersResult.value.data))
    if (usageResult.status === 'fulfilled') setUsage(usageResult.value.data || {})
    if (sourcesResult.status === 'fulfilled') setSources(unwrapList(sourcesResult.value.data))
    setLoading(false)
  }

  useEffect(() => { load() }, [id])

  const usageCounts = useMemo(() => ({
    sources: usage.sources_count ?? usage.source_count ?? getOrgSourcesCount(org),
    tables: usage.tables_count ?? usage.table_count ?? getOrgTablesCount(org),
    profiles30d: usage.profiles_last_30d ?? usage.profiles_30d ?? 0,
    incidents30d: usage.incidents_last_30d ?? usage.incidents_30d ?? 0,
    checks30d: usage.check_results_last_30d ?? usage.check_results_30d ?? 0,
  }), [usage, org])

  const savePlan = async () => {
    setSaving(true)
    try {
      await adminUpdatePlan(id, { plan, subscription_status: subscriptionStatus })
      toast.success('Subscription details updated')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update subscription')
    } finally {
      setSaving(false)
    }
  }

  const saveLLM = async () => {
    if (!llmKey) return
    setSaving(true)
    try {
      await adminSetLLMKey(id, { api_key: llmKey, model: llmModel || undefined })
      setLlmKey('')
      toast.success('LLM key saved')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save LLM key')
    } finally {
      setSaving(false)
    }
  }

  const removeLLM = async () => {
    if (!confirm('Remove this organization LLM key?')) return
    setSaving(true)
    try {
      await adminRemoveLLMKey(id)
      toast.success('LLM key removed')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to remove LLM key')
    } finally {
      setSaving(false)
    }
  }

  const createApiKey = async () => {
    setSaving(true)
    try {
      const res = await adminCreateApiKey(id, { name: 'default' })
      setNewApiKeyResult(res.data.api_key)
      toast.success('API key created')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create API key')
    } finally {
      setSaving(false)
    }
  }

  const changeRole = async (user, role) => {
    setSaving(true)
    try {
      await adminChangeUserRole(user.id, { role })
      toast.success(`${user.email} changed to ${role}`)
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to change role')
    } finally {
      setSaving(false)
    }
  }

  const toggleUser = async (user) => {
    setSaving(true)
    try {
      if (getUserActive(user)) {
        await adminDeactivateOrgUser(id, user.id)
        toast.success('Member deactivated')
      } else {
        await adminReactivateOrgUser(id, user.id)
        toast.success('Member reactivated')
      }
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update member')
    } finally {
      setSaving(false)
    }
  }

  const cancelSubscription = async () => {
    if (!confirm('Cancel this organization subscription?')) return
    setSaving(true)
    try {
      await adminCancelOrgSubscription(id, { reason: 'Staff admin cancellation' })
      toast.success('Subscription canceled')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to cancel subscription')
    } finally {
      setSaving(false)
    }
  }

  const deleteOrg = async () => {
    if (!confirm(`Delete ${org?.name}? This performs the backend soft delete/suspend action.`)) return
    setSaving(true)
    try {
      await adminDeleteOrg(id)
      toast.success('Organization deleted')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete organization')
    } finally {
      setSaving(false)
    }
  }

  if (loading && !org) return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
  if (!org) return <div className="py-20 text-center text-muted-foreground">Organization not found.</div>

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="icon" asChild><Link to="/orgs"><ArrowLeft className="size-4" /></Link></Button>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{org.name}</h1>
              <PlanBadge plan={org.plan} />
              <StatusBadge status={org.subscription_status} />
            </div>
            <p className="font-mono text-sm text-muted-foreground">{org.slug}</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          {loading && <Loader2 className="size-4 animate-spin" />}
          Refresh
        </Button>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Organization info</CardTitle>
            <CardDescription>Canonical workspace and billing identifiers.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl>
              <InfoRow label="Name" value={org.name} />
              <InfoRow label="Slug" value={org.slug} mono />
              <InfoRow label="Plan" value={<PlanBadge plan={org.plan} />} />
              <InfoRow label="Billing status" value={<StatusBadge status={org.subscription_status} />} />
              <InfoRow label="PayPal subscription ID" value={org.paypal_subscription_id} mono />
              <InfoRow label="Stripe customer ID" value={org.stripe_customer_id} mono />
              <InfoRow label="Created" value={formatDateTime(org.created_at)} />
              <InfoRow label="Members" value={getOrgMembersCount(org)} />
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Subscription</CardTitle>
            <CardDescription>{planDetails(org.plan)}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
              <div className="grid gap-1.5">
                <Label>Plan</Label>
                <Select value={plan} onValueChange={setPlan}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>{PLANS.map((item) => <SelectItem key={item} value={item} className="capitalize">{item}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label>Status</Label>
                <Select value={subscriptionStatus} onValueChange={setSubscriptionStatus}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>{SUBSCRIPTION_STATUSES.map((item) => <SelectItem key={item} value={item} className="capitalize">{item.replaceAll('_', ' ')}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={savePlan} disabled={saving}>
                {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                Save subscription
              </Button>
              <Button variant="outline" onClick={cancelSubscription} disabled={saving}>
                <XCircle className="size-4" />
                Cancel subscription
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        <UsageTile label="Sources" value={usageCounts.sources} />
        <UsageTile label="Tables" value={usageCounts.tables} />
        <UsageTile label="Profiles" value={usageCounts.profiles30d} detail="Last 30 days" />
        <UsageTile label="Incidents" value={usageCounts.incidents30d} detail="Last 30 days" />
        <UsageTile label="Check results" value={usageCounts.checks30d} detail="Last 30 days" />
      </div>

      <Card className="overflow-hidden p-0">
        <CardHeader>
          <CardTitle className="text-base">Members ({users.length})</CardTitle>
          <CardDescription>Email, role, login recency, and account actions.</CardDescription>
        </CardHeader>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last login</TableHead>
                <TableHead>Joined</TableHead>
                <TableHead className="w-56">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => {
                const active = getUserActive(user)
                const nextRole = user.role === 'member' || user.role === 'viewer' ? 'admin' : user.role === 'admin' ? 'owner' : null
                return (
                  <TableRow key={user.id}>
                    <TableCell className="font-mono text-sm">{user.email}</TableCell>
                    <TableCell>{user.full_name || '-'}</TableCell>
                    <TableCell><Badge variant="outline" className="capitalize">{user.role}</Badge></TableCell>
                    <TableCell><StatusBadge status={active ? 'active' : 'inactive'} /></TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDate(user.last_login_at)}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDate(user.joined_at || user.created_at)}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="outline" size="sm" onClick={() => toggleUser(user)} disabled={saving}>
                          {active ? <UserX className="size-4" /> : <UserCheck className="size-4" />}
                          {active ? 'Deactivate' : 'Reactivate'}
                        </Button>
                        {nextRole && (
                          <Button variant="ghost" size="sm" onClick={() => changeRole(user, nextRole)} disabled={saving}>
                            <ShieldCheck className="size-4" />
                            Promote
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
              {users.length === 0 && (
                <TableRow><TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">No members returned for this organization.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>

      <Card className="overflow-hidden p-0">
        <CardHeader>
          <CardTitle className="text-base">Data sources</CardTitle>
          <CardDescription>Connection inventory and source health state.</CardDescription>
        </CardHeader>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Tables</TableHead>
                <TableHead>Last connected</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((source) => (
                <TableRow key={source.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Database className="size-4 text-muted-foreground" />
                      <span className="font-medium">{source.name || source.id}</span>
                    </div>
                  </TableCell>
                  <TableCell><Badge variant="outline" className="uppercase">{source.type || source.connector_type || '-'}</Badge></TableCell>
                  <TableCell><StatusBadge status={source.status || 'unknown'} /></TableCell>
                  <TableCell className="text-right font-mono text-sm">{source.tables_count ?? source.table_count ?? '-'}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTime(source.last_connected_at)}</TableCell>
                </TableRow>
              ))}
              {sources.length === 0 && (
                <TableRow><TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">No data sources returned for this organization.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">LLM key</CardTitle>
            <CardDescription>Per-org narration credentials override the global OpenRouter fallback.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="flex items-center gap-2 rounded-md border bg-muted/40 p-3">
              <Key className="size-4 text-muted-foreground" />
              <BooleanBadge value={org.has_llm_key} trueLabel="Key configured" falseLabel="Using global fallback" />
              {org.llm_model && <Badge variant="outline" className="ml-auto">{org.llm_model}</Badge>}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label>New API key</Label>
                <Input type="password" value={llmKey} onChange={(event) => setLlmKey(event.target.value)} placeholder="sk-or-v1-..." autoComplete="off" />
              </div>
              <div className="grid gap-1.5">
                <Label>Model override</Label>
                <Input value={llmModel} onChange={(event) => setLlmModel(event.target.value)} placeholder="openrouter/model-id" />
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={saveLLM} disabled={!llmKey || saving}>Save key</Button>
              {org.has_llm_key && <Button variant="outline" size="sm" onClick={removeLLM} disabled={saving}><Trash2 className="size-4" />Remove key</Button>}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Programmatic API key</CardTitle>
            <CardDescription>Generate a one-time visible key for backend integrations.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            {newApiKeyResult && (
              <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3">
                <div className="mb-1 text-xs font-medium text-emerald-700 dark:text-emerald-300">Copy now. It will not be shown again.</div>
                <code className="block break-all font-mono text-sm">{newApiKeyResult}</code>
              </div>
            )}
            <Button variant="outline" size="sm" onClick={createApiKey} disabled={saving} className="w-fit">
              <Key className="size-4" />
              Generate API key
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-base text-destructive">Danger zone</CardTitle>
          <CardDescription>Delete performs the backend soft delete or suspension operation for this workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          <Separator className="mb-4" />
          <Button variant="destructive" onClick={deleteOrg} disabled={saving}>
            <Trash2 className="size-4" />
            Delete organization
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
