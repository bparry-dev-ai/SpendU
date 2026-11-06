// Add or edit a spending entry (purchase or refund). The "Bill" tab switches
// to the bill-payment form, so one Add button covers everything.
import { Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { del, get, patch, post, query } from '../api'
import { addDays } from '../format'
import { activeCards, activeCategories, useApp } from '../state'
import { BillPaymentForm } from './BillPaymentSheet'
import { ConfirmButton, Field, Pills, Segmented, Sheet } from './ui'

const LAST_CARD_KEY = 'spendu-last-card'

function readLastCard() {
  try { return Number(localStorage.getItem(LAST_CARD_KEY)) || null } catch { return null }
}

export function QuickAdd({ kind, onCreated }) {
  // Inline "+ New" pill: creates a card/category without leaving the form.
  const { changed, notify } = useApp()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const save = async () => {
    if (!name.trim()) return setOpen(false)
    try {
      const res = await post(`/${kind}`, { name })
      changed()
      onCreated(res.id)
      setName('')
      setOpen(false)
    } catch (e) {
      notify(e.message, 'error')
    }
  }
  if (!open) {
    return (
      <button type="button" className="pill ghost" onClick={() => setOpen(true)}>
        <Plus size={14} /> New
      </button>
    )
  }
  return (
    <span className="pill-input">
      <input autoFocus value={name} maxLength={50} placeholder={kind === 'cards' ? 'Card name' : 'Category name'}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); save() } if (e.key === 'Escape') setOpen(false) }} />
      <button type="button" className="btn small primary" onClick={save}>Add</button>
    </span>
  )
}

