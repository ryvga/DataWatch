import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Bot, ChevronRight, CircleAlert, Plus, RefreshCw, ShieldCheck } from 'lucide-react'
import { createAISystem, getAISystem, getAISystems } from '@/api/endpoints'
import { notify } from '@/lib/notify'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'

const stateTone = {
  pass: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  fail: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  error: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  unknown: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  unsupported: 'border-border bg-muted text-muted-foreground',
  not_applicable: 'border-border bg-muted text-muted-foreground',
  action_required: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  evidence_gap: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  observed_healthy: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  not_assessed: 'border-border bg-muted text-muted-foreground',
}

function StatusBadge({ value }) {
  return <Badge variant="outline" className={stateTone[value] || 'capitalize'}>{String(value || 'not assessed').replaceAll('_', ' ')}</Badge>
}

function CreateSystemDialog({ onCreated }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ name: '', slug: '', intended_purpose: '', human_oversight: '' })
  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      const { data } = await createAISystem({
        ...form,
        slug: form.slug || form.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
        lifecycle_status: 'draft', autonomy_level: 'assistive', prohibited_uses: [], risk_context: {},
      })
      setOpen(false)
      setForm({ name: '', slug: '', intended_purpose: '', human_oversight: '' })
      notify.success('AI system registered in observe mode')
      onCreated(data)
    } catch (error) {
      notify.error(error.response?.data?.detail || 'Could not register AI system')
    } finally { setSaving(false) }
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="mr-2 size-4" />Register system</Button></DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <form onSubmit={submit}>
          <DialogHeader><DialogTitle>Register an AI system</DialogTitle><DialogDescription>Record accountability and purpose first. This phase observes and warns; it never blocks a deployment.</DialogDescription></DialogHeader>
          <div className="grid gap-4 py-5">
            <div className="grid gap-2"><Label htmlFor="ai-name">System name</Label><Input id="ai-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Customer support RAG" /></div>
            <div className="grid gap-2"><Label htmlFor="ai-slug">Stable slug</Label><Input id="ai-slug" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })} placeholder="Generated from the name" /></div>
            <div className="grid gap-2"><Label htmlFor="ai-purpose">Intended purpose</Label><Textarea id="ai-purpose" required value={form.intended_purpose} onChange={(e) => setForm({ ...form, intended_purpose: e.target.value })} placeholder="What decision or workflow does this system support?" /></div>
            <div className="grid gap-2"><Label htmlFor="ai-oversight">Human oversight</Label><Textarea id="ai-oversight" required value={form.human_oversight} onChange={(e) => setForm({ ...form, human_oversight: e.target.value })} placeholder="Who reviews outputs, and how can they intervene?" /></div>
          </div>
          <DialogFooter><Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={saving}>{saving ? 'Registering…' : 'Register system'}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Inventory() {
  const navigate = useNavigate()
  const [systems, setSystems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const load = async () => {
    setLoading(true); setError('')
    try { setSystems((await getAISystems()).data) } catch { setError('AI governance inventory could not be loaded.') } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div><div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground"><ShieldCheck className="size-4" />Observe-only governance</div><h1 className="text-2xl font-semibold tracking-tight">AI systems</h1><p className="mt-1 max-w-2xl text-sm text-muted-foreground">Trace versions, declared database use, active release manifests, and evidence without storing prompts, outputs, rows, or embeddings.</p></div>
        <CreateSystemDialog onCreated={(item) => navigate(`/ai-systems/${item.id}`)} />
      </div>
      {error && <div role="alert" className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"><CircleAlert className="size-4" />{error}<Button size="sm" variant="outline" className="ml-auto" onClick={load}><RefreshCw className="mr-2 size-3.5" />Retry</Button></div>}
      <Card><CardHeader><CardTitle className="text-base">Governance work queue</CardTitle><CardDescription>Systems needing ownership or with open control failures appear first.</CardDescription></CardHeader><CardContent className="p-0">
        <Table><TableHeader><TableRow><TableHead>System</TableHead><TableHead>Lifecycle</TableHead><TableHead>Version</TableHead><TableHead>Owners</TableHead><TableHead className="text-right">Open failures</TableHead><TableHead className="w-10" /></TableRow></TableHeader>
          <TableBody>{loading ? <TableRow><TableCell colSpan={6} className="h-28 text-center text-muted-foreground">Loading inventory…</TableCell></TableRow> : systems.length === 0 ? <TableRow><TableCell colSpan={6} className="h-36 text-center"><Bot className="mx-auto mb-3 size-8 text-muted-foreground/50" /><p className="font-medium">No AI systems registered</p><p className="mt-1 text-sm text-muted-foreground">Start with purpose and accountable owners, then bind a version to verified assets.</p></TableCell></TableRow> : [...systems].sort((a, b) => b.openFailures - a.openFailures).map((item) => {
            const ownerCount = [item.businessOwnerId, item.technicalOwnerId, item.riskOwnerId].filter(Boolean).length
            return <TableRow key={item.id} className="cursor-pointer" onClick={() => navigate(`/ai-systems/${item.id}`)}><TableCell><div className="font-medium">{item.name}</div><div className="text-xs text-muted-foreground">{item.slug}</div></TableCell><TableCell><Badge variant="secondary" className="capitalize">{item.lifecycleStatus}</Badge></TableCell><TableCell className="font-mono text-xs">{item.currentVersionId ? item.currentVersionId.slice(0, 8) : 'Not versioned'}</TableCell><TableCell><span className={ownerCount === 3 ? '' : 'text-amber-700 dark:text-amber-300'}>{ownerCount}/3 assigned</span></TableCell><TableCell className="text-right tabular-nums">{item.openFailures}</TableCell><TableCell><ChevronRight className="size-4 text-muted-foreground" /></TableCell></TableRow>
          })}</TableBody></Table>
      </CardContent></Card>
    </div>
  )
}

function Detail({ id }) {
  const [system, setSystem] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { getAISystem(id).then(({ data }) => setSystem(data)).catch(() => setError('This AI system could not be loaded.')) }, [id])
  if (error) return <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-destructive">{error}</div>
  if (!system) return <div className="py-20 text-center text-sm text-muted-foreground">Loading AI system…</div>
  const owners = [system.businessOwnerId, system.technicalOwnerId, system.riskOwnerId].filter(Boolean).length
  const summary = system.governanceSummary || { headlineStatus: 'not_assessed', inherentRisk: { score: 0, components: {} }, controlCoveragePercent: 0, evidenceConfidencePercent: 0, residualRiskScore: 0, reasons: [] }
  return (
    <div className="space-y-6">
      <div><Button variant="ghost" size="sm" asChild className="-ml-2 mb-3"><Link to="/ai-systems"><ArrowLeft className="mr-2 size-4" />AI systems</Link></Button><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><h1 className="text-2xl font-semibold tracking-tight">{system.name}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{system.intendedPurpose}</p></div><Badge variant="outline">Observe only</Badge></div></div>
      <div className="grid gap-4 md:grid-cols-4">
        <Card><CardHeader className="pb-2"><CardDescription>Accountability</CardDescription><CardTitle className="text-2xl">{owners}/3 owners</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">Business, technical, and risk ownership are independently tracked.</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Governance status</CardDescription><CardTitle className="text-lg"><StatusBadge value={summary.headlineStatus} /></CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">Derived from linked controls and evidence; gaps never count as passing.</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Evidence confidence</CardDescription><CardTitle className="text-2xl tabular-nums">{summary.evidenceConfidencePercent}%</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">Conclusive, current evidence divided by applicable controls.</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardDescription>Residual risk</CardDescription><CardTitle className="text-2xl tabular-nums">{summary.residualRiskScore}/100</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">Inherent {summary.inherentRisk.score}/100 · coverage {summary.controlCoveragePercent}%.</CardContent></Card>
      </div>
      {summary.reasons.length > 0 && <Card><CardHeader><CardTitle className="text-base">Why this status?</CardTitle><CardDescription>Every headline state resolves to its latest control reason.</CardDescription></CardHeader><CardContent className="grid gap-2 sm:grid-cols-2">{summary.reasons.map((reason) => <div key={`${reason.controlId}-${reason.reasonCode}`} className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm"><div><p className="font-medium">{reason.controlId}</p><p className="text-xs text-muted-foreground">{reason.reasonCode.replaceAll('_', ' ')}</p></div><StatusBadge value={reason.status} /></div>)}</CardContent></Card>}
      <Card><CardHeader><CardTitle className="text-base">Declared data map</CardTitle><CardDescription>Immutable, schema-bound declarations. They do not claim observed workload use or legal purpose.</CardDescription></CardHeader><CardContent className="p-0"><Table><TableHeader><TableRow><TableHead>Use</TableHead><TableHead>Fields</TableHead><TableHead>Evidence class</TableHead><TableHead>Schema binding</TableHead></TableRow></TableHeader><TableBody>{system.dataUses.length ? system.dataUses.map((item) => <TableRow key={item.id}><TableCell className="capitalize">{item.definition.useKind.replaceAll('_', ' ')}</TableCell><TableCell>{item.definition.fields.join(', ')}</TableCell><TableCell><Badge variant="outline">{item.evidenceClass}</Badge></TableCell><TableCell className="font-mono text-xs">{item.definition.schemaFingerprint.slice(0, 12)}</TableCell></TableRow>) : <TableRow><TableCell colSpan={4} className="h-24 text-center text-muted-foreground">No data-use revision has been bound to a version.</TableCell></TableRow>}</TableBody></Table></CardContent></Card>
      <Card><CardHeader><CardTitle className="text-base">Evidence timeline</CardTitle><CardDescription>Terminal evaluations link to immutable, content-addressed, metadata-only evidence.</CardDescription></CardHeader><CardContent className="space-y-0">{system.evidenceTimeline.length ? system.evidenceTimeline.map((item) => <div key={item.id} className="flex gap-4 border-l pl-5 pb-5 last:pb-0"><div className="-ml-[25px] mt-1.5 size-2.5 rounded-full bg-border ring-4 ring-background" /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="font-medium">{item.controlId}</span><StatusBadge value={item.status} /><Badge variant="outline">{item.evidenceClass}</Badge></div><p className="mt-1 text-sm text-muted-foreground">{item.reasonCode.replaceAll('_', ' ')}</p><p className="mt-1 font-mono text-[11px] text-muted-foreground">evaluation {item.inputHash.slice(0, 16)} · evidence {item.evidenceId?.slice(0, 8) || 'historical'} · {new Date(item.createdAt).toLocaleString()}</p></div></div>) : <div className="py-10 text-center text-sm text-muted-foreground">Activate a manifest and run an evaluation to create connector-backed evidence.</div>}</CardContent></Card>
    </div>
  )
}

export default function AISystems() {
  const { id } = useParams()
  return id ? <Detail id={id} /> : <Inventory />
}
