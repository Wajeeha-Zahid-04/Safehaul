// Result-area states (spec §4): empty, loading, error with retry, all-routes-No-Travel.
import { RISK_COLORS } from '../lib/risk'

export function EmptyState() {
  return (
    <div className="mt-6 rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-600">
      <p className="font-medium text-slate-800">Compare up to 3 truck routes</p>
      <p className="mt-1">
        Pick an origin and destination. Each route is checked against the forecast at the
        truck's ETA for every checkpoint, with your load weight applied.
      </p>
    </div>
  )
}

export function SkeletonCards({ count = 3 }: { count?: number }) {
  return (
    <div className="mt-6 space-y-3" aria-busy aria-label="Loading routes">
      <div className="h-4 w-28 animate-pulse rounded bg-slate-200" />
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="space-y-3 rounded-lg border border-slate-200 p-3">
          <div className="h-4 w-1/3 animate-pulse rounded bg-slate-200" />
          <div className="grid grid-cols-3 gap-3">
            {Array.from({ length: 6 }, (_, j) => (
              <div key={j} className="h-8 animate-pulse rounded bg-slate-100" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm">
      <p className="font-medium text-red-800">Couldn't plan this trip</p>
      <p className="mt-1 text-red-700">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-100"
      >
        Retry
      </button>
    </div>
  )
}

export function NoTravelBanner() {
  return (
    <div
      role="alert"
      className="mt-6 rounded-lg p-4 text-sm text-white"
      style={{ backgroundColor: RISK_COLORS[4] }}
    >
      <p className="font-semibold">Every route has No-Travel conditions</p>
      <p className="mt-1 text-white/90">
        Do not travel on these routes at this departure time. Try a later departure or a lighter
        load; the recommended route has the least No-Travel exposure.
      </p>
    </div>
  )
}

export function Disclaimer() {
  return (
    <p className="mt-6 border-t border-slate-200 pt-3 text-xs text-slate-500">
      SafeHaul is a decision aid based on forecast data. It is not an official safety clearance;
      always follow road authority closures and your own judgement.
    </p>
  )
}
