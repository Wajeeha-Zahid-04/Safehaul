const etaFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

/** ISO timestamp -> short local time, e.g. "Thu 14:05". */
export function formatEta(iso: string): string {
  return etaFormat.format(new Date(iso))
}

/** Seconds -> "4 h 37 min" / "52 min". */
export function formatDuration(seconds: number): string {
  const totalMin = Math.round(seconds / 60)
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return h > 0 ? `${h} h ${m} min` : `${m} min`
}

/** Stable display name per route id: 0 -> "Route A". */
export function routeName(id: number): string {
  return `Route ${String.fromCharCode(65 + id)}`
}
