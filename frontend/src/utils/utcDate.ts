/** UTC calendar date, shifted by whole days, as YYYY-MM-DD. */
export function utcIsoDate(offsetDays = 0): string {
  const now = new Date()
  const utc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + offsetDays))
  return utc.toISOString().slice(0, 10)
}
