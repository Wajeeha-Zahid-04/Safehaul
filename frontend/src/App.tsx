import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { planTrip } from './api/client'
import type { HeatmapRequest } from './api/types'
import { MapView } from './components/MapView'
import {
  Disclaimer,
  EmptyState,
  ErrorState,
  NoTravelBanner,
  SkeletonCards,
} from './components/PanelStates'
import { RouteCards } from './components/RouteCards'
import { TripForm } from './components/TripForm'
import { planBounds, toBBox } from './lib/geojson'

export default function App() {
  const [selectedRouteId, setSelectedRouteId] = useState<number | null>(null)
  const [sheetExpanded, setSheetExpanded] = useState(false) // mobile bottom sheet only
  const plan = useMutation({
    mutationFn: planTrip,
    onSuccess: (data) => setSelectedRouteId(data.recommended_id),
  })

  // Heatmap covers every route, starts at the trip's departure and uses the trip's load.
  const heatmapRequest = useMemo<HeatmapRequest | null>(
    () =>
      plan.data && plan.variables
        ? {
            bbox: toBBox(planBounds(plan.data)),
            start: plan.variables.departure,
            load_lb: plan.variables.load_lb,
          }
        : null,
    [plan.data, plan.variables],
  )

  return (
    // Desktop: 380 px panel + map. Mobile: full-screen map with the panel as a bottom sheet.
    <div className="relative h-dvh w-screen overflow-hidden md:flex">
      <main className="absolute inset-0 md:relative md:flex-1 md:order-2">
        <MapView
          plan={plan.data}
          selectedRouteId={selectedRouteId}
          heatmapRequest={heatmapRequest}
        />
      </main>

      <aside
        className={`absolute inset-x-0 bottom-0 z-20 flex flex-col rounded-t-2xl bg-white shadow-[0_-4px_24px_rgba(15,23,42,0.18)] transition-[max-height] duration-300 md:static md:order-1 md:max-h-none md:w-[380px] md:shrink-0 md:rounded-none md:border-r md:border-slate-200 md:shadow-none ${
          sheetExpanded ? 'max-h-[85dvh]' : 'max-h-[42dvh]'
        }`}
      >
        <button
          type="button"
          onClick={() => setSheetExpanded((open) => !open)}
          aria-expanded={sheetExpanded}
          aria-label={sheetExpanded ? 'Collapse panel' : 'Expand panel'}
          className="flex w-full justify-center py-2 md:hidden"
        >
          <span className="h-1.5 w-10 rounded-full bg-slate-300" />
        </button>

        <div className="overflow-y-auto px-4 pb-4 md:pt-4">
          <h1 className="text-xl font-semibold">SafeHaul</h1>
          <p className="mt-1 mb-4 text-sm text-slate-600">Truck route safety planner</p>
          <TripForm isSubmitting={plan.isPending} onSubmit={(request) => plan.mutate(request)} />

          {plan.isIdle && <EmptyState />}
          {plan.isPending && <SkeletonCards />}
          {plan.isError && (
            <ErrorState
              message={plan.error.message}
              onRetry={() => plan.variables && plan.mutate(plan.variables)}
            />
          )}
          {plan.isSuccess && (
            <>
              {plan.data.all_no_travel && <NoTravelBanner />}
              <RouteCards
                plan={plan.data}
                selectedRouteId={selectedRouteId}
                onSelect={setSelectedRouteId}
              />
            </>
          )}

          <Disclaimer />
        </div>
      </aside>
    </div>
  )
}
