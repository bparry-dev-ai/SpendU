// Full searchable history of spending, refunds and bill payments.
import { CalendarRange, ChevronLeft, ChevronRight, Download, Search, SlidersHorizontal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { get, query } from '../api'
import TransactionList from '../components/TransactionList'
import { Empty, ErrorNote, Money, PageHeader, Segmented, Spinner } from '../components/ui'
import { addDays, fmtDate, money, shiftMonth, shiftRange } from '../format'
import { useApp } from '../state'

function rangeFor(preset, today) {
  const month = today.slice(0, 7)
  switch (preset) {
    case '7_days': return { start: addDays(today, -6), end: today }
    case 'this_month': return { start: `${month}-01`, end: today }
    case 'last_month': {
      const lm = shiftMonth(month, -1)
      return { start: `${lm}-01`, end: addDays(`${month}-01`, -1) }
    }
    case '30_days': return { start: addDays(today, -29), end: today }
    case '90_days': return { start: addDays(today, -89), end: today }
    case 'this_year': return { start: `${today.slice(0, 4)}-01-01`, end: today }
    default: return { start: '', end: '' }
  }
}

const TIME_PRESETS = [
  { value: '7_days', label: 'Last 7 days' },
  { value: 'this_month', label: 'This month' },
  { value: '30_days', label: 'Last 30 days' },
  { value: 'all', label: 'All time' },
  { value: 'custom', label: 'Custom dates' },
]
const CUSTOM_KEY = 'spendu-activity-range'

function readCustom(today) {
  try {
    const saved = JSON.parse(localStorage.getItem(CUSTOM_KEY))
    if (saved?.start && saved?.end) return saved
  } catch { /* private mode or bad data */ }
  return { start: `${today.slice(0, 7)}-01`, end: today }
}

// Pick any date range, e.g. a card statement period (15 Oct – 14 Nov), and
// step it a month at a time to check statement after statement.
function CustomRange({ value, onChange }) {
  const set = (k, v) => onChange({ ...value, [k]: v })
  const valid = value.start && value.end && value.start <= value.end
  return (
    <div className="custom-range card pad">
      <div className="custom-range-fields">
        <label className="field"><span className="field-label">From</span>
          <input className="input" type="date" value={value.start} max={value.end || undefined}
            onChange={(e) => set('start', e.target.value)} /></label>
        <label className="field"><span className="field-label">To</span>
          <input className="input" type="date" value={value.end} min={value.start || undefined}
            onChange={(e) => set('end', e.target.value)} /></label>
      </div>
      {valid && (
        <div className="custom-range-step">
          <button type="button" className="btn small secondary" onClick={() => onChange(shiftRange(value, -1))}>
            <ChevronLeft size={14} /> Month earlier
          </button>
          <span className="muted small"><CalendarRange size={13} /> {fmtDate(value.start, { month: 'short', day: 'numeric', year: 'numeric' })} – {fmtDate(value.end, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
          <button type="button" className="btn small secondary" onClick={() => onChange(shiftRange(value, 1))}>
            Month later <ChevronRight size={14} />
          </button>
        </div>
      )}
      {value.start && value.end && value.start > value.end && <p className="form-error">The start date is after the end date.</p>}
      <p className="muted small">Tip: pick a card under Filters and set these to your statement dates to check the app's total against the statement.</p>
    </div>
  )
}

// What makes up the total: purchases, refunds, bill payments, bill refunds.
function Breakdown({ b }) {
  if (!b) return null
  const parts = [
    { key: 'spending', label: 'Spending', value: b.spending },
    { key: 'refunds', label: 'Refunds', value: -b.refunds },
    { key: 'bills', label: 'Bills', value: b.bills },
    { key: 'bill_refunds', label: 'Bill refunds', value: -b.bill_refunds },
  ].filter((p) => p.value)
  if (parts.length < 2) return null
  return (
    <div className="result-breakdown">
      {parts.map((p) => (
        <span key={p.key} className={p.value < 0 ? 'credit' : ''}>
          {p.label} <strong>{p.value < 0 ? `+${money(-p.value)}` : money(p.value)}</strong>
        </span>
      ))}
    </div>
  )
}

export default function Activity() {
  const { meta, today, version } = useApp()
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [kind, setKind] = useState('all')
  const [cardId, setCardId] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [preset, setPreset] = useState('7_days')
  const [custom, setCustomState] = useState(() => readCustom(today))
  const setCustom = (next) => {
    setCustomState(next)
    try { localStorage.setItem(CUSTOM_KEY, JSON.stringify(next)) } catch { /* private mode */ }
  }
  const [showFilters, setShowFilters] = useState(false)
  const [page, setPage] = useState(1)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 250)
    return () => clearTimeout(t)
  }, [q])

  const range = preset === 'custom' ? custom : rangeFor(preset, today)
  const filters = { q: debouncedQ, kind, card_id: cardId, category_id: categoryId, start: range.start, end: range.end }
  const filterKey = JSON.stringify(filters)

  useEffect(() => { setPage(1) }, [filterKey])

  useEffect(() => {
    let alive = true
    setLoading(true)
    get('/transactions' + query({ ...filters, page, page_size: 50 }))
      .then((r) => {
        if (!alive) return
        setResult((prev) => (page > 1 && prev ? { ...r, items: [...prev.items, ...r.items] } : r))
        setError(null)
      })
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, page, version])

  const activeFilterCount = [cardId, categoryId, preset !== '7_days' ? preset : ''].filter(Boolean).length

  return (
    <div className="page">
      <PageHeader title="Activity" subtitle="Everything you've spent, refunded and paid."
        actions={
          <a className="btn secondary" href={'/api/export.csv' + query(filters)} download>
            <Download size={16} /> Export CSV
          </a>
        } />

      <div className="toolbar">
        <div className="search">
          <Search size={16} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search merchant, category, notes…" />
        </div>
        <button className={`btn secondary ${activeFilterCount ? 'has-dot' : ''}`} onClick={() => setShowFilters((s) => !s)}>
          <SlidersHorizontal size={16} /> Filters{activeFilterCount ? ` (${activeFilterCount})` : ''}
        </button>
      </div>

      <div className="chip-row no-scrollbar">
        {TIME_PRESETS.map((p) => (
          <button
            key={p.value}
            type="button"
            className={`pill ${preset === p.value ? 'on' : ''}`}
            onClick={() => setPreset(p.value)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {preset === 'custom' && <CustomRange value={custom} onChange={setCustom} />}

      <Segmented value={kind} onChange={setKind} size="sm" options={[
        { value: 'all', label: 'All' }, { value: 'spending', label: 'Spending' },
        { value: 'refunds', label: 'Refunds' }, { value: 'bills', label: 'Bills' },
      ]} />

      {showFilters && (
        <div className="filters card pad">
          <label className="field">
            <span className="field-label">Date</span>
            <select className="input" value={preset} onChange={(e) => setPreset(e.target.value)}>
              <option value="7_days">Last 7 days</option>
              <option value="this_month">This month</option>
              <option value="last_month">Last month</option>
              <option value="30_days">Last 30 days</option>
              <option value="90_days">Last 90 days</option>
              <option value="this_year">This year</option>
              <option value="all">All time</option>
              <option value="custom">Custom…</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Card</span>
            <select className="input" value={cardId} onChange={(e) => setCardId(e.target.value)}>
              <option value="">All cards</option>
              {meta.cards.map((c) => <option key={c.card_id} value={c.card_id}>{c.name}{c.archived ? ' (archived)' : ''}</option>)}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Category</span>
            <select className="input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">All categories</option>
              {meta.categories.map((c) => <option key={c.category_id} value={c.category_id}>{c.name}{c.archived ? ' (archived)' : ''}</option>)}
            </select>
          </label>
          {activeFilterCount > 0 && (
            <button className="link" onClick={() => { setCardId(''); setCategoryId(''); setPreset('7_days') }}>Clear filters</button>
          )}
        </div>
      )}

      <ErrorNote error={error} />
      {result && (
        <div className="result-summary">
          <span>{result.count} transaction{result.count === 1 ? '' : 's'}</span>
          <span>Total <Money value={result.total} signed /></span>
        </div>
      )}
      {result && <Breakdown b={result.breakdown} />}

      {!result ? <div className="center-pad"><Spinner /></div> : result.items.length === 0 ? (
        <Empty icon="🔍" title="Nothing found">Try a different search or clear the filters.</Empty>
      ) : (
        <div className="card">
          <TransactionList items={result.items} />
        </div>
      )}

      {result && page < result.pages && (
        <button className="btn secondary block" disabled={loading} onClick={() => setPage((p) => p + 1)}>
          {loading ? 'Loading…' : 'Load more'}
        </button>
      )}
    </div>
  )
}
