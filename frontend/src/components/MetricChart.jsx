import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceDot, ResponsiveContainer,
} from 'recharts'
import { format } from 'date-fns'

export default function MetricChart({ data, dataKey, anomalies = [], color = '#3b82f6', label = '' }) {
  if (!data?.length) {
    return (
      <div className="flex items-center justify-center h-40 text-gray-600 text-sm">
        No data yet
      </div>
    )
  }

  const formatted = data.map((p) => ({
    ...p,
    _ts: format(new Date(p.collected_at), 'MM/dd HH:mm'),
    _val: p[dataKey] ?? null,
  }))

  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={formatted} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis
          dataKey="_ts"
          tick={{ fill: '#6b7280', fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: '#6b7280', fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={60}
        />
        <Tooltip
          contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
          labelStyle={{ color: '#9ca3af' }}
          itemStyle={{ color: color }}
          formatter={(v) => [v?.toLocaleString(), label || dataKey]}
        />
        <Line
          type="monotone"
          dataKey="_val"
          stroke={color}
          strokeWidth={2}
          dot={false}
          connectNulls
        />
        {anomalies.map((a, i) => (
          <ReferenceDot
            key={i}
            x={format(new Date(a.collected_at), 'MM/dd HH:mm')}
            y={a[dataKey]}
            r={5}
            fill="#ef4444"
            stroke="#991b1b"
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
