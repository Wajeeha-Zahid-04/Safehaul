const etaFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

/** ISO timestamp -> short local time, e.g. "Thu 14:05". */
export function formatEta(iso: string): string {
  return etaFormat.format(new Date(iso))
}
