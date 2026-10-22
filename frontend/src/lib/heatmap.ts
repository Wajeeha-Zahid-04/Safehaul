import type { FeatureCollection, Point } from 'geojson'
import type { ExpressionSpecification } from 'maplibre-gl'
import type { HeatmapResponse, RiskLevel } from '../api/types'
import { RISK_COLORS } from './risk'

export interface HeatPointProps {
  score: RiskLevel
}

export type HeatmapFrame = FeatureCollection<Point, HeatPointProps>

// MapLibre zoom levels use 512 px tiles: 40,075 km / 512 px at the equator, zoom 0.
const METERS_PER_PIXEL_Z0 = 78_271.517
const MAX_ZOOM = 16
// Kernel radius relative to grid spacing: wide enough that neighbouring cells blend into one
// surface instead of separate dots.
const RADIUS_PER_SPACING = 2

/**
 * MapLibre's heatmap kernel is GAUSS * exp(-4.5 (r/R)^2) with GAUSS = 1/sqrt(2*pi) ~= 0.399.
 * Over a uniform grid (spacing d, radius R = k*d) the kernels sum to ~0.399 * pi * k^2 / 4.5,
 * which is ~1.11 for k = 2. Intensity 0.9 cancels that, so an area of uniform risk has
 * density ~= weight = score / 4 and shows its own level's colour in `heatmapColor`.
 * An isolated cell peaks lower (~0.36 x weight) but still clears the visible threshold.
 */
export const HEATMAP_INTENSITY = 0.9

/**
 * One GeoJSON frame per forecast hour, built once so the slider only swaps references.
 * Low (0) and missing (null) cells are omitted: they contribute no heat.
 */
export function heatmapFrames(data: HeatmapResponse): HeatmapFrame[] {
  return data.scores.map((row) => ({
    type: 'FeatureCollection',
    features: row.flatMap((score, i) =>
      score
        ? [
            {
              type: 'Feature' as const,
              geometry: {
                type: 'Point' as const,
                coordinates: [data.points[i][1], data.points[i][0]],
              },
              properties: { score },
            },
          ]
        : [],
    ),
  }))
}

/**
 * Pixel radius that keeps covering ~RADIUS_PER_SPACING grid cells at every zoom: grid spacing
 * in metres converted to pixels at zoom 0, then doubled per zoom level (exponential base 2).
 */
export function heatmapRadius(spacingKm: number, latitude: number): ExpressionSpecification {
  const metersPerPixel = METERS_PER_PIXEL_Z0 * Math.cos((latitude * Math.PI) / 180)
  const radiusZ0 = (spacingKm * 1000 * RADIUS_PER_SPACING) / metersPerPixel
  return [
    'interpolate',
    ['exponential', 2],
    ['zoom'],
    0,
    radiusZ0,
    MAX_ZOOM,
    radiusZ0 * 2 ** MAX_ZOOM,
  ]
}

/** Weight = risk score scaled to 0..1 (spec §4: "weight is the risk score"). */
export const heatmapWeight: ExpressionSpecification = ['/', ['get', 'score'], 4]

/**
 * Density -> colour in the risk palette: 0.25 Moderate yellow, 0.5 High orange, 0.75 Severe
 * red, 1.0 No Travel purple. The low end fades in from transparent so edges feather and even
 * an isolated Moderate cell (~0.09) stays visible.
 */
export const heatmapColor: ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['heatmap-density'],
  0,
  'rgba(0,0,0,0)',
  0.03,
  'rgba(234,179,8,0.45)',
  0.25,
  RISK_COLORS[1],
  0.5,
  RISK_COLORS[2],
  0.75,
  RISK_COLORS[3],
  1,
  RISK_COLORS[4],
]

export function meanLatitude(data: HeatmapResponse): number {
  if (data.points.length === 0) return 0
  return data.points.reduce((sum, [lat]) => sum + lat, 0) / data.points.length
}
