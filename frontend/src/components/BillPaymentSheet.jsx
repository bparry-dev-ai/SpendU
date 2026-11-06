// Record (or edit) a bill payment. Opened from the Bills checklist's
// "Mark paid" button with the bill, amount and card already filled in.
import { useState } from 'react'
import { del, patch, post } from '../api'
import { monthLabel, shiftMonth } from '../format'
import { activeCards, useApp } from '../state'
import { QuickAdd } from './TransactionSheet'
import { ConfirmButton, Field, Pills, Sheet } from './ui'

export function BillPaymentForm({ bill, payment, month, onDone }) {
  const { meta, today, changed, notify } = useApp()
  const cards = activeCards(meta)
  const bills = meta.bills.filter((b) => b.active || b.bill_id === (payment?.bill_id ?? bill?.bill_id))
  const editing = Boolean(payment)
  const defaultMonth = month || today.slice(0, 7)

  const [form, setForm] = useState(() => ({
    bill_id: payment?.bill_id ?? bill?.bill_id ?? '',
    amount: payment ? payment.amount.toFixed(2) : bill?.expected ? Number(bill.expected).toFixed(2) : '',
    card_id: payment?.card_id ?? (cards.some((c) => c.card_id === bill?.card_id) ? bill.card_id : cards[0]?.card_id) ?? null,
    date: payment?.date || today,
    bill_month: payment?.bill_month || defaultMonth,
    notes: payment?.notes || '',
  }))
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const pickBill = (id) => {
    const b = meta.bills.find((x) => x.bill_id === Number(id))
    setForm((f) => ({
      ...f,
      bill_id: Number(id),
      amount: f.amount || (b?.amount ? Number(b.amount).toFixed(2) : ''),
      card_id: cards.some((c) => c.card_id === b?.card_id) ? b.card_id : f.card_id,
    }))
  }

  const save = async (e) => {
    e.preventDefault()
    setError(null)
    if (!form.bill_id) return setError('Pick which bill.')
    if (!form.amount || Number(form.amount) <= 0) return setError('Enter an amount.')
    if (!form.card_id) return setError('Pick a card.')
    setSaving(true)
    try {
      if (editing) await patch(`/bill-payments/${payment.id}`, form)
      else await post('/bill-payments', form)
      changed()
      notify(editing ? 'Payment updated' : 'Bill marked as paid')
      onDone()
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  const remove = async () => {
    await del(`/bill-payments/${payment.id}`)
    changed()
    notify('Payment removed — bill is unpaid again')
    onDone()
  }

  const monthOptions = [-2, -1, 0, 1].map((d) => shiftMonth(defaultMonth, d))
  if (!monthOptions.includes(form.bill_month)) monthOptions.unshift(form.bill_month)

  return (
    <form onSubmit={save} className="stack">
      {!bill && (
        <Field label="Bill">
          {bills.length === 0 ? (
            <p className="muted small">No bills yet — set them up on the Bills page.</p>
          ) : (
            <select className="input" value={form.bill_id} onChange={(e) => pickBill(e.target.value)}>
              <option value="">Choose a bill…</option>
              {bills.map((b) => <option key={b.bill_id} value={b.bill_id}>{b.name}</option>)}
            </select>
          )}
        </Field>
      )}

      <div className="amount-input">
        <span>$</span>
        <input inputMode="decimal" type="number" step="0.01" min="0" placeholder="0.00" value={form.amount}
          onChange={(e) => set('amount', e.target.value)} aria-label="Amount" autoFocus={!bill} />
      </div>

      <Field label="Paid with">
        <Pills items={cards} value={form.card_id} getKey={(c) => c.card_id} getLabel={(c) => c.name}
          getColor={(c) => c.color} onChange={(id) => set('card_id', id)}
          extra={<QuickAdd kind="cards" onCreated={(id) => set('card_id', id)} />} />
      </Field>

      <div className="grid-2">
        <Field label="Date paid">
          <input className="input" type="date" value={form.date} onChange={(e) => set('date', e.target.value)} required />
        </Field>
        <Field label="For which month">
          <select className="input" value={form.bill_month} onChange={(e) => set('bill_month', e.target.value)}>
            {monthOptions.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
          </select>
        </Field>
      </div>

      <Field label="Notes">
        <input className="input" value={form.notes} maxLength={300} placeholder="Optional, e.g. confirmation number"
          onChange={(e) => set('notes', e.target.value)} />
      </Field>

      {error && <p className="form-error">{error}</p>}
      <div className="row">
        {editing && <ConfirmButton onConfirm={remove}>Remove payment</ConfirmButton>}
        <span className="spacer" />
        <button type="submit" className="btn primary" disabled={saving}>
          {saving ? 'Saving…' : editing ? 'Save' : 'Mark paid'}
        </button>
      </div>
    </form>
  )
}

export default function BillPaymentSheet({ bill, payment, month, onClose }) {
  const title = payment ? 'Edit payment' : bill ? `Pay ${bill.name}` : 'Pay a bill'
  return (
    <Sheet title={title} onClose={onClose}>
      <BillPaymentForm bill={bill} payment={payment} month={month} onDone={onClose} />
    </Sheet>
  )
}
