// Monthly budgets — personal (your spending) and family (everyone's).
import { Plus, Users } from 'lucide-react'
import { useState } from 'react'
import { del, patch, post } from '../api'
import {
  Badge, Card, ConfirmButton, Empty, ErrorNote, Field, MonthSwitcher, PageHeader, Progress, Segmented, Sheet, Spinner,
} from '../components/ui'
import { money, pct } from '../format'
import { activeCategories, useApp, useFetch } from '../state'

const TONE = { over: 'bad', warning: 'warn', ahead: 'warn', ok: 'ok' }
const STATUS_TEXT = { over: 'Over budget', warning: 'Almost there', ahead: 'Spending fast', ok: 'On track' }

export function BudgetRow({ b, compact, onEdit, monthProgress }) {
  const label = b.category_name || 'All spending'
  return (
    <button type="button" className={`budget-row ${compact ? 'compact' : ''}`} onClick={onEdit} disabled={!onEdit}>
      <div className="budget-top">
        <span className="budget-name">
          {label}
          {b.is_family ? <span className="tag"><Users size={11} /> Family</span> : null}
        </span>
        <span className="budget-nums">
          <strong>{money(b.spent)}</strong><span className="muted"> / {money(b.amount)}</span>
        </span>
      </div>
      <Progress value={b.pct} tone={TONE[b.status]} marker={monthProgress} />
      {!compact && (
        <div className="budget-foot">
          <Badge tone={TONE[b.status]}>{STATUS_TEXT[b.status]}</Badge>
          <span className="muted small">
            {b.remaining >= 0 ? `${money(b.remaining)} left` : `${money(-b.remaining)} over`} · {pct(b.pct)} used
          </span>
        </div>
      )}
    </button>
  )
}

function BudgetEditor({ budget, onClose, onSaved }) {
  const { meta, family, notify } = useApp()
  const editing = Boolean(budget)
  const [isFamily, setIsFamily] = useState(budget ? Boolean(budget.is_family) : false)
  const [category, setCategory] = useState(budget?.category_name || '')
  const [amount, setAmount] = useState(budget?.amount ?? '')
  const [error, setError] = useState(null)
  const familyNames = useFetch(isFamily ? '/budgets/family-categories' : null)
  const names = isFamily ? familyNames.data?.names || [] : activeCategories(meta).map((c) => c.name)

  const save = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const payload = { amount, category_name: category || null, is_family: isFamily }
      const res = editing ? await patch(`/budgets/${budget.budget_id}`, payload) : await post('/budgets', payload)
      onSaved(res)
      notify(editing ? 'Budget updated' : 'Budget created')
      onClose()
    } catch (err) {
      setError(err.message)
    }
  }
  const remove = async () => {
    onSaved(await del(`/budgets/${budget.budget_id}`))
    notify('Budget deleted')
    onClose()
  }

  return (
    <Sheet title={editing ? 'Edit budget' : 'New budget'} onClose={onClose}>
      <form className="stack" onSubmit={save}>
        {!editing && family.length > 1 && (
          <Field label="Whose spending" hint={isFamily ? 'Counts everyone\'s spending in categories with this name.' : 'Counts only your own spending.'}>
            <Segmented value={isFamily ? 'family' : 'me'} onChange={(v) => { setIsFamily(v === 'family'); setCategory('') }}
              options={[{ value: 'me', label: 'Just me' }, { value: 'family', label: 'Family' }]} />
          </Field>
        )}
        <Field label="Category">
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All spending (overall limit)</option>
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>
        <Field label="Monthly limit">
          <div className="amount-input small">
            <span>$</span>
            <input type="number" inputMode="decimal" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" required />
          </div>
        </Field>
        {error && <p className="form-error">{error}</p>}
        <div className="row">
          {editing && <ConfirmButton onConfirm={remove} />}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary">{editing ? 'Save' : 'Create'}</button>
        </div>
      </form>
    </Sheet>
  )
}

export default function Budgets() {
  const { today, family } = useApp()
  const [month, setMonth] = useState(today.slice(0, 7))
  const [editor, setEditor] = useState(null)
  const { data, error, reload } = useFetch(`/budgets?month=${month}`)

  const section = (title, items, hint) => (
    <Card title={title}>
      {hint && <p className="muted small">{hint}</p>}
      <div className="stack-sm">
        {items.map((b) => (
          <BudgetRow key={b.budget_id} b={b} monthProgress={data.month_progress}
            onEdit={b.can_edit ? () => setEditor(b) : undefined} />
        ))}
      </div>
    </Card>
  )

  return (
    <div className="page">
      <PageHeader title="Budgets" subtitle="Monthly limits. The thin line shows how far through the month you are."
        actions={<button className="btn primary" onClick={() => setEditor('new')}><Plus size={16} /> New budget</button>} />
      <MonthSwitcher month={month} onChange={setMonth} />
      <ErrorNote error={error} onRetry={reload} />
      {!data ? <div className="center-pad"><Spinner /></div> : (
        data.personal.length + data.family.length === 0 ? (
          <Empty icon="🎯" title="No budgets yet"
            action={<button className="btn primary" onClick={() => setEditor('new')}><Plus size={16} /> Create a budget</button>}>
            Set a monthly limit for a category (like Eating Out) or for all your spending.
          </Empty>
        ) : (
          <>
            {data.personal.length > 0 && section('Your budgets', data.personal)}
            {data.family.length > 0 && section('Family budgets', data.family, family.length > 1 ? 'Shared — anyone in the family can edit these.' : null)}
            <p className="muted small center">Bills aren't counted in budgets — they're tracked on the Bills page.</p>
          </>
        )
      )}
      {editor && <BudgetEditor budget={editor === 'new' ? null : editor} onClose={() => setEditor(null)} onSaved={reload} />}
    </div>
  )
}
