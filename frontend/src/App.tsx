import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { planTrip } from './api/client'
import type { HeatmapRequest } from './api/types'
import { MapView } from './components/MapView'
import { RouteCards } from './components/RouteCards'
import { TripForm } from './components/TripForm'
import { planBounds, toBBox } from './lib/geojson'

// Legend, heatmap toggle and the full loading/error/No-Travel states come in ticket #13.
export default function App() {
  const [selectedRouteId, setSelectedRouteId] = useState<number | null>(null)
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
    <div className="flex h-screen w-screen">
      <aside className="w-[380px] shrink-0 overflow-y-auto border-r border-slate-200 p-4">
        <h1 className="text-xl font-semibold">SafeHaul</h1>
        <p className="mt-1 mb-4 text-sm text-slate-600">Truck route safety planner</p>
        <TripForm isSubmitting={plan.isPending} onSubmit={(request) => plan.mutate(request)} />
        {plan.isSuccess && (
          <RouteCards
            plan={plan.data}
            selectedRouteId={selectedRouteId}
            onSelect={setSelectedRouteId}
          />
        )}
        {plan.isError && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {plan.error.message}
          </p>
        )}
      </aside>
      <main className="relative flex-1">
        <MapView
          plan={plan.data}
          selectedRouteId={selectedRouteId}
          heatmapRequest={heatmapRequest}
        />
      </main>
    </div>
  )
}
