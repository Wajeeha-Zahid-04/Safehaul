import { useState, type FormEvent } from 'react'
import type { IntervalMi, Place, PlanRequest } from '../api/types'
import {
  DEPARTURE_GRACE_MS,
  MAX_DEPARTURE_AHEAD_MS,
  fromLocalInputValue,
  toLocalInputValue,
} from '../lib/datetime'
import { PlaceAutocomplete } from './PlaceAutocomplete'

const INTERVALS: IntervalMi[] = [10, 25, 50]
const MAX_LOAD_LB = 120_000
const DEFAULT_LOAD_LB = 40_000

interface Props {
  isSubmitting: boolean
  onSubmit: (request: PlanRequest) => void
}

function validate(
  origin: Place | null,
  destination: Place | null,
  departure: Date | null,
  load: number,
): string | null {
  if (!origin || !destination) return 'Pick an origin and destination from the suggestions.'
  if (origin.lat === destination.lat && origin.lon === destination.lon) {
    return 'Origin and destination must be different.'
  }
  const now = Date.now()
  if (!departure) return 'Choose a departure date and time.'
  if (departure.getTime() < now - DEPARTURE_GRACE_MS) return 'Departure cannot be in the past.'
  if (departure.getTime() > now + MAX_DEPARTURE_AHEAD_MS) {
    return 'Departure must be within the next 48 hours.'
  }
  if (!Number.isFinite(load) || load < 0 || load > MAX_LOAD_LB) {
    return `Load must be between 0 and ${MAX_LOAD_LB.toLocaleString()} lb.`
  }
  return null
}

export function TripForm({ isSubmitting, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departure, setDeparture] = useState(() => toLocalInputValue(new Date()))
  const [load, setLoad] = useState(String(DEFAULT_LOAD_LB))
  const [interval, setIntervalMi] = useState<IntervalMi>(25)
  const [error, setError] = useState<string | null>(null)
  // Picker bounds; refreshed on focus so they don't go stale while the page is open.
  const [nowMs, setNowMs] = useState(() => Date.now())

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const departureDate = fromLocalInputValue(departure)
    const loadLb = Number(load)
    const problem = validate(origin, destination, departureDate, loadLb)
    setError(problem)
    if (problem || !origin || !destination || !departureDate) return
    onSubmit({
      origin,
      destination,
      departure: departureDate.toISOString(),
      load_lb: loadLb,
      interval_mi: interval,
    })
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <PlaceAutocomplete
        label="Origin"
        placeholder="e.g. Chicago, IL"
        value={origin}
        onChange={setOrigin}
      />
      <PlaceAutocomplete
        label="Destination"
        placeholder="e.g. Detroit, MI"
        value={destination}
        onChange={setDestination}
      />

      <div>
        <label htmlFor="departure" className="mb-1 block text-sm font-medium text-slate-700">
          Departure
        </label>
        <input
          id="departure"
          type="datetime-local"
          value={departure}
          min={toLocalInputValue(new Date(nowMs))}
          max={toLocalInputValue(new Date(nowMs + MAX_DEPARTURE_AHEAD_MS))}
          onFocus={() => setNowMs(Date.now())}
          onChange={(e) => setDeparture(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:ring-2 focus:ring-sky-200 focus:outline-none"
        />
        <p className="mt-1 text-xs text-slate-500">Now to 48 hours ahead, local time.</p>
      </div>

      <div>
        <label htmlFor="load" className="mb-1 block text-sm font-medium text-slate-700">
          Load weight (lb)
        </label>
        <input
          id="load"
          type="number"
          inputMode="numeric"
          min={0}
          max={MAX_LOAD_LB}
          step={500}
          value={load}
          onChange={(e) => setLoad(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:ring-2 focus:ring-sky-200 focus:outline-none"
        />
      </div>

      <fieldset>
        <legend className="mb-1 block text-sm font-medium text-slate-700">Checkpoint every</legend>
        <div role="radiogroup" className="grid grid-cols-3 rounded-md border border-slate-300 p-0.5">
          {INTERVALS.map((mi) => (
            <button
              key={mi}
              type="button"
              role="radio"
              aria-checked={interval === mi}
              onClick={() => setIntervalMi(mi)}
              className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                interval === mi ? 'bg-sky-600 text-white' : 'text-slate-700 hover:bg-slate-100'
              }`}
            >
              {mi} mi
            </button>
          ))}
        </div>
      </fieldset>

      {error && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-400"
      >
        {isSubmitting && (
          <span
            aria-hidden
            className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
          />
        )}
        {isSubmitting ? 'Planning routes…' : 'Plan routes'}
      </button>
    </form>
  )
}
