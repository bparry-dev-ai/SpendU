// Full searchable history of spending, refunds and bill payments.
import { Download, Search, SlidersHorizontal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { get, query } from '../api'
import TransactionList from '../components/TransactionList'
import { Empty, ErrorNote, Money, PageHeader, Segmented, Spinner } from '../components/ui'
import { addDays, shiftMonth } from '../format'
import { useApp } from '../state'

function rangeFor(preset, today) {
  const month = today.slice(0, 7)
  switch (preset) {
    case 'this_month': return { start: `${month}-01`, end: today }
    case 'last_month': {
      const lm = shiftMonth(month, -1)
      return { start: `${lm}-01`, end: addDays(`${month}-01`, -1) }
    }
    case '90_days': return { start: addDays(today, -89), end: today }
    case 'this_year': return { start: `${today.slice(0, 4)}-01-01`, end: today }
    default: return { start: '', end: '' }
  }
}

export default function Activity() {
  const { meta, today, version } = useApp()
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [kind, setKind] = useState('all')
  const [cardId, setCardId] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [preset, setPreset] = useState('all')
  const [custom, setCustom] = useState({ start: '', end: '' })
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

  const activeFilterCount = [cardId, categoryId, preset !== 'all' ? preset : ''].filter(Boolean).length

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

      <Segmented value={kind} onChange={setKind} size="sm" options={[
        { value: 'all', label: 'All' }, { value: 'spending', label: 'Spending' },
        { value: 'refunds', label: 'Refunds' }, { value: 'bills', label: 'Bills' },
      ]} />

      {showFilters && (
        <div className="filters card pad">
          <label className="field">
            <span className="field-label">Date</span>
            <select className="input" value={preset} onChange={(e) => setPreset(e.target.value)}>
              <option value="all">All time</option>
              <option value="this_month">This month</option>
              <option value="last_month">Last month</option>
              <option value="90_days">Last 90 days</option>
              <option value="this_year">This year</option>
              <option value="custom">Custom…</option>
            </select>
          </label>
          {preset === 'custom' && (
            <>
              <label className="field"><span className="field-label">From</span>
                <input className="input" type="date" value={custom.start} onChange={(e) => setCustom({ ...custom, start: e.target.value })} /></label>
              <label className="field"><span className="field-label">To</span>
                <input className="input" type="date" value={custom.end} onChange={(e) => setCustom({ ...custom, end: e.target.value })} /></label>
            </>
          )}
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
            <button className="link" onClick={() => { setCardId(''); setCategoryId(''); setPreset('all') }}>Clear filters</button>
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
