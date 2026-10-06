/** Display-only date formatting for the Lead Gen / criteria pages (UK style). */

const DAY = { day: 'numeric', month: 'short', year: 'numeric' }
const TIME = { hour: '2-digit', minute: '2-digit' }

/** "6 Oct 2026" */
export function formatDay(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-GB', DAY)
}

/** "6 Oct 2026 at 01:41" */
export function formatDayTime(iso, joiner = ' at ') {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.toLocaleDateString('en-GB', DAY)}${joiner}${d.toLocaleTimeString('en-GB', TIME)}`
}

/** "2026-10-06" (a London calendar date from the API) -> "6 Oct 2026" without timezone drift. */
export function formatIsoDate(ymd) {
  if (!ymd) return ''
  const [y, m, d] = ymd.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-GB', { ...DAY, timeZone: 'UTC' })
}
