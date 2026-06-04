export default function HealthBadge({ status, size = 'sm' }) {
  const map = {
    healthy: 'bg-green-500/10 text-green-400 border-green-500/20',
    warning: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    error:   'bg-red-500/10 text-red-400 border-red-500/20',
    paused:  'bg-gray-500/10 text-gray-400 border-gray-500/20',
    pending: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    connected: 'bg-green-500/10 text-green-400 border-green-500/20',
    open:    'bg-red-500/10 text-red-400 border-red-500/20',
    acknowledged: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    resolved: 'bg-green-500/10 text-green-400 border-green-500/20',
  }
  const cls = map[status?.toLowerCase()] || 'bg-gray-500/10 text-gray-400 border-gray-500/20'
  const sz = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1'
  return (
    <span className={`inline-flex items-center rounded-full border font-medium ${cls} ${sz}`}>
      {status}
    </span>
  )
}
