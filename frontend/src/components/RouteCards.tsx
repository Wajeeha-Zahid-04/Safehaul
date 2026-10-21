import type { PlanResponse, RouteResult } from '../api/types'
import { formatDuration, routeName } from '../lib/format'
import { RISK_COLORS } from '../lib/risk'

interface Props {
  plan: PlanResponse
  selectedRouteId: number | null
  onSelect: (routeId: number) => void
}

interface StatProps {
  label: string
  value: string
  highlight?: string // risk colour when the value is non-zero
}

function Stat({ label, value, highlight }: StatProps) {
  return (
    <div>
      <dt className="text-[11px] tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className="font-semibold tabular-nums" style={highlight ? { color: highlight } : undefined}>
        {value}
      </dd>
    </div>
  )
}

function milesStat(label: string, miles: number, color: string) {
  return <Stat label={label} value={`${miles} mi`} highlight={miles > 0 ? color : undefined} />
}

function RouteCard({
  route,
  recommended,
  reason,
  selected,
  onSelect,
}: {
  route: RouteResult
  recommended: boolean
  reason: string
  selected: boolean
  onSelect: (routeId: number) => void
}) {
  return (
    <li>
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect(route.id)}
        className={`w-full rounded-lg border p-3 text-left transition-shadow ${
          selected
            ? 'border-sky-500 bg-sky-50/50 shadow-md ring-1 ring-sky-500'
            : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
        }`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-slate-900">{routeName(route.id)}</span>
          {recommended && (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
              Recommended
            </span>
          )}
          {route.do_not_travel && (
            <span
              className="rounded-full px-2 py-0.5 text-xs font-semibold text-white"
              style={{ backgroundColor: RISK_COLORS[4] }}
            >
              Do not travel
            </span>
          )}
        </div>
        {recommended && <p className="mt-1 text-sm text-slate-600">{reason}</p>}

        <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2 text-sm">
          <Stat label="Distance" value={`${route.distance_mi} mi`} />
          <Stat label="Time" value={formatDuration(route.duration_s)} />
          <Stat label="Avg risk" value={route.avg_score.toFixed(2)} />
          {milesStat('Severe', route.severe_mi, RISK_COLORS[3])}
          {milesStat('High', route.high_mi, RISK_COLORS[2])}
          {milesStat('No Travel', route.notravel_mi, RISK_COLORS[4])}
        </dl>
      </button>
    </li>
  )
}

export function RouteCards({ plan, selectedRouteId, onSelect }: Props) {
  // The API returns routes ranked, so the recommended route is already first.
  return (
    <section aria-label="Route options" className="mt-6">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">
        {plan.routes.length} route{plan.routes.length === 1 ? '' : 's'} found
      </h2>
      <ul className="space-y-3">
        {plan.routes.map((route) => (
          <RouteCard
            key={route.id}
            route={route}
            recommended={route.id === plan.recommended_id}
            reason={plan.recommendation_reason}
            selected={route.id === selectedRouteId}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </section>
  )
}
