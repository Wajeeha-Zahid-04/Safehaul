// `||` (not `??`) so an empty value copied from .env.example falls back to the default.
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Free, keyless vector basemap (OpenFreeMap). Override with any MapLibre style URL.
export const MAP_STYLE_URL: string =
  import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/positron'
