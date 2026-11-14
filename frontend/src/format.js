// Formatting helpers. Dates travel as 'YYYY-MM-DD' strings and are parsed as
// local calendar dates (never through UTC, which can shift them a day).

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const usdWhole = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export const money = (n) => usd.format(n || 0)
export const moneyShort = (n) => (Math.abs(n) >= 1000 ? usdWhole.format(n || 0) : usd.format(n || 0))

export function toDate(s) {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d || 1)
}

export function isoDate(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export const fmtDate = (s, opts = { month: 'short', day: 'numeric' }) => toDate(s).toLocaleDateString('en-US', opts)
export const fmtDateLong = (s) => toDate(s).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
export const monthLabel = (ym, short = false) =>
  toDate(ym + '-01').toLocaleDateString('en-US', { month: short ? 'short' : 'long', year: 'numeric' })
export const monthName = (ym) => toDate(ym + '-01').toLocaleDateString('en-US', { month: 'long' })

export function shiftMonth(ym, delta) {
  const d = toDate(ym + '-01')
  d.setMonth(d.getMonth() + delta)
  return isoDate(d).slice(0, 7)
}

// Move a date by whole months, keeping the day (clamped to the month's last day).
export function shiftDate(s, months) {
  const [y, m, d] = s.split('-').map(Number)
  const last = new Date(y, m - 1 + months + 1, 0).getDate()
  return isoDate(new Date(y, m - 1 + months, Math.min(d, last)))
}

// Move a date range (e.g. a card statement period) by whole months.
// The end moves as "the day before the next start", so 1–31 Oct becomes
// 1–30 Nov and then 1–31 Dec, and 15 Oct–14 Nov becomes 15 Nov–14 Dec.
export function shiftRange({ start, end }, months) {
  return { start: shiftDate(start, months), end: addDays(shiftDate(addDays(end, 1), months), -1) }
}

export function addDays(s, n) {
  const d = toDate(s)
  d.setDate(d.getDate() + n)
  return isoDate(d)
}

export function relativeDay(s, today) {
  if (s === today) return 'Today'
  if (s === addDays(today, -1)) return 'Yesterday'
  if (s === addDays(today, 1)) return 'Tomorrow'
  const sameYear = s.slice(0, 4) === today.slice(0, 4)
  return fmtDate(s, sameYear ? { weekday: 'short', month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' })
}

export function daysUntil(s, today) {
  return Math.round((toDate(s) - toDate(today)) / 86400000)
}

export const pct = (x) => `${Math.round((x || 0) * 100)}%`

export const ordinal = (n) => {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December']
