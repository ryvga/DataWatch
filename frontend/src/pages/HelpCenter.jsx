import { useState } from 'react'
import { Search, ChevronDown, ChevronRight, BarChart2, TrendingUp, Activity, AlertCircle, Layers, Target, GitBranch, ArrowUpDown, Percent, Clock, Hash } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// ─── Data ────────────────────────────────────────────────────────────────────

const CATEGORIES = [
  {
    id: 'statistical',
    label: 'Statistical Methods',
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/20',
    icon: BarChart2,
  },
  {
    id: 'ml',
    label: 'Machine Learning',
    color: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/20',
    icon: Activity,
  },
  {
    id: 'spc',
    label: 'Statistical Process Control',
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
    icon: TrendingUp,
  },
  {
    id: 'rule',
    label: 'Rule-Based',
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/20',
    icon: AlertCircle,
  },
  {
    id: 'structural',
    label: 'Structural Checks',
    color: 'text-rose-600 dark:text-rose-400',
    bg: 'bg-rose-500/10',
    border: 'border-rose-500/20',
    icon: Layers,
  },
]

const METHODS = [
  {
    id: 'zscore',
    category: 'statistical',
    name: 'Z-Score',
    icon: BarChart2,
    tagline: 'How many standard deviations away from the mean?',
    minHistory: '7 snapshots',
    what: `The Z-Score measures how far a value is from the historical average, expressed in units of standard deviation. A Z-Score of 0 means the value is exactly at the average; a Z-Score of ±3 means it sits at the outer edge of what the data normally produces.`,
    how: `For a rolling window of the last 14 daily snapshots, the system computes the arithmetic mean (μ) and standard deviation (σ). The current observation x is then normalized:

  Z = (x − μ) / σ

If |Z| exceeds the sensitivity threshold (default 3), the check raises an anomaly. The threshold is tunable per table: a lower value is more sensitive (catches subtle shifts), a higher value only flags dramatic deviations.`,
    why: `Z-Score works well when data follows an approximately bell-shaped (Gaussian) distribution and anomalies appear as sudden isolated spikes or drops rather than gradual trends. It is fast to compute and easy to interpret.`,
    limits: `Z-Score is less reliable when the distribution is highly skewed, when there are fewer than 7 historical points, or when the data exhibits strong seasonality (where the Isolation Forest or STL methods are more appropriate).`,
    example: `If row counts over the past 14 days averaged 50,000 with a standard deviation of 2,000, a count of 42,000 would produce Z = (42,000 − 50,000) / 2,000 = −4. This exceeds the threshold of ±3, triggering an alert.`,
  },
  {
    id: 'isolation_forest',
    category: 'ml',
    name: 'Isolation Forest',
    icon: Activity,
    tagline: 'Multivariate anomaly detection using random partitioning',
    minHistory: '21 snapshots',
    what: `Isolation Forest is an ensemble machine-learning algorithm that identifies anomalies by measuring how easily a data point can be isolated from the rest of the dataset through random recursive partitioning.`,
    how: `The algorithm builds many binary decision trees (an "isolation forest"). At each node, a feature is chosen at random and a random split value is selected within the observed range. Anomalous points — being rare and extreme — tend to be isolated near the root of the tree with very few splits. Normal points require many splits to isolate.

The anomaly score for a point is based on the average path length across all trees:

  score(x) = 2^(−E[h(x)] / c(n))

where E[h(x)] is the average path length and c(n) is the expected path length for a dataset of size n. Scores close to 1 indicate strong anomalies; scores near 0.5 are normal.

Panopta evaluates five metrics jointly: row count, null rate, distinct ratio, mean value, and standard deviation. This multivariate approach catches anomalies that would look normal on any single metric in isolation.`,
    why: `Unlike Z-Score, Isolation Forest does not assume a particular distribution and captures complex, multidimensional anomalies. It excels when multiple metrics simultaneously deviate in correlated ways.`,
    limits: `Requires at least 21 historical snapshots for the model to be stable. The trained model is cached and reused (refreshed every 7 days) to avoid the computational cost of retraining on every snapshot.`,
    example: `Suppose row count stays normal but null rate suddenly climbs while distinct ratio drops — each individually might fall within Z-Score tolerance, but Isolation Forest recognizes the joint pattern as anomalous.`,
  },
  {
    id: 'stl',
    category: 'statistical',
    name: 'STL Seasonal Decomposition',
    icon: TrendingUp,
    tagline: 'Separate trend, seasonality, and residual noise',
    minHistory: '21 daily snapshots',
    what: `STL (Seasonal and Trend decomposition using Loess) decomposes a time series into three additive components: a smooth trend, a repeating seasonal pattern, and the residual (noise). An anomaly is detected when the residual becomes unusually large.`,
    how: `Given a time series y_t, STL finds:

  y_t = T_t + S_t + R_t

where T_t is the trend (a smoothed moving average), S_t is the seasonal component (weekly cycle with period = 7 for daily data), and R_t = y_t − T_t − S_t is the residual.

Anomalies are flagged when the residual deviates more than 3 standard deviations from zero:

  |R_t| > 3 · σ_R`,
    why: `Many real-world datasets have natural weekly patterns (e.g., lower activity on weekends). STL removes this structure before measuring deviation, preventing the system from alerting every Monday because volume is routinely low.`,
    limits: `Requires at least 21 daily snapshots to estimate both trend and seasonal components reliably. Seasonal period is fixed at 7 days.`,
    example: `A table that regularly shows half its weekday volume on Sundays is not flagged by STL — but if Sunday volume drops to zero unexpectedly, the residual spikes and an alert fires.`,
  },
  {
    id: 'cusum',
    category: 'spc',
    name: 'CUSUM',
    icon: Target,
    tagline: 'Cumulative sum control chart for detecting gradual shifts',
    minHistory: '10 snapshots',
    what: `CUSUM (Cumulative Sum Control Chart) is a sequential analysis technique from statistical process control. Unlike Z-Score, which resets with each new observation, CUSUM accumulates evidence of a sustained shift over time, making it far more sensitive to gradual drift.`,
    how: `First, each new observation x_i is normalized against the historical mean μ and standard deviation σ:

  d_i = (x_i − μ) / σ

Two accumulators are maintained — one tracking upward shifts (C⁺) and one tracking downward shifts (C⁻):

  C⁺ᵢ = max(0, C⁺ᵢ₋₁ + dᵢ − k)
  C⁻ᵢ = max(0, C⁻ᵢ₋₁ − dᵢ − k)

The allowance k (default 0.5) determines the smallest shift worth detecting (in σ units). An alert fires when either accumulator exceeds the decision threshold h (default 5.0), meaning sustained cumulative evidence of a shift.`,
    why: `CUSUM is the gold standard for detecting process mean shifts in manufacturing quality control and is equally powerful for data pipelines. It catches gradual, persistent degradation (e.g., row counts steadily declining 2% per day) that would individually never cross a Z-Score threshold but cumulatively signal a systemic problem.`,
    limits: `CUSUM is designed to detect persistent shifts, not isolated spikes (Z-Score handles those better). It requires at least 10 historical points to estimate the baseline mean and standard deviation.`,
    example: `If row counts drift down by 3% each day for a week, each daily Z-Score might be only −0.5 — far below the alert threshold. But CUSUM's C⁻ accumulates: after 7 days it could reach 5.0+, triggering a shift detection alert.`,
  },
  {
    id: 'mann_kendall',
    category: 'spc',
    name: 'Mann-Kendall Trend Test',
    icon: TrendingUp,
    tagline: 'Non-parametric test for monotonic trends',
    minHistory: '8 snapshots',
    what: `The Mann-Kendall test is a non-parametric hypothesis test that determines whether a time series has a statistically significant monotonic (consistently increasing or decreasing) trend, without assuming any particular probability distribution.`,
    how: `The test compares all pairs of observations in the series. For each pair (i < j), it records a concordant pair (+1) if x_j > x_i, a discordant pair (−1) if x_j < x_i, or a tie (0).

The Kendall correlation coefficient τ is defined as:

  τ = (concordant − discordant) / (n(n−1)/2)

Values of τ close to +1 indicate a strong upward trend; close to −1, a strong downward trend; near 0, no consistent trend.

A p-value is computed from the distribution of τ under the null hypothesis of no trend. Panopta flags the check as anomalous when:

  |τ| > 0.6  AND  p-value < 0.05

Both conditions must hold simultaneously — a strong trend that is statistically significant.`,
    why: `Mann-Kendall does not require the data to be normally distributed and is robust to outliers. It is ideal for detecting long-running trends in data volumes, such as a table that has been slowly growing or shrinking over weeks.`,
    limits: `The test measures monotonic trend, not sudden level shifts (use CUSUM for those). It requires at least 8 historical points to produce a meaningful p-value.`,
    example: `If a table's row count has increased every week for the past 10 weeks, Mann-Kendall would produce τ ≈ +1 with p ≈ 0.001, flagging a significant upward trend — potentially indicating unbounded data accumulation.`,
  },
  {
    id: 'percentile_drift',
    category: 'statistical',
    name: 'Percentile Drift',
    icon: Percent,
    tagline: 'Compare current distribution shape to its historical baseline',
    minHistory: '14 snapshots',
    what: `Percentile Drift checks whether the shape of a numeric column's value distribution has shifted significantly compared to its historical baseline. It focuses on the median (p50) and 95th percentile (p95), which together characterize central tendency and tail behavior.`,
    how: `For each numeric column with sufficient history, the system computes rolling averages of p50 and p95 over the past 14 snapshots:

  avg_p50 = mean(p50₁, p50₂, …, p50₁₄)
  avg_p95 = mean(p95₁, p95₂, …, p95₁₄)

The relative change for the current snapshot is then:

  relative_change = |current − avg| / max(|avg|, 1.0)

An alert fires when relative_change > 30% for either percentile. Using relative change (rather than absolute) ensures the check scales properly regardless of the magnitude of the column's values.`,
    why: `Row count and null rate measure volume and completeness, but they miss distributional shifts. A column where prices were clustered around $50 suddenly clustering around $500 would pass row count checks — but Percentile Drift would catch the shift in the median.`,
    limits: `Only numeric columns are evaluated. The check is less meaningful for columns with very low cardinality (e.g., boolean flags).`,
    example: `If the median order amount was $47 historically but is now $71, relative change = |71 − 47| / 47 ≈ 51% > 30% — alert fires. This could indicate a pricing schema change, a data pipeline bug, or currency conversion drift.`,
  },
  {
    id: 'cardinality_drop',
    category: 'statistical',
    name: 'Cardinality Drop',
    icon: Hash,
    tagline: 'Detect when a column loses its expected variety of distinct values',
    minHistory: '7 snapshots',
    what: `Cardinality refers to the number of distinct values in a column relative to its total row count. A sudden drop in cardinality indicates that values have become suspiciously concentrated — possibly due to a bug causing repeated values, a pipeline truncation, or incorrect data backfill.`,
    how: `For each column, the distinct ratio is computed as:

  distinct_ratio = distinct_count / total_row_count

The system maintains a 14-day rolling average of this ratio: avg_ratio. An anomaly is flagged when the current ratio drops more than 30% relative to the historical baseline:

  relative_drop = (avg_ratio − current_ratio) / avg_ratio > 0.30`,
    why: `A table that normally has 10,000 unique customer IDs suddenly having only 50 is a serious data quality signal. The cardinality check catches this pattern that neither Z-Score nor rule checks would reliably detect.`,
    limits: `Not meaningful for columns that are inherently low-cardinality (e.g., status codes with 3 possible values). Best suited for ID columns, email addresses, and other high-cardinality identifiers.`,
    example: `If a "user_id" column typically has a distinct ratio of 0.95 (95% unique) but today it shows 0.30, relative drop = (0.95 − 0.30) / 0.95 ≈ 68% — far above the 30% threshold.`,
  },
  {
    id: 'row_growth',
    category: 'statistical',
    name: 'Row Growth Rate',
    icon: ArrowUpDown,
    tagline: 'Detect abnormal changes in how fast a table is growing',
    minHistory: '7 snapshots',
    what: `Rather than measuring the absolute row count, this check measures the per-snapshot change (delta) in row count and applies Z-Score analysis to those deltas. This makes it sensitive to abnormal growth or shrinkage even in very large tables.`,
    how: `The system computes the row count delta between consecutive snapshots:

  Δᵢ = row_count_i − row_count_{i−1}

A rolling window of the last 14 deltas is used to compute the mean (μ_Δ) and standard deviation (σ_Δ). The Z-Score of the most recent delta is:

  Z_Δ = (Δ_current − μ_Δ) / σ_Δ

An alert fires when |Z_Δ| exceeds 3.`,
    why: `A table that grows by 5,000 rows per hour should raise an alert if it suddenly grows by 50,000 rows or by 0 rows — both are anomalies relative to its expected growth rate, regardless of the absolute size.`,
    limits: `Not meaningful for tables that are batch-overwritten (where deltas would be near −100% each cycle). Best for append-only or incrementally growing tables.`,
    example: `An event log table adds ~10,000 events per day (μ_Δ = 10,000, σ_Δ = 500). A sudden day with only 200 new events gives Z = (200 − 10,000) / 500 = −19.6 — far above threshold, indicating the event pipeline likely stopped.`,
  },
  {
    id: 'null_rate',
    category: 'statistical',
    name: 'Null Rate Trend',
    icon: Percent,
    tagline: 'Flag columns where missing data increases over time',
    minHistory: '7 snapshots',
    what: `This check tracks the fraction of NULL (missing) values in each column across successive snapshots. A rising null rate suggests that a data source is becoming incomplete — a sensor stopped reporting, an API started returning empty values, or a join key became unresolvable.`,
    how: `For each column, the null rate at time t is:

  null_rate_t = null_count_t / total_rows_t

The system computes the Z-Score of the current null rate against its rolling 14-snapshot history. Separately, it applies a rule-based check: if null rate jumps more than 20 percentage points (absolute) in a single snapshot, an immediate alert fires regardless of the historical baseline.`,
    why: `Null rates are one of the most reliable early indicators of data pipeline failure. They often rise gradually before a complete outage, giving time to investigate before downstream systems are affected.`,
    limits: `Columns that are intentionally nullable (e.g., optional fields in a form) may have legitimate null rate variation. Sensitivity can be adjusted per table.`,
    example: `A GPS coordinates column that was 2% null rises to 28% null — an absolute jump of 26pp — immediately flagged as a rule-based anomaly, even if the Z-Score hasn't accumulated enough history yet.`,
  },
  {
    id: 'schema_change',
    category: 'structural',
    name: 'Schema Change Detection',
    icon: GitBranch,
    tagline: 'Alert when columns are added, removed, or renamed',
    minHistory: '1 snapshot (baseline)',
    what: `Every time a table is profiled, the system computes a fingerprint of its column structure: the set of column names and their data types. When this fingerprint changes from one snapshot to the next, a schema change event is recorded.`,
    how: `The schema fingerprint is a deterministic hash of sorted column names and types:

  fingerprint = hash({col: type for col in schema})

If the current fingerprint differs from the previous one, the system identifies the specific differences:
  - Added columns (appear in current but not previous)
  - Dropped columns (in previous but not current)
  - Type changes (same name, different type)

Schema changes produce P2 (High) severity incidents.`,
    why: `Unexpected schema changes are among the most disruptive data quality events. A dropped column can silently break downstream reports, dashboards, and machine learning pipelines without any row count change to signal the problem.`,
    limits: `Does not detect column renames (which appear as a drop + add). Does not track column ordering changes.`,
    example: `A "revenue" column is renamed to "revenue_usd" in a schema migration. Panopta sees "revenue" as dropped and "revenue_usd" as added — P2 incident fires, allowing downstream teams to update their queries before the discrepancy causes silent failures.`,
  },
  {
    id: 'freshness',
    category: 'rule',
    name: 'Freshness / SLA Check',
    icon: Clock,
    tagline: 'Verify data arrives within the expected time window',
    minHistory: '0 (immediate)',
    what: `A freshness check verifies that the most recent timestamp in a designated timestamp column is no older than the expected data arrival interval. This ensures that the data pipeline is actively delivering new data on schedule.`,
    how: `When a "freshness column" is configured for a table, the profiler queries:

  freshness_seconds = NOW() − MAX(freshness_column)

If freshness_seconds exceeds the monitoring interval (plus a configurable grace period), a rule violation fires immediately — no historical baseline is needed. This check is P1 (Critical) severity because stale data directly signals a broken pipeline.`,
    why: `A table can have correct schema, good row counts, and healthy null rates — but still be useless if its data is 6 hours old. Freshness checks are the most direct measure of pipeline health and are often the first line of alerting in data reliability engineering.`,
    limits: `Requires a designated timestamp column to be configured. If no freshness column is set, this check is skipped.`,
    example: `An orders table is expected to refresh every 15 minutes. If the latest order timestamp is 2 hours ago, freshness_seconds ≈ 7,200. This far exceeds the 15-minute interval, generating a P1 incident.`,
  },
  {
    id: 'enum_drift',
    category: 'structural',
    name: 'Enum / Category Drift',
    icon: Layers,
    tagline: 'Detect new or disappearing categories in categorical columns',
    minHistory: '3 snapshots',
    what: `For columns with a small number of distinct values (categorical or enum-like columns), this check tracks the set of observed values over time. New values appearing or existing values disappearing can indicate data quality issues or undocumented system changes.`,
    how: `The system maintains a reference set of expected categories from historical snapshots. For each new snapshot:

  new_values = current_distinct_values − historical_union
  missing_values = historical_union − current_distinct_values

An alert fires when new values appear that were never seen before, or when previously common values entirely disappear (indicating data encoding changes or enum contract violations).`,
    why: `A "payment_status" column that has always contained {pending, completed, failed} suddenly containing "refunded" is a semantic change that may break downstream logic filtering on those values. Enum drift catches this before it silently corrupts reports.`,
    limits: `Only applied to columns with fewer than 50 distinct values. High-cardinality columns (like user IDs) are excluded as their value sets naturally evolve.`,
    example: `A "country_code" column adds "XK" (Kosovo) after a data provider update. Without this check, no alert would fire — the row count is unchanged. Enum drift flags the new value, prompting validation against downstream country-filtering logic.`,
  },
  {
    id: 'uniqueness',
    category: 'rule',
    name: 'Uniqueness Check',
    icon: Target,
    tagline: 'Detect duplicate rows in columns that should be unique',
    minHistory: '0 (immediate)',
    what: `For columns that are expected to have unique values (primary keys, UUIDs, transaction IDs), this check detects when the cardinality ratio drops below 1.0, indicating that duplicates are present.`,
    how: `The uniqueness ratio is:

  uniqueness_ratio = distinct_count / total_row_count

A ratio below 1.0 means duplicates exist. The check flags columns where:

  (1 − uniqueness_ratio) > 0.001

meaning more than 0.1% of rows are duplicates. This threshold prevents false alerts from floating-point precision issues while catching real data duplication events.`,
    why: `Duplicate primary keys or transaction IDs are catastrophic data quality failures. They cause double-counting in analytics, incorrect aggregations, and can violate referential integrity constraints. Early detection allows pipeline teams to identify and revert the bad load.`,
    limits: `Panopta does not know which columns are intended to be unique — it evaluates all high-cardinality columns. False positives may occur for columns that are naturally non-unique. Users can suppress specific column checks in table settings.`,
    example: `A transaction ID column normally has a distinct ratio of 1.000. After a pipeline bug causes an idempotent write to be executed twice, the ratio drops to 0.500 (every transaction duplicated). Uniqueness check fires immediately.`,
  },
  {
    id: 'distribution_drift',
    category: 'statistical',
    name: 'Distribution Drift',
    icon: BarChart2,
    tagline: 'Compare current statistical moments to the historical mean',
    minHistory: '7 snapshots',
    what: `Distribution drift checks whether the overall statistical shape of a numeric column has shifted by comparing its mean against its historical rolling average. This is a fast, first-order check for distributional change.`,
    how: `For each numeric column, the check computes how far the current mean deviates from the historical rolling average using Z-Score normalization:

  Z_mean = (mean_current − avg(mean_historical)) / std(mean_historical)

An alert fires when |Z_mean| > 3. This complements Percentile Drift — distribution drift is faster (runs always) while percentile drift catches asymmetric or tail-specific shifts that mean changes would miss.`,
    why: `The mean is the simplest summary of a numeric column's distribution. A shift in the mean is often the first detectable signal that the underlying data generation process has changed — even before outliers or null rates spike.`,
    limits: `The mean is sensitive to outliers. In skewed distributions, a single extreme value can shift the mean significantly. Percentile Drift (using median) is more robust for skewed columns.`,
    example: `A "response_time_ms" column with a historical mean of 120ms suddenly averages 380ms. This signals latency degradation in the upstream service long before users report it, and before row counts or null rates change.`,
  },
]

