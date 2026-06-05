import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Building2, ExternalLink, Loader2, Search } from 'lucide-react'
import { adminGetOrgs } from '../../api/endpoints'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const PLAN_COLORS = {
  free: 'secondary',
  starter: 'outline',
  growth: 'default',
  enterprise: 'default',
}

const STATUS_COLORS = {
  trialing: 'outline',
  active: 'default',
  past_due: 'destructive',
  canceled: 'secondary',
}

export default function AdminOrgs() {
  const [orgs, setOrgs] = useState([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')

  useEffect(() => {
    adminGetOrgs().then((r) => setOrgs(r.data)).finally(() => setLoading(false))
  }, [])

  const filtered = orgs.filter(
    (o) => o.name.toLowerCase().includes(q.toLowerCase()) || o.slug.includes(q.toLowerCase())
  )

  if (loading) return <div className="flex justify-center py-20"><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Organisations</h1>
          <p className="text-sm text-muted-foreground">{orgs.length} workspaces total</p>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-4">
        {[
          { label: 'Total', value: orgs.length },
          { label: 'Free', value: orgs.filter((o) => o.plan === 'free').length },
          { label: 'Paid', value: orgs.filter((o) => o.plan !== 'free').length },
          { label: 'With LLM key', value: orgs.filter((o) => o.has_llm_key).length },
        ].map((s) => (
          <Card key={s.label}>
            <CardHeader className="pb-1 pt-4 px-4">
              <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{s.label}</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <div className="text-2xl font-bold">{s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Search by name or slug…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Organisation</TableHead>
              <TableHead>Plan</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Users</TableHead>
              <TableHead>LLM key</TableHead>
              <TableHead>Created</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((org) => (
              <TableRow key={org.id}>
                <TableCell>
                  <div className="font-medium">{org.name}</div>
                  <div className="text-xs text-muted-foreground font-mono">{org.slug}</div>
                </TableCell>
                <TableCell>
                  <Badge variant={PLAN_COLORS[org.plan] || 'outline'} className="capitalize">{org.plan}</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_COLORS[org.subscription_status] || 'outline'} className="capitalize text-xs">
                    {org.subscription_status}
                  </Badge>
                </TableCell>
                <TableCell className="text-right font-mono text-sm">{org.user_count}</TableCell>
                <TableCell>
                  {org.has_llm_key
                    ? <span className="text-xs text-green-600 dark:text-green-400 font-medium">✓ set</span>
                    : <span className="text-xs text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(org.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon" asChild>
                    <Link to={`/orgs/${org.id}`}><ExternalLink className="size-4" /></Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}
