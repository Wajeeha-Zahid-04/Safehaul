import type { FeatureCollection, LineString, Point } from 'geojson'
import type { PlanResponse, RiskLevel } from '../api/types'

export interface SegmentProps {
  routeId: number
  level: RiskLevel
}

export interface CheckpointProps {
  routeId: number
  index: number
  level: RiskLevel
}

export type Bounds = [[number, number], [number, number]]

/** One LineString per checkpoint segment, coloured by that checkpoint's level. */
export function routeSegments(plan: PlanResponse): FeatureCollection<LineString, SegmentProps> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((route) =>
      route.checkpoints.map((cp) => ({
        type: 'Feature' as const,
        geometry: { type: 'LineString' as const, coordinates: cp.path },
        properties: { routeId: route.id, level: cp.level },
      })),
    ),
  }
}

export function checkpointPoints(plan: PlanResponse): FeatureCollection<Point, CheckpointProps> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((route) =>
      route.checkpoints.map((cp) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [cp.lon, cp.lat] },
        properties: { routeId: route.id, index: cp.index, level: cp.level },
      })),
    ),
  }
}

/** [[west, south], [east, north]] -> GeoJSON bbox [min_lon, min_lat, max_lon, max_lat]. */
export function toBBox([[w, s], [e, n]]: Bounds): [number, number, number, number] {
  return [w, s, e, n]
}

/** Union of all route bboxes as [[west, south], [east, north]]. */
export function planBounds(plan: PlanResponse): Bounds {
  const [first, ...rest] = plan.routes.map((r) => r.bbox)
  return rest.reduce<Bounds>(
    ([[w, s], [e, n]], [minLon, minLat, maxLon, maxLat]) => [
      [Math.min(w, minLon), Math.min(s, minLat)],
      [Math.max(e, maxLon), Math.max(n, maxLat)],
    ],
    [
      [first[0], first[1]],
      [first[2], first[3]],
    ],
  )
}
