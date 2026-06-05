import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Key, Loader2, Save, Trash2 } from 'lucide-react'
import {
  adminGetOrg, adminGetOrgUsers, adminUpdatePlan, adminSetLLMKey,
  adminRemoveLLMKey, adminCreateApiKey,
} from '../../api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from 'sonner'

const PLANS = ['free', 'starter', 'growth', 'enterprise']
const STATUSES = ['trialing', 'active', 'past_due', 'canceled']

export default function AdminOrgDetail() {
  const { id } = useParams()
  const [org, setOrg] = useState(null)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [plan, setPlan] = useState('')
  const [subStatus, setSubStatus] = useState('')
  const [llmKey, setLlmKey] = useState('')
  const [llmModel, setLlmModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [newApiKeyResult, setNewApiKeyResult] = useState(null)

  useEffect(() => {
    Promise.all([adminGetOrg(id), adminGetOrgUsers(id)]).then(([o, u]) => {
      setOrg(o.data)
      setPlan(o.data.plan)
      setSubStatus(o.data.subscription_status)
      setLlmModel(o.data.llm_model || '')
      setUsers(u.data)
    }).finally(() => setLoading(false))
  }, [id])

  const savePlan = async () => {
    setSaving(true)
    try {
      await adminUpdatePlan(id, { plan, subscription_status: subStatus })
      toast.success('Plan updated')
    } catch { toast.error('Failed to update plan') }
    finally { setSaving(false) }
  }

  const saveLLM = async () => {
    if (!llmKey) return
    setSaving(true)
    try {
      await adminSetLLMKey(id, { api_key: llmKey, model: llmModel || undefined })
      setLlmKey('')
      toast.success('LLM key saved')
      const o = await adminGetOrg(id)
      setOrg(o.data)
    } catch { toast.error('Failed to save LLM key') }
    finally { setSaving(false) }
  }

  const removeLLM = async () => {
    if (!confirm('Remove LLM key?')) return
    setSaving(true)
    try {
      await adminRemoveLLMKey(id)
      toast.success('LLM key removed')
      const o = await adminGetOrg(id)
      setOrg(o.data)
    } catch { toast.error('Failed to remove LLM key') }
    finally { setSaving(false) }
  }

  const createApiKey = async () => {
    setSaving(true)
    try {
      const res = await adminCreateApiKey(id, { name: 'default' })
      setNewApiKeyResult(res.data.api_key)
      toast.success('API key created — copy it now, it won\'t be shown again')
    } catch { toast.error('Failed to create API key') }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>
  if (!org) return <div className="py-20 text-center text-muted-foreground">Org not found.</div>

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" asChild><Link to="/orgs"><ArrowLeft className="size-4" /></Link></Button>
        <div>
          <h1 className="text-2xl font-bold">{org.name}</h1>
          <p className="text-sm text-muted-foreground font-mono">{org.slug}</p>
        </div>
        <Badge variant="outline" className="capitalize ml-2">{org.plan}</Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Plan management */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Plan & Billing</CardTitle>
            <CardDescription>Update plan and subscription status. Stripe integration coming soon.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Plan</Label>
                <Select value={plan} onValueChange={setPlan}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{PLANS.map((p) => <SelectItem key={p} value={p} className="capitalize">{p}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Status</Label>
                <Select value={subStatus} onValueChange={setSubStatus}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            {org.stripe_customer_id && (
              <p className="text-xs text-muted-foreground">Stripe ID: <code>{org.stripe_customer_id}</code></p>
            )}
            <Button onClick={savePlan} disabled={saving} className="w-fit">
              {saving ? <Loader2 className="size-4 mr-2 animate-spin" /> : <Save className="size-4 mr-2" />}
              Save plan
            </Button>
          </CardContent>
        </Card>

        {/* LLM Key */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">LLM API Key</CardTitle>
            <CardDescription>Set the OpenRouter key for this org's AI narration. Takes priority over global key.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex items-center gap-2 rounded-lg border bg-muted/40 p-3">
              <Key className="size-4 text-muted-foreground shrink-0" />
              <span className="text-sm">
                {org.has_llm_key
                  ? <span className="text-green-600 dark:text-green-400 font-medium">Key configured</span>
                  : <span className="text-muted-foreground">No key set — using global fallback</span>}
              </span>
              {org.llm_model && <Badge variant="outline" className="ml-auto text-xs">{org.llm_model}</Badge>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>New API key</Label>
              <Input
                type="password"
                placeholder="sk-or-v1-..."
                value={llmKey}
                onChange={(e) => setLlmKey(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Model override (optional)</Label>
              <Input
                placeholder="e.g. nvidia/nemotron-3-super-120b..."
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={saveLLM} disabled={!llmKey || saving} size="sm">
                {saving ? <Loader2 className="size-4 mr-1 animate-spin" /> : null}
                Save key
              </Button>
              {org.has_llm_key && (
                <Button variant="outline" size="sm" onClick={removeLLM} disabled={saving}>
                  <Trash2 className="size-4 mr-1" />Remove
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* API Key */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">API Key</CardTitle>
          <CardDescription>Create a programmatic API key for this org. Keys are shown once — copy immediately.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {newApiKeyResult && (
            <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-3">
              <p className="text-xs font-medium text-green-700 dark:text-green-400 mb-1">Copy now — won't be shown again:</p>
              <code className="text-sm font-mono break-all select-all">{newApiKeyResult}</code>
            </div>
          )}
          <Button variant="outline" size="sm" onClick={createApiKey} disabled={saving} className="w-fit">
            <Key className="size-4 mr-2" />
            Generate new API key
          </Button>
        </CardContent>
      </Card>

      {/* Users */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Members ({users.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Last login</TableHead>
                <TableHead>Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-mono text-sm">{u.email}</TableCell>
                  <TableCell className="text-sm">{u.full_name || '—'}</TableCell>
                  <TableCell><Badge variant="outline" className="capitalize">{u.role}</Badge></TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : '—'}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(u.created_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
