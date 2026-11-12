// The "Subscription" tab of Add transaction: log a charge for one of your
// subscriptions (due ones first), or set up a new subscription while logging
// its first charge, without leaving the screen.
import { useState } from 'react'
import { post } from '../api'
import { fmtDate, money, toDate } from '../format'
import { activeCards, activeCategories, useApp } from '../state'
import { QuickAdd } from './TransactionSheet'
import { Field, Pills, Segmented } from './ui'

const FREQ = { weekly: 'Weekly', monthly: 'Monthly', yearly: 'Yearly' }
const PERIOD_DAYS = { weekly: 7, monthly: 30, yearly: 365 }
const NEW = 'new'

const daysBetween = (a, b) => Math.round((toDate(a) - toDate(b)) / 86400000)

// Same rule as the server (counts_as_next in recurring.py): a charge on or
// after the due date, or up to half a period early, is the upcoming one.
const countsAsNext = (sub, date) => daysBetween(sub.next_date, date) <= Math.floor(PERIOD_DAYS[sub.frequency] / 2)

// Due ones first (oldest first), then the rest by name.
const sortSubs = (subs) => [...subs].sort((a, b) =>
  (b.pending - a.pending) || (a.pending ? a.next_date.localeCompare(b.next_date) : a.name.localeCompare(b.name)))