function MerchantInput({ value, onChange, onPick, onExact }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const timer = useRef()

  useEffect(() => {
    clearTimeout(timer.current)
    if (!open) return
    timer.current = setTimeout(() => {
      get('/merchants' + query({ q: value })).then((r) => {
        setSuggestions(r.merchants)
        // Typing a known merchant's full name counts the same as picking it from the list.
        const typed = (value || '').trim().toLowerCase()
        const exact = typed && r.merchants.find((s) => s.merchant.toLowerCase() === typed)
        if (exact) onExact(exact)
      }).catch(() => {})
    }, 150)
    return () => clearTimeout(timer.current)
  }, [value, open])

  const shown = suggestions.filter((s) => s.merchant.toLowerCase() !== (value || '').toLowerCase() || !value)
  return (
    <div className="autocomplete">
      <input className="input" value={value} placeholder="Where? e.g. Tesco, Amazon" maxLength={80}
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => onChange(e.target.value)} autoComplete="off" />
      {open && shown.length > 0 && (
        <ul className="autocomplete-list">
          {shown.slice(0, 6).map((s) => (
            <li key={s.merchant}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { onPick(s); setOpen(false) }}>
                {s.merchant} <span className="muted small">· used {s.uses}×</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function TransactionSheet({ entry, onClose }) {
  const { meta, today, changed, notify } = useApp()
  const editing = Boolean(entry)
  const cards = activeCards(meta)
  const categories = activeCategories(meta)

  const [mode, setMode] = useState(entry ? (entry.amount < 0 ? 'refund' : 'purchase') : 'purchase')
  const [form, setForm] = useState(() => ({
    amount: entry ? Math.abs(entry.amount).toFixed(2) : '',
    merchant: entry?.merchant || '',
    category_id: entry?.category_id || null,
    card_id: entry?.card_id || (cards.some((c) => c.card_id === readLastCard()) ? readLastCard() : cards[0]?.card_id) || null,
    date: entry?.date || today,
    notes: entry?.notes || '',
  }))
  const [categoryTouched, setCategoryTouched] = useState(editing)
  const [showNotes, setShowNotes] = useState(Boolean(entry?.notes))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const applyMerchantCategory = (s) => {
    if (!categoryTouched && s.category_id && categories.some((c) => c.category_id === s.category_id)) {
      set('category_id', s.category_id)
    }
  }
  const pickMerchant = (s) => {
    set('merchant', s.merchant)
    applyMerchantCategory(s)
  }

  const save = async (e) => {
    e?.preventDefault()
    setError(null)
    if (!form.amount || Number(form.amount) <= 0) return setError('Enter an amount.')
    if (!form.category_id) return setError('Pick a category.')
    if (!form.card_id) return setError('Pick a card.')
    setSaving(true)
    try {
      const payload = { ...form, is_refund: mode === 'refund' }
      if (editing) await patch(`/spending/${entry.id}`, payload)
      else await post('/spending', payload)
      try { localStorage.setItem(LAST_CARD_KEY, String(form.card_id)) } catch { /* private mode */ }
      changed()
      notify(editing ? 'Saved changes' : mode === 'refund' ? 'Refund added' : 'Spending added')
      onClose()
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  const remove = async () => {
    try {
      await del(`/spending/${entry.id}`)
      changed()
      notify('Transaction deleted')
      onClose()
    } catch (err) {
      setError(err.message)
    }
  }

  if (mode === 'bill') {
    return (
      <Sheet title="Pay a bill" onClose={onClose}>
        <Segmented value={mode} onChange={setMode}
          options={[{ value: 'purchase', label: 'Purchase' }, { value: 'refund', label: 'Refund' }, { value: 'bill', label: 'Bill' }]} />
        <BillPaymentForm onDone={onClose} />
      </Sheet>
    )
  }

  const footer = (
    <>
      {editing && <ConfirmButton onConfirm={remove} />}
      <span className="spacer" />
      <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
      <button type="submit" form="tx-form" className="btn primary" disabled={saving}>
        {saving ? 'Saving…' : editing ? 'Save' : 'Add'}
      </button>
    </>
  )

  return (
    <Sheet title={editing ? 'Edit transaction' : 'Add transaction'} onClose={onClose} footer={footer}>
      <form id="tx-form" onSubmit={save} className="stack">
        {!editing ? (
          <Segmented value={mode} onChange={setMode}
            options={[{ value: 'purchase', label: 'Purchase' }, { value: 'refund', label: 'Refund' }, { value: 'bill', label: 'Bill' }]} />
        ) : (
          <Segmented value={mode} onChange={setMode}
            options={[{ value: 'purchase', label: 'Purchase' }, { value: 'refund', label: 'Refund / credit' }]} />
        )}

        <div className={`amount-input ${mode === 'refund' ? 'credit' : ''}`}>
          <span>{mode === 'refund' ? '+$' : '$'}</span>
          <input inputMode="decimal" type="number" step="0.01" min="0" placeholder="0.00" autoFocus={!editing}
            value={form.amount} onChange={(e) => set('amount', e.target.value)} aria-label="Amount" />
        </div>

        <Field label="Merchant">
          <MerchantInput value={form.merchant} onChange={(v) => set('merchant', v)} onPick={pickMerchant} onExact={applyMerchantCategory} />
        </Field>

        <Field label="Category">
          {categories.length === 0 && <p className="muted small">No categories yet — add your first one.</p>}
          <Pills items={categories} value={form.category_id} getKey={(c) => c.category_id}
            getLabel={(c) => (c.icon ? `${c.icon} ${c.name}` : c.name)} getColor={(c) => c.color}
            onChange={(id) => { set('category_id', id); setCategoryTouched(true) }}
            extra={<QuickAdd kind="categories" onCreated={(id) => { set('category_id', id); setCategoryTouched(true) }} />} />
        </Field>

        <Field label="Card">
          <Pills items={cards} value={form.card_id} getKey={(c) => c.card_id} getLabel={(c) => c.name}
            getColor={(c) => c.color} onChange={(id) => set('card_id', id)}
            extra={<QuickAdd kind="cards" onCreated={(id) => set('card_id', id)} />} />
        </Field>

        <Field label="Date">
          <div className="row wrap">
            <input className="input date" type="date" value={form.date} onChange={(e) => set('date', e.target.value)} required />
            <button type="button" className={`pill ${form.date === today ? 'on' : ''}`} onClick={() => set('date', today)}>Today</button>
            <button type="button" className={`pill ${form.date === addDays(today, -1) ? 'on' : ''}`}
              onClick={() => set('date', addDays(today, -1))}>Yesterday</button>
          </div>
        </Field>

        {showNotes ? (
          <Field label="Notes">
            <textarea className="input" rows={2} maxLength={500} value={form.notes}
              onChange={(e) => set('notes', e.target.value)} placeholder="Anything to remember" />
          </Field>
        ) : (
          <button type="button" className="link left" onClick={() => setShowNotes(true)}>+ Add a note</button>
        )}

        {error && <p className="form-error">{error}</p>}
      </form>
    </Sheet>
  )
}
