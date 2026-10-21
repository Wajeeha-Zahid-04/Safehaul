import { useMutation } from '@tanstack/react-query'
import { planTrip } from './api/client'
import { TripForm } from './components/TripForm'

// RouteCards, MapView and HeatmapLayer are added in tickets #10-#13.
export default function App() {
  const plan = useMutation({ mutationFn: planTrip })

  return (
    <div className="flex h-screen w-screen">
      <aside className="w-[380px] shrink-0 overflow-y-auto border-r border-slate-200 p-4">
        <h1 className="text-xl font-semibold">SafeHaul</h1>
        <p className="mt-1 mb-4 text-sm text-slate-600">Truck route safety planner</p>
        <TripForm isSubmitting={plan.isPending} onSubmit={(request) => plan.mutate(request)} />
        {plan.isSuccess && (
          <p className="mt-4 text-sm text-slate-700">
            {plan.data.routes.length} route(s) planned. {plan.data.recommendation_reason}
          </p>
        )}
        {plan.isError && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {plan.error.message}
          </p>
        )}
      </aside>
      <main className="flex-1" />
    </div>
  )
}
