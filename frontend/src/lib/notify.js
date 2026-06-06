/**
 * Panopta notification system — wraps Sonner with domain-specific variants.
 *
 * Usage:
 *   notify.ok('Source connected')
 *   notify.err('Connection failed', 'Check credentials')
 *   notify.source.connected('prod-postgres')
 *   notify.incident.p1('users — empty table', 'Row count dropped to 0')
 *   notify.profiling.started('public.orders')
 *   notify.profiling.done('public.orders', 41_000)
 */
import { toast } from 'sonner'

const SHORT  = 3000
const STD    = 4500
const LONG   = 7000
const STICKY = Infinity

// ── Primitives ────────────────────────────────────────────────────────────────

export const notify = {
  ok: (msg, description) =>
    toast.success(msg, { description, duration: SHORT }),

  err: (msg, description) =>
    toast.error(msg, { description, duration: LONG }),

  warn: (msg, description) =>
    toast.warning(msg, { description, duration: STD }),

  info: (msg, description) =>
    toast.info(msg, { description, duration: STD }),

  loading: (msg, description) =>
    toast.loading(msg, { description }),

  dismiss: (id) => toast.dismiss(id),

  // ── Data source ─────────────────────────────────────────────────────────────
  source: {
    connected: (name) =>
      toast.success(`${name} connected`, {
        description: 'Connection test passed — ready for schema discovery.',
        duration: STD,
      }),

    failed: (name, detail) =>
      toast.error(`${name} unreachable`, {
        description: detail || 'Connection test failed. Check credentials in Settings.',
        duration: LONG,
      }),

    deleted: (name) =>
      toast.success(`${name} archived`, {
        description: 'All monitored tables from this source are paused.',
        duration: STD,
      }),

    testing: (name) =>
      toast.loading(`Testing ${name}…`, {
        description: 'Attempting connection to the warehouse.',
      }),

    discovered: (name, count) =>
      toast.info(`${name} — ${count} schema${count !== 1 ? 's' : ''} found`, {
        description: 'Select a schema and table name below.',
        duration: STD,
      }),
  },

  // ── Table monitoring ─────────────────────────────────────────────────────────
  table: {
    added: (name) =>
      toast.success(`Now monitoring ${name}`, {
        description: 'First profile will run on the next scheduled interval.',
        duration: STD,
      }),

    removed: (name) =>
      toast.success(`${name} removed`, {
        description: 'Historical profiles and incidents are preserved.',
        duration: STD,
      }),

    runQueued: (name) =>
      toast.info(`Profile run queued for ${name}`, {
        description: 'Results will appear in a few seconds.',
        duration: STD,
      }),
  },

  // ── Profiling ────────────────────────────────────────────────────────────────
  profiling: {
    started: (name) =>
      toast.loading(`Profiling ${name}…`, {
        description: 'Running aggregate SQL query on the warehouse.',
      }),

    done: (name, rows) =>
      toast.success(`${name} profiled`, {
        description: rows != null
          ? `${rows.toLocaleString()} rows · anomaly checks queued.`
          : 'Anomaly detection checks queued.',
        duration: STD,
      }),

    failed: (name) =>
      toast.error(`Profiling failed — ${name}`, {
        description: 'Check the data source connection and table permissions.',
        duration: LONG,
      }),
  },

  // ── Incidents ────────────────────────────────────────────────────────────────
  incident: {
    p1: (title, detail) =>
      toast.error(`🚨 P1 — ${title}`, {
        description: detail || 'Critical anomaly detected. Immediate attention required.',
        duration: STICKY,
        important: true,
      }),

    p2: (title, detail) =>
      toast.warning(`⚡ P2 — ${title}`, {
        description: detail || 'Significant anomaly detected.',
        duration: LONG,
      }),

    p3: (title, detail) =>
      toast.info(`P3 — ${title}`, {
        description: detail || 'Statistical anomaly detected.',
        duration: STD,
      }),

    acknowledged: (title) =>
      toast.info(`Acknowledged: ${title}`, {
        description: 'Incident is being investigated.',
        duration: STD,
      }),

    resolved: (title) =>
      toast.success(`Resolved: ${title}`, {
        description: 'Incident closed and marked as resolved.',
        duration: STD,
      }),
  },

  // ── AI narration ─────────────────────────────────────────────────────────────
  narration: {
    retrying: () =>
      toast.loading('Re-running AI analysis…', {
        description: 'Queued with the LLM worker.',
      }),

    ready: () =>
      toast.success('AI analysis ready', {
        description: 'Incident report generated successfully.',
        duration: STD,
      }),

    failed: () =>
      toast.error('AI analysis failed', {
        description: 'LLM could not generate a valid report. Try again.',
        duration: LONG,
      }),
  },

  // ── Alerts / routing ─────────────────────────────────────────────────────────
  alert: {
    created: (channel) =>
      toast.success(`${channel} alert route created`, {
        description: 'Incidents above the threshold will be dispatched here.',
        duration: STD,
      }),

    deleted: (channel) =>
      toast.success(`${channel} route removed`, {
        duration: SHORT,
      }),

    testSent: (channel) =>
      toast.success(`Test delivered to ${channel}`, {
        description: 'If nothing arrived, check webhook URL and permissions.',
        duration: STD,
      }),

    testFailed: (channel) =>
      toast.error(`${channel} test failed`, {
        description: 'Delivery error — verify config and retry.',
        duration: LONG,
      }),
  },
}