// ─── Component helpers ────────────────────────────────────────────────────────

function CategoryBadge({ categoryId }) {
  const cat = CATEGORIES.find((c) => c.id === categoryId)
  if (!cat) return null
  return (
    <span className={cn('rounded-full border px-2 py-0.5 text-[11px] font-medium', cat.bg, cat.border, cat.color)}>
      {cat.label}
    </span>
  )
}

function MethodCard({ method }) {
  const [open, setOpen] = useState(false)
  const Icon = method.icon

  return (
    <div className={cn('rounded-xl border bg-card overflow-hidden transition-shadow', open && 'shadow-md')}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start gap-4 p-5 text-left hover:bg-muted/30 transition-colors"
      >
        <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Icon className="size-4 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="font-semibold text-sm">{method.name}</span>
            <CategoryBadge categoryId={method.category} />
          </div>
          <p className="text-sm text-muted-foreground">{method.tagline}</p>
          <div className="mt-2 text-xs text-muted-foreground/60">Min. history: {method.minHistory}</div>
        </div>
        <div className="mt-1 text-muted-foreground shrink-0">
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </div>
      </button>

      {open && (
        <div className="border-t bg-muted/10 px-5 py-5 flex flex-col gap-5">
          <Section title="What it measures" content={method.what} />
          <Section title="How it works" content={method.how} mono />
          <Section title="Why it matters" content={method.why} />
          <Section title="Limitations" content={method.limits} />
          <div>
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Example</h4>
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-foreground/80">
              {method.example}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Section({ title, content, mono = false }) {
  return (
    <div>
      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">{title}</h4>
      <div className={cn('text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed', mono && 'font-mono text-[13px] bg-muted/40 rounded-lg p-3 border')}>
        {content}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function HelpCenter() {
  const [query, setQuery] = useState('')
  const [activeCategory, setActiveCategory] = useState(null)

  const filtered = METHODS.filter((m) => {
    const matchesQuery = !query || [m.name, m.tagline, m.what, m.how].join(' ').toLowerCase().includes(query.toLowerCase())
    const matchesCat = !activeCategory || m.category === activeCategory
    return matchesQuery && matchesCat
  })

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">Help Center</h1>
        <p className="mt-2 text-muted-foreground max-w-xl">
          How Panopta monitors your data — every detection method explained in mathematical terms, without the engineering jargon.
        </p>
      </div>

      {/* Search + filters */}
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search methods…"
            className="pl-9"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setActiveCategory(null)}
            className={cn(
              'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              !activeCategory
                ? 'bg-primary text-primary-foreground border-primary'
                : 'border-border text-muted-foreground hover:bg-muted'
            )}
          >
            All
          </button>
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => setActiveCategory(activeCategory === cat.id ? null : cat.id)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                activeCategory === cat.id
                  ? cn(cat.bg, cat.border, cat.color)
                  : 'border-border text-muted-foreground hover:bg-muted'
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results count */}
      {(query || activeCategory) && (
        <p className="mb-4 text-sm text-muted-foreground">
          {filtered.length} method{filtered.length !== 1 ? 's' : ''} found
        </p>
      )}

      {/* Method cards */}
      <div className="flex flex-col gap-3">
        {filtered.length === 0 ? (
          <div className="rounded-xl border bg-muted/20 p-10 text-center text-muted-foreground">
            No methods match your search.
          </div>
        ) : (
          filtered.map((m) => <MethodCard key={m.id} method={m} />)
        )}
      </div>

      {/* Footer context */}
      <div className="mt-10 rounded-xl border bg-muted/20 p-5">
        <h3 className="font-semibold mb-2">Severity Levels</h3>
        <div className="grid sm:grid-cols-3 gap-3 text-sm">
          <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
            <div className="font-semibold text-red-600 dark:text-red-400 mb-1">P1 — Critical</div>
            <p className="text-muted-foreground">Row count drops to zero, or freshness SLA is breached. Data is entirely missing or severely stale.</p>
          </div>
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
            <div className="font-semibold text-amber-600 dark:text-amber-400 mb-1">P2 — High</div>
            <p className="text-muted-foreground">Schema drift detected, or 3+ statistical checks fire simultaneously. Data may be structurally broken.</p>
          </div>
          <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <div className="font-semibold text-blue-600 dark:text-blue-400 mb-1">P3 — Medium</div>
            <p className="text-muted-foreground">1–2 statistical checks triggered. Data quality is degraded but not catastrophically broken.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
