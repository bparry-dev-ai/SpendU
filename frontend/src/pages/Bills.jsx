// Monthly bills checklist + managing the bills themselves.
import { CheckCircle2, Pencil, Plus, Zap } from 'lucide-react'
import { useState } from 'react'
import { del, patch, post } from '../api'
import {
  Badge, Card, ConfirmButton, Empty, ErrorNote, Field, Money, MonthSwitcher, PageHeader, Pills, Progress, Segmented,
  Sheet, Spinner,
} from '../components/ui'
import { daysUntil, fmtDate, money, MONTHS, ordinal } from '../format'
import { activeCards, useApp, useFetch } from '../state'

const STATUS = {
  paid: { tone: 'ok', label: 'Paid' },
  overdue: { tone: 'bad', label: 'Overdue' },
  due_soon: { tone: 'warn', label: 'Due soon' },
  upcoming: { tone: 'neutral', label: 'Upcoming' },
}

export function BillStatus({ status }) {
  const s = STATUS[status] || STATUS.upcoming
  return <Badge tone={s.tone}>{s.label}</Badge>
}

function dueText(item, today) {
  if (item.status === 'paid') return `Due ${fmtDate(item.due_date)}`
  const d = daysUntil(item.due_date, today)
  if (d === 0) return 'Due today'
  if (d === 1) return 'Due tomorrow'
  if (d < 0) return `${-d} day${d === -1 ? '' : 's'} overdue`
  return `Due ${fmtDate(item.due_date)} · in ${d} days`
}

function ChecklistRow({ item, month }) {
  const { openSheet, today, family } = useApp()
  const paid = item.status === 'paid'
  return (
    <div className={`check-row ${item.status}`}>
      <span className={`check-mark ${paid ? 'on' : ''}`}>{paid && <CheckCircle2 size={22} />}</span>
      <div className="tx-main">
        <span className="tx-title">
          {item.name}
          {item.autopay ? <span className="tag"><Zap size={11} /> Autopay</span> : null}
        </span>
        <span className="tx-detail">
          {dueText(item, today)}
          {paid && item.payments.map((p) => (
            <span key={p.id}> · paid {fmtDate(p.date)}{family.length > 1 ? ` by ${p.is_mine ? 'you' : p.username}` : ''}{p.card ? ` (${p.card})` : ''}</span>
          ))}
        </span>
      </div>
      <div className="check-right">
        <Money value={paid ? item.paid_total : item.expected || 0} />
        {paid ? (
          item.payments.filter((p) => p.is_mine).slice(0, 1).map((p) => (
            <button key={p.id} className="link small" onClick={() => openSheet({ type: 'bill-payment', payment: { ...p, bill_id: item.bill_id, bill_month: month } })}>Edit</button>
          ))
        ) : (
          <button className="btn small primary" onClick={() => openSheet({ type: 'bill-payment', bill: item, month })}>Mark paid</button>
        )}
      </div>
    </div>
  )
}

