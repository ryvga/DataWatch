import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { format } from 'date-fns'

export default function MetricChart({ data, dataKey, anomalies = [], color = 'hsl(var(--chart-1))', label = '' }) {
  if (!data?.length) {
    return (
      <div className="flex h-44 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
        No profile data yet
      </div>
    )
  }

  const formatted = data.map((p) => ({
    ...p,
    _ts: format(new Date(p.collected_at), 'MM/dd HH:mm'),
    _val: p[dataKey] ?? null,
  }))

  return (
    <ResponsiveContainer width="100%" height={210}>
      <LineChart data={formatted} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis
          dataKey="_ts"
          tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} tickLine={false} axisLine={false} width={64} />
        <Tooltip
          contentStyle={{
            background: 'hsl(var(--popover))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 8,
            color: 'hsl(var(--popover-foreground))',
            boxShadow: '0 10px 24px rgba(0, 0, 0, 0.12)',
          }}
          labelStyle={{ color: 'hsl(var(--muted-foreground))' }}
          itemStyle={{ color }}
          formatter={(v) => [v?.toLocaleString(), label || dataKey]}
        />
        <Line type="monotone" dataKey="_val" stroke={color} strokeWidth={2} dot={false} connectNulls />
        {anomalies.map((a, i) => (
          <ReferenceDot
            key={i}
            x={format(new Date(a.collected_at), 'MM/dd HH:mm')}
            y={a[dataKey]}
            r={5}
            fill="hsl(var(--destructive))"
            stroke="hsl(var(--background))"
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