export default function SubscriptionChargeForm({ subs, initial, onDone }) {
  const { meta, today, changed, notify } = useApp()
  const cards = activeCards(meta)
  const categories = activeCategories(meta)
  const list = sortSubs(subs)
  const validCard = (id) => (cards.some((c) => c.card_id === id) ? id : null)

  const [choice, setChoice] = useState(initial.recurring_id ?? (list.length ? null : NEW))
  const [form, setForm] = useState(() => {
    const sub = list.find((s) => s.recurring_id === initial.recurring_id)
    return {
      amount: initial.amount || (sub ? Number(sub.amount).toFixed(2) : ''),
      date: initial.date || (sub?.pending ? sub.next_date : today),
      card_id: initial.card_id ?? validCard(sub?.card_id) ?? cards[0]?.card_id ?? null,
      name: initial.merchant || '',
      frequency: 'monthly',
      category_id: initial.category_id ?? null,
      update_amount: false,
    }
  })
  const [dateTouched, setDateTouched] = useState(Boolean(initial.date))
  const [amountTouched, setAmountTouched] = useState(Boolean(initial.amount))
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const sub = list.find((s) => s.recurring_id === choice)

  const pick = (id) => {
    setChoice(id)
    setError(null)
    const s = list.find((x) => x.recurring_id === id)
    if (!s) return
    setForm((f) => ({
      ...f,
      amount: amountTouched && f.amount ? f.amount : Number(s.amount).toFixed(2),
      date: dateTouched ? f.date : s.pending ? s.next_date : today,
      card_id: validCard(s.card_id) ?? f.card_id,
      update_amount: false,
    }))
  }

  const amountChanged = sub && form.amount && Math.abs(Number(form.amount) - sub.amount) > 0.004
  const duplicate = sub?.last_charge && form.date &&
    Math.abs(daysBetween(form.date, sub.last_charge)) <= (sub.frequency === 'weekly' ? 2 : 5)

  const save = async (e) => {
    e.preventDefault()
    setError(null)
    if (!choice) return setError('Pick a subscription, or + New.')
    if (!form.amount || Number(form.amount) <= 0) return setError('Enter an amount.')
    if (!form.card_id) return setError('Pick a card.')
    if (!form.date) return setError('Pick the date of the charge.')
    if (choice === NEW) {
      if (!form.name.trim()) return setError('Give the subscription a name.')
      if (!form.category_id) return setError('Pick a category.')
    }
    setSaving(true)
    try {
      if (choice === NEW) {
        const res = await post('/recurring', {
          name: form.name, amount: form.amount, frequency: form.frequency, category_id: form.category_id,
          card_id: form.card_id, next_date: form.date, log_charge: true,
        })
        const created = res.items.reduce((a, b) => (b.recurring_id > (a?.recurring_id ?? 0) ? b : a), null)
        notify(`${form.name.trim()} added to subscriptions · next charge ${fmtDate(created.next_date)}`)
      } else {
        const res = await post(`/recurring/${sub.recurring_id}/charge`, {
          amount: form.amount, date: form.date, card_id: form.card_id, update_amount: form.update_amount,
        })
        notify(res.moved ? `${sub.name} logged · next charge ${fmtDate(res.next_date)}` : `${sub.name} logged`)
      }
      try { localStorage.setItem('spendu-last-card', String(form.card_id)) } catch { /* private mode */ }
      changed()
      onDone()
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save} className="stack">
      <Field label="Subscription">
        <Pills items={list} value={choice} getKey={(s) => s.recurring_id} getColor={(s) => s.category_color}
          getLabel={(s) => <>{s.name}{s.pending && <span className="pill-tag">due</span>}</>}
          onChange={pick}
          extra={
            <button type="button" className={`pill ghost ${choice === NEW ? 'on' : ''}`} onClick={() => { setChoice(NEW); setError(null) }}>
              + New subscription
            </button>
          } />
        {sub && (
          <span className="field-hint">
            Usually {money(sub.amount)} {FREQ[sub.frequency].toLowerCase()} · next charge {fmtDate(sub.next_date)}
            {sub.last_charge && <> · last logged {fmtDate(sub.last_charge)}</>}
          </span>
        )}
      </Field>

      {choice && (
        <>
          <div className="amount-input">
            <span>$</span>
            <input inputMode="decimal" type="number" step="0.01" min="0" placeholder="0.00" value={form.amount}
              onChange={(e) => { set('amount', e.target.value); setAmountTouched(true) }} aria-label="Amount" />
          </div>

          {choice === NEW && (
            <>
              <Field label="Name">
                <input className="input" value={form.name} maxLength={80} placeholder="e.g. Netflix, Spotify, Gym"
                  onChange={(e) => set('name', e.target.value)} />
              </Field>
              <Field label="How often">
                <Segmented value={form.frequency} onChange={(v) => set('frequency', v)}
                  options={Object.entries(FREQ).map(([value, label]) => ({ value, label }))} />
              </Field>
              <Field label="Category">
                <Pills items={categories} value={form.category_id} getKey={(c) => c.category_id}
                  getLabel={(c) => (c.icon ? `${c.icon} ${c.name}` : c.name)} getColor={(c) => c.color}
                  onChange={(id) => set('category_id', id)}
                  extra={<QuickAdd kind="categories" onCreated={(id) => set('category_id', id)} />} />
              </Field>
            </>
          )}

          <Field label="Card" hint={sub && form.card_id !== sub.card_id ? `${sub.name} will use this card from now on.` : undefined}>
            <Pills items={cards} value={form.card_id} getKey={(c) => c.card_id} getLabel={(c) => c.name}
              getColor={(c) => c.color} onChange={(id) => set('card_id', id)}
              extra={<QuickAdd kind="cards" onCreated={(id) => set('card_id', id)} />} />
          </Field>

          <Field label="Date of the charge">
            <div className="row wrap">
              <input className="input date" type="date" value={form.date} required
                onChange={(e) => { set('date', e.target.value); setDateTouched(true) }} />
              <button type="button" className={`pill ${form.date === today ? 'on' : ''}`}
                onClick={() => { set('date', today); setDateTouched(true) }}>Today</button>
            </div>
          </Field>

          {amountChanged && (
            <label className="check">
              <input type="checkbox" checked={form.update_amount} onChange={(e) => set('update_amount', e.target.checked)} />
              Price changed: make {money(Number(form.amount))} the usual amount
            </label>
          )}

          {sub && form.date && (duplicate ? (
            <p className="notice warn">
              {sub.name} was already logged on {fmtDate(sub.last_charge)}. Only add this if it's a separate charge.
            </p>
          ) : countsAsNext(sub, form.date) ? (
            <p className="notice">This is the {fmtDate(sub.next_date)} charge, so the next one moves on a {sub.frequency === 'weekly' ? 'week' : sub.frequency === 'yearly' ? 'year' : 'month'}.</p>
          ) : (
            <p className="notice">An earlier charge: the next charge stays {fmtDate(sub.next_date)}.</p>
          ))}
          {choice === NEW && (
            <p className="notice">Logs this charge now and adds {form.name.trim() || 'it'} to Subscriptions, so you're reminded when the next one is due.</p>
          )}
        </>
      )}

      {error && <p className="form-error">{error}</p>}
      <div className="row">
        <span className="spacer" />
        <button type="button" className="btn ghost" onClick={onDone}>Cancel</button>
        <button type="submit" className="btn primary" disabled={saving || !choice}>
          {saving ? 'Saving…' : choice === NEW ? 'Add & log' : 'Log charge'}
        </button>
      </div>
    </form>
  )
}
