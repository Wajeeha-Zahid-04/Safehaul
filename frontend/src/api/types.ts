// Shapes of the SafeHaul API (backend/api). Coordinates in `path`/`bbox` are GeoJSON [lon, lat].

export interface Place {
  label: string
  lat: number
  lon: number
}

export type IntervalMi = 10 | 25 | 50

export interface PlanRequest {
  origin: Place
  destination: Place
  departure: string // ISO 8601 with offset
  load_lb: number
  interval_mi: IntervalMi
}

/** 0 Low, 1 Moderate, 2 High, 3 Severe, 4 No Travel */
export type RiskLevel = 0 | 1 | 2 | 3 | 4

export interface CheckpointResult {
  index: number
  lat: number
  lon: number
  distance_mi: number
  segment_mi: number
  eta: string
  forecast_hour: string
  wind_mph: number
  gust_mph: number
  rain_in: number
  precip_in: number
  snow_in: number
  level: RiskLevel
  level_label: string
  reasons: string[]
  path: [number, number][]
}

export interface RouteResult {
  id: number
  rank: number
  distance_mi: number
  duration_s: number
  notravel_mi: number
  severe_mi: number
  high_mi: number
  avg_score: number
  do_not_travel: boolean
  bbox: [number, number, number, number]
  checkpoints: CheckpointResult[]
}

export interface HeatmapRequest {
  bbox: [number, number, number, number] // [min_lon, min_lat, max_lon, max_lat]
  start: string // ISO 8601
  load_lb: number
}

export interface HeatmapResponse {
  start: string // first hour (UTC, ISO); frame h is start + h hours
  hours: number // 49 (0..48)
  spacing_km: number
  points: [number, number][] // [lat, lon]
  scores: (RiskLevel | null)[][] // scores[hour][point]; null = no forecast
}

export interface PlanResponse {
  recommended_id: number
  recommendation_reason: string
  all_no_travel: boolean
  routes: RouteResult[] // ranked, recommended first
}