function BillEditor({ bill, onClose }) {
  const { meta, changed, notify } = useApp()
  const cards = activeCards(meta)
  const editing = Boolean(bill)
  const [form, setForm] = useState({
    name: bill?.name || '',
    amount: bill?.amount ?? '',
    frequency: bill?.frequency || 'monthly',
    due_day: bill?.due_day ?? '',
    due_month: bill?.due_month ?? '',
    card_id: bill?.card_id ?? null,
    autopay: Boolean(bill?.autopay),
    notes: bill?.notes || '',
  })
  const [error, setError] = useState(null)
  const history = useFetch(editing ? `/bills/${bill.bill_id}/payments` : null)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const save = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const payload = { ...form, due_month: form.frequency === 'yearly' ? form.due_month : null }
      if (editing) await patch(`/bills/${bill.bill_id}`, payload)
      else await post('/bills', payload)
      changed()
      notify(editing ? 'Bill updated' : 'Bill added')
      onClose()
    } catch (err) {
      setError(err.message)
    }
  }
  const remove = async () => {
    const res = await del(`/bills/${bill.bill_id}`)
    changed()
    notify(res.message)
    onClose()
  }
  const restore = async () => {
    await patch(`/bills/${bill.bill_id}`, { active: true })
    changed()
    notify('Bill restored')
    onClose()
  }

  return (
    <Sheet title={editing ? `Edit ${bill.name}` : 'New bill'} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <Field label="Name"><input className="input" value={form.name} maxLength={60} placeholder="e.g. Rent, Phone, Car insurance" onChange={(e) => set('name', e.target.value)} required /></Field>
        <div className="grid-2">
          <Field label="Usual amount" hint="Pre-fills when you mark it paid">
            <input className="input" type="number" inputMode="decimal" step="0.01" value={form.amount} onChange={(e) => set('amount', e.target.value)} placeholder="0.00" />
          </Field>
          <Field label="How often">
            <Segmented value={form.frequency} onChange={(v) => set('frequency', v)} options={[{ value: 'monthly', label: 'Monthly' }, { value: 'yearly', label: 'Yearly' }]} />
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Due day of month" hint="Leave empty to not track it on the checklist">
            <select className="input" value={form.due_day} onChange={(e) => set('due_day', e.target.value)}>
              <option value="">Not scheduled</option>
              {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{ordinal(d)}</option>)}
            </select>
          </Field>
          {form.frequency === 'yearly' && (
            <Field label="Due month">
              <select className="input" value={form.due_month} onChange={(e) => set('due_month', e.target.value)} required>
                <option value="">Choose…</option>
                {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select>
            </Field>
          )}
        </div>
        <Field label="Usually paid with">
          <Pills items={cards} value={form.card_id} getKey={(c) => c.card_id} getLabel={(c) => c.name} getColor={(c) => c.color}
            onChange={(id) => set('card_id', form.card_id === id ? null : id)} />
        </Field>
        <label className="check"><input type="checkbox" checked={form.autopay} onChange={(e) => set('autopay', e.target.checked)} /> On autopay (just a reminder label — you still mark it paid)</label>
        <Field label="Notes"><input className="input" value={form.notes} maxLength={300} onChange={(e) => set('notes', e.target.value)} placeholder="Account number, website…" /></Field>
        {error && <p className="form-error">{error}</p>}
        <div className="row">
          {editing && (bill.active ? <ConfirmButton onConfirm={remove}>Delete</ConfirmButton> : <button type="button" className="btn ghost" onClick={restore}>Restore bill</button>)}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary">{editing ? 'Save' : 'Add bill'}</button>
        </div>
      </form>

      {editing && history.data && history.data.payments.length > 0 && (
        <div className="history">
          <h3>Payment history</h3>
          {history.data.payments.map((p) => (
            <div key={p.id} className="history-row">
              <span>{fmtDate(p.date, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
              <span className="muted">{p.is_mine ? p.card : p.username}</span>
              <Money value={p.amount} />
            </div>
          ))}
        </div>
      )}
    </Sheet>
  )
}

export default function Bills() {
  const { today } = useApp()
  const [month, setMonth] = useState(today.slice(0, 7))
  const [editor, setEditor] = useState(null) // null | 'new' | bill
  const [showAll, setShowAll] = useState(false)
  const { data, error, reload } = useFetch(`/bills/checklist?month=${month}`)
  const all = useFetch('/bills')

  const summary = data?.summary
  return (
    <div className="page">
      <PageHeader title="Bills" subtitle="Your monthly checklist — tap Mark paid as you pay each one."
        actions={<button className="btn primary" onClick={() => setEditor('new')}><Plus size={16} /> New bill</button>} />

      <MonthSwitcher month={month} onChange={setMonth} />
      <ErrorNote error={error} onRetry={reload} />
      {!data ? <div className="center-pad"><Spinner /></div> : (
        <>
          {summary.count > 0 && (
            <Card className="bill-summary">
              <div className="row between">
                <div><span className="big">{summary.paid}</span><span className="muted"> of {summary.count} paid</span></div>
                <div className="right">
                  <div className="muted small">Left to pay</div>
                  <strong>{money(summary.remaining)}</strong>
                </div>
              </div>
              <Progress value={summary.paid / summary.count} tone="ok" />
              <div className="row gap muted small">
                {summary.overdue > 0 && <Badge tone="bad">{summary.overdue} overdue</Badge>}
                {summary.due_soon > 0 && <Badge tone="warn">{summary.due_soon} due soon</Badge>}
                <span>Expected total {money(summary.expected_total)}</span>
              </div>
            </Card>
          )}

          {data.items.length === 0 && data.needs_setup.length > 0 ? null : data.items.length === 0 ? (
            <Empty icon="🧾" title="No bills due this month"
              action={<button className="btn primary" onClick={() => setEditor('new')}><Plus size={16} /> Add a bill</button>}>
              Add your recurring bills (rent, phone, insurance…) with a due day, and they'll show up here every month.
            </Empty>
          ) : (
            <div className="card">{data.items.map((i) => <ChecklistRow key={i.bill_id} item={i} month={month} />)}</div>
          )}

          {data.other_payments.length > 0 && (
            <Card title="Other bill payments this month">
              {data.other_payments.map((p) => (
                <div key={p.id} className="history-row">
                  <span>{p.bill_name}</span><span className="muted">{fmtDate(p.date)}</span><Money value={p.amount} />
                </div>
              ))}
            </Card>
          )}

          {data.needs_setup.length > 0 && (
            <Card title="Finish setting up" className="setup">
              <p className="muted small">These bills came from the old version and have no due day yet, so they aren't on the checklist.</p>
              {data.needs_setup.map((b) => (
                <div key={b.bill_id} className="mini-row">
                  <span className="tx-main"><span className="tx-title">{b.name}</span>
                    <span className="tx-detail">{b.last_paid ? `Last paid ${fmtDate(b.last_paid)} · ${money(b.last_amount)}` : 'Never paid'}</span></span>
                  <button className="btn small secondary" onClick={() => setEditor(b)}>Set due day</button>
                </div>
              ))}
            </Card>
          )}
        </>
      )}

      <Card title="All bills" action={<button className="link" onClick={() => setShowAll((s) => !s)}>{showAll ? 'Hide' : 'Show'}</button>}>
        {showAll && (all.data ? all.data.bills.map((b) => (
          <button key={b.bill_id} className={`mini-row clickable ${b.active ? '' : 'archived'}`} onClick={() => setEditor(b)}>
            <span className="tx-main">
              <span className="tx-title">{b.name}{!b.active && <Badge>Archived</Badge>}</span>
              <span className="tx-detail">
                {b.due_day ? `${b.frequency === 'yearly' ? `${MONTHS[b.due_month - 1]} ` : 'Every month on the '}${ordinal(b.due_day)}` : 'Not scheduled'}
                {b.card_name ? ` · ${b.card_name}` : ''}
              </span>
            </span>
            {b.amount ? <Money value={b.amount} /> : null}
            <Pencil size={14} className="muted" />
          </button>
        )) : <Spinner />)}
      </Card>

      {editor && <BillEditor bill={editor === 'new' ? null : editor} onClose={() => { setEditor(null); all.reload() }} />}
    </div>
  )
}

