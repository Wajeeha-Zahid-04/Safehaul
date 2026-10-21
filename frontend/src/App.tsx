// App shell. TripForm, RouteCards, MapView and HeatmapLayer are added in tickets #9–#13.
export default function App() {
  return (
    <div className="flex h-screen w-screen">
      <aside className="w-[380px] shrink-0 overflow-y-auto border-r border-slate-200 p-4">
        <h1 className="text-xl font-semibold">SafeHaul</h1>
        <p className="mt-1 text-sm text-slate-600">Truck route safety planner</p>
      </aside>
      <main className="flex-1" />
    </div>
  )
}
