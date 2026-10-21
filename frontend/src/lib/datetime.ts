export const MAX_DEPARTURE_AHEAD_MS = 48 * 60 * 60 * 1000
// Mirrors the backend's grace window for a departure of "now".
export const DEPARTURE_GRACE_MS = 5 * 60 * 1000

const pad = (n: number) => String(n).padStart(2, '0')

/** Date -> value for <input type="datetime-local"> in the user's local time zone. */
export function toLocalInputValue(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** <input type="datetime-local"> value (local time) -> Date, or null if empty/invalid. */
export function fromLocalInputValue(value: string): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}
