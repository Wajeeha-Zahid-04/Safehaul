import type { ExpressionSpecification } from 'maplibre-gl'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import Map, {
  Layer,
  NavigationControl,
  Source,
  type LayerProps,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'
import type { HeatmapRequest, PlanResponse } from '../api/types'
import { MAP_STYLE_URL } from '../config'
import { checkpointPoints, planBounds, routeSegments } from '../lib/geojson'
import { maplibrePromise } from '../lib/maplibre'
import { riskColorExpression } from '../lib/risk'
import { CheckpointPopup } from './CheckpointPopup'
import { HeatmapLayer } from './HeatmapLayer'

const INITIAL_VIEW = { longitude: -96, latitude: 39, zoom: 3.5 }
const FIT_PADDING = 60
const CHECKPOINT_LAYER = 'checkpoints'
const ROUTE_CASING_LAYER = 'route-casing'

interface Props {
  plan: PlanResponse | undefined
  selectedRouteId: number | null
  heatmapRequest: HeatmapRequest | null
}

interface PopupTarget {
  routeId: number
  index: number
}

function isSelected(selectedRouteId: number | null): ExpressionSpecification {
  return ['==', ['get', 'routeId'], selectedRouteId ?? -1]
}

/** Selected route: thick and opaque, drawn on top. Others: thinner at 40% opacity (spec §4). */
function routeLayers(selectedRouteId: number | null): LayerProps[] {
  const selected = isSelected(selectedRouteId)
  const opacity: ExpressionSpecification = ['case', selected, 1, 0.4]
  const sortKey: ExpressionSpecification = ['case', selected, 1, 0]
  return [
    {
      id: ROUTE_CASING_LAYER,
      type: 'line',
      layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': sortKey },
      paint: {
        'line-color': '#ffffff',
        'line-width': ['case', selected, 10, 6],
        'line-opacity': opacity,
      },
    },
    {
      id: 'route-line',
      type: 'line',
      layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': sortKey },
      paint: {
        'line-color': riskColorExpression,
        'line-width': ['case', selected, 6, 3],
        'line-opacity': opacity,
      },
    },
  ]
}

function checkpointLayer(selectedRouteId: number | null): LayerProps {
  return {
    id: CHECKPOINT_LAYER,
    type: 'circle',
    filter: isSelected(selectedRouteId),
    paint: {
      'circle-radius': 6,
      'circle-color': riskColorExpression,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2,
    },
  }
}

// Memoised so panel-only state changes (form typing, card hover) never re-render the map.
export const MapView = memo(function MapView({ plan, selectedRouteId, heatmapRequest }: Props) {
  const mapRef = useRef<MapRef>(null)
  const [popup, setPopup] = useState<PopupTarget | null>(null)
  const [hovering, setHovering] = useState(false)

  // GeoJSON depends only on the plan, so switching routes never re-uploads source data.
  const segments = useMemo(() => (plan ? routeSegments(plan) : null), [plan])
  const points = useMemo(() => (plan ? checkpointPoints(plan) : null), [plan])
  const [casing, line] = useMemo(() => routeLayers(selectedRouteId), [selectedRouteId])
  const circles = useMemo(() => checkpointLayer(selectedRouteId), [selectedRouteId])

  useEffect(() => {
    if (plan) mapRef.current?.fitBounds(planBounds(plan), { padding: FIT_PADDING, duration: 800 })
  }, [plan])

  // Popup only for a checkpoint on the selected route of the current plan.
  const popupCheckpoint =
    popup && popup.routeId === selectedRouteId
      ? plan?.routes.find((r) => r.id === popup.routeId)?.checkpoints[popup.index]
      : undefined

  function onClick(e: MapLayerMouseEvent) {
    const props = e.features?.[0]?.properties
    setPopup(props ? { routeId: Number(props.routeId), index: Number(props.index) } : null)
  }

  return (
    <Map
      ref={mapRef}
      mapLib={maplibrePromise}
      initialViewState={INITIAL_VIEW}
      mapStyle={MAP_STYLE_URL}
      interactiveLayerIds={[CHECKPOINT_LAYER]}
      onClick={onClick}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      cursor={hovering ? 'pointer' : 'grab'}
      style={{ width: '100%', height: '100%' }}
    >
      <NavigationControl position="top-right" />
      {segments && (
        <Source id="routes" type="geojson" data={segments}>
          <Layer {...casing} />
          <Layer {...line} />
        </Source>
      )}
      {points && (
        <Source id="checkpoints" type="geojson" data={points}>
          <Layer {...circles} />
        </Source>
      )}
      {heatmapRequest && segments && (
        // Keyed by request so a new plan remounts it: fresh query, slider back to hour 0.
        <HeatmapLayer
          key={JSON.stringify(heatmapRequest)}
          request={heatmapRequest}
          beforeId={ROUTE_CASING_LAYER}
        />
      )}
      {popupCheckpoint && (
        <CheckpointPopup checkpoint={popupCheckpoint} onClose={() => setPopup(null)} />
      )}
    </Map>
  )
})
