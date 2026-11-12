// Recurring spending (subscriptions). They never add spending by themselves:
// when one is due it waits here (and on Home) for you to confirm or skip.
import { Pencil, Plus } from 'lucide-react'
import { useState } from 'react'
import { del, patch, post } from '../api'
import PendingSubscriptions from '../components/PendingSubscriptions'
import { QuickAdd } from '../components/TransactionSheet'
import {
  Badge, Card, CategoryIcon, ConfirmButton, Empty, ErrorNote, Field, Money, PageHeader, Pills, Segmented, Sheet, Spinner, Stat,
} from '../components/ui'
import { fmtDate, money } from '../format'
import { activeCards, activeCategories, useApp, useFetch } from '../state'

const FREQ = { weekly: 'Weekly', monthly: 'Monthly', yearly: 'Yearly' }

function SubscriptionEditor({ item, onClose }) {
  const { meta, today, changed, notify } = useApp()
  const editing = Boolean(item)
  const [form, setForm] = useState({
    name: item?.name || '', amount: item?.amount ?? '', frequency: item?.frequency || 'monthly',
    next_date: item?.next_date || today, category_id: item?.category_id ?? null, card_id: item?.card_id ?? activeCards(meta)[0]?.card_id ?? null,
    notes: item?.notes || '', active: item ? Boolean(item.active) : true,
  })
  const [error, setError] = useState(null)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const save = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      if (editing) await patch(`/recurring/${item.recurring_id}`, form)
      else await post('/recurring', form)
      changed()
      notify(editing ? 'Subscription updated' : 'Subscription added')
      onClose()
    } catch (err) {
      setError(err.message)
    }
  }
  const remove = async () => {
    await del(`/recurring/${item.recurring_id}`)
    changed()
    notify('Subscription deleted (past charges are kept)')
    onClose()
  }

  return (
    <Sheet title={editing ? `Edit ${item.name}` : 'New subscription'} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <Field label="Name"><input className="input" value={form.name} maxLength={80} placeholder="e.g. Netflix, Spotify, Gym" onChange={(e) => set('name', e.target.value)} required /></Field>
        <div className="grid-2">
          <Field label="Amount">
            <input className="input" type="number" inputMode="decimal" step="0.01" value={form.amount} onChange={(e) => set('amount', e.target.value)} required />
          </Field>
          <Field label={editing ? 'Next charge' : 'First / next charge'}>
            <input className="input" type="date" value={form.next_date} onChange={(e) => set('next_date', e.target.value)} required />
          </Field>
        </div>
        <Field label="How often">
          <Segmented value={form.frequency} onChange={(v) => set('frequency', v)} options={Object.entries(FREQ).map(([value, label]) => ({ value, label }))} />
        </Field>
        <Field label="Category">
          <Pills items={activeCategories(meta)} value={form.category_id} getKey={(c) => c.category_id} getLabel={(c) => c.name}
            getColor={(c) => c.color} onChange={(id) => set('category_id', id)}
            extra={<QuickAdd kind="categories" onCreated={(id) => set('category_id', id)} />} />
        </Field>
        <Field label="Card">
          <Pills items={activeCards(meta)} value={form.card_id} getKey={(c) => c.card_id} getLabel={(c) => c.name}
            getColor={(c) => c.color} onChange={(id) => set('card_id', id)} />
        </Field>
        {editing && (
          <label className="check"><input type="checkbox" checked={!form.active} onChange={(e) => set('active', !e.target.checked)} /> Paused (cancelled for now)</label>
        )}
        {error && <p className="form-error">{error}</p>}
        <div className="row">
          {editing && <ConfirmButton onConfirm={remove} />}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary">{editing ? 'Save' : 'Add'}</button>
        </div>
      </form>
    </Sheet>
  )
}

export default function Subscriptions() {
  const { data, error, reload } = useFetch('/recurring')
  const [editor, setEditor] = useState(null)
  const [subFilter, setSubFilter] = useState('all')

  const filteredSubs = data?.items.filter((i) => {
    if (subFilter === 'active') return i.active
    if (subFilter === 'paused') return !i.active
    return true
  }) || []

  return (
    <div className="page">
      <PageHeader title="Subscriptions" subtitle="Repeating charges. When one comes due you'll be asked to confirm it."
        actions={<button className="btn primary" onClick={() => setEditor('new')}><Plus size={16} /> New</button>} />
      <ErrorNote error={error} onRetry={reload} />
      {!data ? <div className="center-pad"><Spinner /></div> : data.items.length === 0 ? (
        <Empty icon="🔁" title="No subscriptions yet"
          action={<button className="btn primary" onClick={() => setEditor('new')}><Plus size={16} /> Add one</button>}>
          Add things like Netflix or a gym membership to see what they cost you per month and year.
        </Empty>
      ) : (
        <>
          <div className="stats-row card pad">
            <Stat label="Per month" value={money(data.summary.monthly_cost)} />
            <Stat label="Per year" value={money(data.summary.yearly_cost)} />
            <Stat label="Active" value={data.summary.count} />
          </div>
          {data.items.some((i) => i.pending) && (
            <Card title="Waiting for you to confirm"><PendingSubscriptions items={data.items.filter((i) => i.pending)} /></Card>
          )}

          <Segmented
            size="sm"
            value={subFilter}
            onChange={setSubFilter}
            options={[
              { value: 'all', label: `All (${data.items.length})` },
              { value: 'active', label: `Active (${data.items.filter((i) => i.active).length})` },
              { value: 'paused', label: `Paused (${data.items.filter((i) => !i.active).length})` },
            ]}
          />

          <div className="card">
            {filteredSubs.length === 0 ? (
              <p className="muted small center card pad">No subscriptions in this view.</p>
            ) : (
              filteredSubs.map((i) => (
                <button key={i.recurring_id} className={`tx-row ${i.active ? '' : 'archived'}`} onClick={() => setEditor(i)}>
                  <CategoryIcon icon={i.category_icon} color={i.category_color} />
                  <span className="tx-main">
                    <span className="tx-title">{i.name} {!i.active && <Badge>Paused</Badge>}</span>
                    <span className="tx-detail">{FREQ[i.frequency]} · next {fmtDate(i.next_date)} · {i.card}</span>
                  </span>
                  <Money value={i.amount} />
                  <Pencil size={14} className="muted" />
                </button>
              ))
            )}
          </div>
        </>
      )}
      {editor && <SubscriptionEditor item={editor === 'new' ? null : editor} onClose={() => setEditor(null)} />}
    </div>
  )
}
