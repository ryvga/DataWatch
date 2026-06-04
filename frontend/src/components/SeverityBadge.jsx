export default function SeverityBadge({ severity }) {
  const map = {
    P1: 'bg-red-500/15 text-red-400 border-red-500/30',
    P2: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    P3: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  }
  const cls = map[severity?.toUpperCase()] || 'bg-gray-500/15 text-gray-400 border-gray-500/30'
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-bold ${cls}`}>
      {severity?.toUpperCase()}
    </span>
  )
}
