import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

/**
 * MapLibre 6 derives its worker URL from `import.meta.url` at runtime, which breaks once Vite
 * pre-bundles (dev) or bundles (build) the library: the worker file isn't next to the chunk.
 * Pointing it at the worker asset explicitly fixes both. Loaded lazily, as react-map-gl would.
 */
export const maplibrePromise = import('maplibre-gl').then((maplibre) => {
  maplibre.setWorkerUrl(workerUrl)
  return maplibre
})
