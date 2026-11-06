// CSV import: upload a statement → review every row → save the ones you keep.
import { CheckCircle2, FileUp, RefreshCw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api, post } from '../api'
import { Badge, Card, Empty, Field, Money, PageHeader, Pills } from '../components/ui'
import { fmtDate } from '../format'
import { activeCards, activeCategories, useApp } from '../state'

const STATUS = {
  new: null,
  duplicate: { tone: 'neutral', label: 'Already imported' },
  possible_duplicate: { tone: 'warn', label: 'Possible duplicate' },
}
const KIND = {
  payment: { tone: 'neutral', label: 'Card payment' },
  income: { tone: 'neutral', label: 'Money in' },
  refund: { tone: 'ok', label: 'Refund' },
}
const MAP_FIELDS = [
  ['date', 'Date'], ['description', 'Description / merchant'], ['amount', 'Amount'],
  ['debit', 'Debit (money out)'], ['credit', 'Credit (money in)'], ['indicator', 'Credit/debit indicator'], ['category', 'Bank category'],
]

export default function Import() {
  const { meta, changed, notify } = useApp()
  const cards = activeCards(meta)
  const categories = activeCategories(meta)
  const [pickedCard, setCardId] = useState(null)
  const cardId = pickedCard ?? cards[0]?.card_id ?? null
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(null)
  const [showMapping, setShowMapping] = useState(false)

  const runPreview = async (overrides = {}) => {
    if (!file || !cardId) return
    setBusy(true)
    setError(null)
    const form = new FormData()
    form.append('file', file)
    form.append('card_id', cardId)
    if (overrides.preset) form.append('preset', overrides.preset)
    else if (preview?.preset) form.append('preset', preview.preset)
    if (overrides.mapping) form.append('mapping', JSON.stringify(overrides.mapping))
    if (overrides.flip) form.append('flip', '1')
    try {
      const res = await api('/import/preview', { method: 'POST', form })
      setPreview(res)
      setRows(res.rows)
      setDone(null)
      if (res.problems.length) setShowMapping(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const update = (i, changes) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...changes } : r)))
  const included = rows.filter((r) => r.include)
  const missingCategory = included.filter((r) => !r.category_id).length
  const total = useMemo(() => included.reduce((s, r) => s + r.amount, 0), [included])

  const setAllUncategorized = (categoryId) => {
    setRows((rs) => rs.map((r) => (r.include && !r.category_id ? { ...r, category_id: Number(categoryId) } : r)))
  }

  const commit = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await post('/import/commit', { card_id: cardId, rows: included, preset: preview.preset, mapping: preview.mapping })
      setDone(res.imported)
      setPreview(null)
      setRows([])
      setFile(null)
      changed()
      notify(`Imported ${res.imported} transactions`)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <PageHeader title="Import CSV" subtitle="Download a statement from your bank's website as CSV and bring it in here." />

      {done !== null && (
        <Card className="success">
          <CheckCircle2 size={22} /> Imported {done} transaction{done === 1 ? '' : 's'}. A backup was taken first, just in case.
        </Card>
      )}

      <Card title="1. Choose the card and file">
        {cards.length === 0 ? <p className="muted">Add a card first (Settings → Cards).</p> : (
          <div className="stack">
            <Field label="Which card is this statement for?">
              <Pills items={cards} value={cardId} getKey={(c) => c.card_id} getLabel={(c) => c.name} getColor={(c) => c.color}
                onChange={(id) => { setCardId(id); setPreview(null) }} />
            </Field>
            <label className="file-drop">
              <FileUp size={22} />
              <span>{file ? file.name : 'Tap to choose a .csv file'}</span>
              <input type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files[0] || null); setPreview(null) }} />
            </label>
            <button className="btn primary" disabled={!file || !cardId || busy} onClick={() => runPreview()}>
              {busy ? 'Reading…' : 'Preview import'}
            </button>
          </div>
        )}
      </Card>

      {error && <p className="form-error">{error}</p>}

      {preview && (
        <>
          <Card title="2. Check the format" action={<button className="link" onClick={() => setShowMapping((s) => !s)}>{showMapping ? 'Hide columns' : 'Adjust columns'}</button>}>
            <div className="row wrap gap">
              <Field label="Bank format">
                <select className="input auto" value={preview.preset} onChange={(e) => runPreview({ preset: e.target.value })}>
                  {preview.presets.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                </select>
              </Field>
              <button className="btn secondary" onClick={() => runPreview({ mapping: preview.mapping, flip: true })} disabled={busy}>
                <RefreshCw size={14} /> Purchases showing as refunds? Flip signs
              </button>
            </div>
            {preview.problems.map((p) => <p key={p} className="form-error">{p}</p>)}
            {showMapping && (
              <div className="mapping">
                {MAP_FIELDS.map(([key, label]) => (
                  <Field key={key} label={label}>
                    <select className="input" value={preview.mapping[key] || ''}
                      onChange={(e) => setPreview({ ...preview, mapping: { ...preview.mapping, [key]: e.target.value || null } })}>
                      <option value="">—</option>
                      {preview.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </Field>
                ))}
                <button className="btn secondary" onClick={() => runPreview({ mapping: preview.mapping })}>Apply columns</button>
              </div>
            )}
          </Card>

          {rows.length === 0 ? <Empty title="No transactions found in that file" /> : (
            <Card title={`3. Review ${rows.length} rows`} pad={false}>
              <div className="import-tools">
                <span className="muted small">Card payments, money-in and duplicates are unticked. Tick anything you want to keep.</span>
                {missingCategory > 0 && (
                  <select className="input auto" value="" onChange={(e) => setAllUncategorized(e.target.value)}>
                    <option value="">Set category for {missingCategory} uncategorised…</option>
                    {categories.map((c) => <option key={c.category_id} value={c.category_id}>{c.name}</option>)}
                  </select>
                )}
              </div>
              <div className="import-rows">
                {rows.map((r, i) => (
                  <div key={r.row} className={`import-row ${r.include ? '' : 'off'}`}>
                    <input type="checkbox" checked={r.include} onChange={(e) => update(i, { include: e.target.checked })} aria-label="Include" />
                    <span className="import-date">{fmtDate(r.date)}</span>
                    <input className="input slim" value={r.merchant || ''} onChange={(e) => update(i, { merchant: e.target.value })} />
                    <select className={`input slim ${r.include && !r.category_id ? 'needs' : ''}`} value={r.category_id || ''}
                      onChange={(e) => update(i, { category_id: Number(e.target.value) || null })}>
                      <option value="">Category…</option>
                      {categories.map((c) => <option key={c.category_id} value={c.category_id}>{c.name}</option>)}
                    </select>
                    <span className="import-badges">
                      {STATUS[r.status] && <Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge>}
                      {KIND[r.kind] && <Badge tone={KIND[r.kind].tone}>{KIND[r.kind].label}</Badge>}
                    </span>
                    <Money value={r.amount} signed className="import-amt" />
                  </div>
                ))}
              </div>
              <div className="import-foot">
                <span>{included.length} selected · <Money value={total} signed /></span>
                {missingCategory > 0 && <span className="form-error">{missingCategory} still need a category</span>}
                <button className="btn primary" disabled={busy || included.length === 0 || missingCategory > 0} onClick={commit}>
                  {busy ? 'Importing…' : `Import ${included.length}`}
                </button>
              </div>
            </Card>
          )}
        </>
      )}

      <Card title="Supported banks">
        <p className="muted small">
          Presets for <strong>Apple Card</strong>, <strong>American Express</strong>, <strong>Navy Federal</strong> and <strong>Keesler Federal</strong>.
          The format is detected automatically and remembered per card. If your file looks wrong, use <em>Adjust columns</em> to pick them yourself.
        </p>
      </Card>
    </div>
  )
}
