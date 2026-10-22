import { useQuery } from '@tanstack/react-query'
import type { GeoJSONSource } from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Layer, Source, useMap, type LayerProps } from 'react-map-gl/maplibre'
import { ApiError, fetchHeatmap } from '../api/client'
import type { HeatmapRequest, HeatmapResponse } from '../api/types'
import {
  HEATMAP_INTENSITY,
  heatmapColor,
  heatmapFrames,
  heatmapRadius,
  heatmapWeight,
  meanLatitude,
} from '../lib/heatmap'

const SOURCE_ID = 'heatmap'
const HEATMAP_STALE_MS = 30 * 60_000 // matches the backend's 30-minute heatmap cache
const TICKS = [0, 12, 24, 36, 48]

const slotFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

interface Props {
  request: HeatmapRequest
  /** Hidden layers keep their data and slider position; toggling never refetches. */
  visible: boolean
  /** Draw the heatmap beneath this layer so route lines stay on top. */
  beforeId?: string
}

function clampToNow(iso: string): string {
  return new Date(Math.max(Date.parse(iso), Date.now())).toISOString()
}

function heatmapLayer(data: HeatmapResponse, visible: boolean): LayerProps {
  return {
    id: 'heatmap',
    type: 'heatmap',
    layout: { visibility: visible ? 'visible' : 'none' },
    paint: {
      'heatmap-weight': heatmapWeight,
      'heatmap-radius': heatmapRadius(data.spacing_km, meanLatitude(data)),
      'heatmap-intensity': HEATMAP_INTENSITY,
      'heatmap-color': heatmapColor,
      'heatmap-opacity': 0.75,
    },
  }
}

/**
 * Corridor heatmap with a 0-48 h slider (spec §4). All 49 hours are fetched once and turned
 * into one GeoJSON frame per hour up front. Moving the slider schedules a single
 * requestAnimationFrame that calls setData on the MapLibre source: no refetch, no React
 * re-render of the map, at most one source update per display frame.
 */
export function HeatmapLayer({ request, visible, beforeId }: Props) {
  const { current: mapRef } = useMap()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['heatmap', request],
    // Clamp to now: a Retry long after a "depart now" plan would otherwise send a past start.
    queryFn: ({ signal }) =>
      fetchHeatmap({ ...request, start: clampToNow(request.start) }, signal),
    staleTime: HEATMAP_STALE_MS,
    // A busy (503) quota won't clear in a second; let the user retry instead.
    retry: (failures, err) => failures < 1 && !(err instanceof ApiError && err.status === 503),
  })

  const frames = useMemo(() => (data ? heatmapFrames(data) : null), [data])
  const layer = useMemo(() => (data ? heatmapLayer(data, visible) : null), [data, visible])
  const startMs = useMemo(() => (data ? new Date(data.start).getTime() : 0), [data])
  // Frames only contain Moderate-or-worse cells, so a frame's size is its elevated-cell count.
  const elevated = useMemo(() => frames?.map((f) => f.features.length) ?? [], [frames])
  const peakHour = useMemo(
    () => elevated.reduce((best, n, h) => (n > elevated[best] ? h : best), 0),
    [elevated],
  )

  const [hour, setHour] = useState(0)
  const targetHour = useRef(0)
  const rafId = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (rafId.current !== null) cancelAnimationFrame(rafId.current)
    },
    [],
  )

  function showHour(next: number) {
    setHour(next) // only the label/slider re-render
    targetHour.current = next
    if (rafId.current !== null) return // an update is already queued for this frame
    rafId.current = requestAnimationFrame(() => {
      rafId.current = null
      const source = mapRef?.getMap().getSource<GeoJSONSource>(SOURCE_ID)
      if (source && frames) source.setData(frames[targetHour.current])
    })
  }

  return (
    <>
      {frames && layer && (
        // `data` stays frames[0] for the source's lifetime; later hours go through setData.
        <Source id={SOURCE_ID} type="geojson" data={frames[0]}>
          <Layer {...layer} beforeId={beforeId} />
        </Source>
      )}

      {/* Mobile: under the legend at the top (the bottom sheet covers the bottom).
          Desktop: centred along the bottom of the map. */}
      <div
        className={`absolute top-[6.75rem] right-14 left-3 rounded-lg bg-white/95 p-3 shadow-lg ring-1 ring-slate-200 md:top-auto md:right-auto md:bottom-8 md:left-1/2 md:w-[min(520px,calc(100%-2rem))] md:-translate-x-1/2 ${
          visible ? '' : 'hidden'
        }`}
      >
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Corridor risk forecast
          </span>
          {data && (
            <span className="text-sm font-semibold text-slate-900 tabular-nums" aria-live="polite">
              {slotFormat.format(startMs + hour * 3_600_000)}
              <span className="ml-1.5 font-normal text-slate-500">+{hour} h</span>
            </span>
          )}
        </div>

        {isPending && (
          <div className="mt-2 space-y-2" aria-busy>
            <div className="h-2 animate-pulse rounded bg-slate-200" />
            <p className="text-xs text-slate-500">Loading 48 h forecast for the corridor…</p>
          </div>
        )}

        {isError && (
          <div className="mt-2 flex items-center justify-between gap-3 text-sm">
            <span className="text-red-700">Heatmap unavailable: {error.message}</span>
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded border border-slate-300 px-2 py-0.5 text-xs font-medium hover:bg-slate-50"
            >
              Retry
            </button>
          </div>
        )}

        {data && (
          <>
            <input
              type="range"
              min={0}
              max={data.hours - 1}
              step={1}
              value={hour}
              onChange={(e) => showHour(Number(e.target.value))}
              aria-label="Forecast hour"
              aria-valuetext={`${slotFormat.format(startMs + hour * 3_600_000)}, plus ${hour} hours`}
              className="mt-2 w-full accent-sky-600"
            />
            <div className="flex justify-between text-[11px] text-slate-500 tabular-nums">
              {TICKS.map((t) => (
                <span key={t}>{t} h</span>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-slate-600" aria-live="polite">
              {elevated[peakHour] === 0 ? (
                'No Moderate-or-worse weather in this corridor over the next 48 h.'
              ) : elevated[hour] > 0 ? (
                `${elevated[hour]} area${elevated[hour] === 1 ? '' : 's'} at Moderate or worse.`
              ) : (
                <>
                  Calm at this hour.{' '}
                  <button
                    type="button"
                    onClick={() => showHour(peakHour)}
                    className="font-medium text-sky-700 underline hover:text-sky-900"
                  >
                    Jump to busiest hour (+{peakHour} h)
                  </button>
                </>
              )}
            </p>
          </>
        )}
      </div>
    </>
  )
}
