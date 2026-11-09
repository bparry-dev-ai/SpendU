// Budget Planner: monthly income split into Needs, Wants and Savings.
// Each budget area is a card: type the planned amount right on it, and see
// this month's spending and your recent average next to it. Numbers refresh
// automatically whenever you add a transaction or pay a bill.
import {
  AlertTriangle, ArrowDownRight, ArrowUpRight, CheckCircle2, Info, Lightbulb, PiggyBank, Plus, Receipt, Repeat,
  RotateCcw, Sparkles, Trash2, Users, X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { del, patch, post, query } from '../api'
import {
  Badge, Card, CategoryIcon, Empty, ErrorNote, Field, MonthSwitcher, PageHeader, Progress, Segmented, Sheet, Spinner,
} from '../components/ui'
import { money, pct } from '../format'
import { useApp, useFetch } from '../state'

const GROUPS = [
  { key: 'needs', label: 'Needs', hint: 'Must-pays: housing, groceries, bills, transport', color: '#6366f1' },
  { key: 'wants', label: 'Wants', hint: 'Nice-to-haves: eating out, shopping, fun, subscriptions', color: '#ec4899' },
  { key: 'savings', label: 'Savings', hint: 'Emergency fund, TSP, extra debt payments', color: '#14b8a6' },
]
const TONE = { over: 'bad', warning: 'warn', ahead: 'warn', ok: 'ok', paid: 'ok', due: 'neutral', unplanned: 'warn' }
const STATUS_TEXT = { over: 'Over', warning: 'Almost there', ahead: 'Spending fast', ok: 'On track', paid: 'Paid', due: 'Not paid yet' }
const KIND_LABEL = { category: 'Category', bill: 'Bill', subscription: 'Subscription', custom: 'Planned only' }

// Shown on Home: category lines acting as monthly limits.
export function LimitRow({ b }) {
  const tone = { over: 'bad', warning: 'warn', ahead: 'warn', ok: 'ok' }[b.status]
  return (
    <div className="budget-row compact">
      <div className="budget-top">
        <span className="budget-name">
          {b.label}
          {b.is_family ? <span className="tag"><Users size={11} /> Household</span> : null}
        </span>
        <span className="budget-nums"><strong>{money(b.spent)}</strong><span className="muted"> / {money(b.amount)}</span></span>
      </div>
      <Progress value={b.pct} tone={tone} />
    </div>
  )
}

// A dollar input that saves when you press Enter or tap away.
function AmountInput({ value, onSave, label, big, placeholder = '0' }) {
  const [text, setText] = useState(value ? String(value) : '')
  useEffect(() => { setText(value ? String(value) : '') }, [value])
  const commit = () => {
    const next = text === '' ? 0 : Number(text)
    if (Number.isNaN(next) || next === (value || 0)) return setText(value ? String(value) : '')
    onSave(next)
  }
  return (
    <label className={`amount-block ${big ? 'big' : ''}`}>
      {label && <span className="amount-block-label">{label}</span>}
      <span className="amount-block-field">
        <span>$</span>
        <input type="number" inputMode="decimal" step="0.01" min="0" value={text} placeholder={placeholder}
          onChange={(e) => setText(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} aria-label={label || 'Amount'} />
      </span>
    </label>
  )
}

function LineIcon({ line }) {
  if (line.kind === 'bill') return <span className="cat-icon" style={{ '--c': '#64748b', width: 36, height: 36 }}><Receipt size={16} /></span>
  if (line.kind === 'subscription') return <span className="cat-icon" style={{ '--c': '#8b5cf6', width: 36, height: 36 }}><Repeat size={16} /></span>
  if (line.kind === 'custom') return <span className="cat-icon" style={{ '--c': '#14b8a6', width: 36, height: 36 }}><PiggyBank size={16} /></span>
  return <CategoryIcon icon={line.icon} color={line.color} />
}

function HistoryNote({ line, months }) {
  if (line.average === null || line.average === undefined) {
    return <span className="muted small">No history yet</span>
  }
  const span = months === 1 ? 'Last month' : `${months}-mo avg`
  const diff = line.average - line.planned
  return (
    <span className="history-note">
      <span className="muted small">{span}</span>
      <strong>{money(line.average)}</strong>
      {line.history === 'over' && <Badge tone="bad"><ArrowUpRight size={12} /> {money(diff)} over plan</Badge>}
      {line.history === 'under' && <Badge tone="ok"><ArrowDownRight size={12} /> {money(-diff)} under</Badge>}
      {line.history === 'on_track' && line.kind === 'category' && <Badge tone="ok">On track</Badge>}
    </span>
  )
}

function LineCard({ line, months, monthProgress, colorFor, onChange }) {
  const { notify } = useApp()
  const save = async (changes, message) => {
    try {
      await patch(`/planner/lines/${line.line_id}`, changes)
      if (message) notify(message)
      onChange()
    } catch (e) {
      notify(e.message, 'error')
    }
  }
  const remove = async () => {
    await del(`/planner/lines/${line.line_id}`)
    notify(line.kind === 'bill' || line.kind === 'subscription' ? `${line.name} removed — restore it any time at the bottom` : `${line.name} removed`)
    onChange()
  }
  const color = line.kind === 'category' ? colorFor(line.name) : undefined
  const showUseAvg = line.average && line.history && line.history !== 'on_track' && line.kind !== 'subscription'

  return (
    <div className={`line-card ${line.status === 'over' ? 'is-over' : ''}`}>
      <div className="line-head">
        <LineIcon line={{ ...line, color }} />
        <div className="tx-main">
          <span className="tx-title">{line.name}</span>
          <span className="tx-detail">{KIND_LABEL[line.kind]}{line.follows_source ? ' · uses usual amount' : ''}</span>
        </div>
        <RemoveButton onConfirm={remove} name={line.name} />
      </div>

      <div className="line-inputs">
        <AmountInput label="Planned / month" value={line.planned}
          onSave={(amount) => save({ amount }, `${line.name} set to ${money(amount)}`)} />
        <label className="group-select">
          <span className="amount-block-label">Group</span>
          <select className="input slim" value={line.group_name} onChange={(e) => save({ group: e.target.value })}>
            {GROUPS.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
          </select>
        </label>
      </div>
      {!line.follows_source && line.source_amount !== null && line.source_amount !== undefined && line.source_amount !== line.planned && (
        <button className="link small left" onClick={() => save({ amount: null }, 'Using the usual amount again')}>
          <RotateCcw size={12} /> Use usual amount ({money(line.source_amount)})
        </button>
      )}

      {line.tracked ? (
        <div className="line-info">
          <div className="line-month">
            <span><strong>{money(line.spent)}</strong><span className="muted"> spent this month</span></span>
            {line.status && <Badge tone={TONE[line.status]}>{STATUS_TEXT[line.status]}</Badge>}
          </div>
          <Progress value={line.pct} tone={TONE[line.status] === 'neutral' ? undefined : TONE[line.status]}
            marker={line.kind === 'category' ? monthProgress : undefined} />
          <div className="line-foot">
            <span className="muted small">
              {line.remaining >= 0 ? `${money(line.remaining)} left` : `${money(-line.remaining)} over`}
            </span>
          </div>
          <div className="line-history">
            <HistoryNote line={line} months={months} />
            {showUseAvg && (
              <button className="btn small secondary" onClick={() => save({ amount: Math.ceil(line.average / 5) * 5 }, `${line.name} updated to your average`)}>
                Use avg
              </button>
            )}
          </div>
        </div>
      ) : (
        <p className="muted small line-note">Planned only — money moved to savings isn't tracked as spending.</p>
      )}
    </div>
  )
}

function RemoveButton({ onConfirm, name }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(false), 3000)
    return () => clearTimeout(t)
  }, [armed])
  return (
    <button type="button" className={`icon-btn ${armed ? 'danger-armed' : ''}`} aria-label={`Remove ${name}`}
      title={armed ? 'Tap again to remove' : 'Remove from plan'} onClick={() => (armed ? onConfirm() : setArmed(true))}>
      {armed ? <Trash2 size={16} /> : <X size={16} />}
    </button>
  )
}

function AddLineSheet({ scope, group, report, onClose, onAdded }) {
  const { notify } = useApp()
  const [kind, setKind] = useState(report.category_choices.length ? 'category' : 'custom')
  const [targetGroup, setTargetGroup] = useState(group)
  const [category, setCategory] = useState('')
  const [label, setLabel] = useState('')
  const [amount, setAmount] = useState('')
  const [error, setError] = useState(null)
  const unplanned = Object.fromEntries(report.unplanned.map((u) => [u.name, u]))

  const pickCategory = (name) => {
    setCategory(name)
    const u = unplanned[name]
    if (u && !amount) setAmount(String(Math.ceil((u.average || u.spent) / 5) * 5))
  }
  const save = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      await post('/planner/lines', { scope, kind, group: targetGroup, category_name: category, label, amount: amount || 0 })
      notify(`${kind === 'category' ? category : label} added to ${GROUPS.find((g) => g.key === targetGroup).label}`)
      onAdded()
      onClose()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <Sheet title="Add a budget area" onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <Segmented value={kind} onChange={setKind} options={[
          { value: 'category', label: 'Spending category' }, { value: 'custom', label: 'Savings / other' },
        ]} />
        {kind === 'category' ? (
          <Field label="Category" hint="Spending in this category is tracked against the plan automatically.">
            {report.category_choices.length === 0 ? (
              <p className="muted small">All your categories are already in the plan. Add new categories in Settings.</p>
            ) : (
              <select className="input" value={category} onChange={(e) => pickCategory(e.target.value)} required>
                <option value="">Choose…</option>
                {report.category_choices.map((n) => (
                  <option key={n} value={n}>{n}{unplanned[n]?.average ? ` (avg ${money(unplanned[n].average)})` : ''}</option>
                ))}
              </select>
            )}
          </Field>
        ) : (
          <Field label="Name" hint="e.g. Emergency fund, TSP, Vacation fund, Extra car payment. Planned only.">
            <input className="input" value={label} maxLength={50} onChange={(e) => setLabel(e.target.value)} required />
          </Field>
        )}
        <Field label="Group">
          <Segmented value={targetGroup} onChange={setTargetGroup} options={GROUPS.map((g) => ({ value: g.key, label: g.label }))} />
        </Field>
        <Field label="Planned per month">
          <div className="amount-input small">
            <span>$</span>
            <input type="number" inputMode="decimal" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          </div>
        </Field>
        {error && <p className="form-error">{error}</p>}
        <div className="row">
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary">Add</button>
        </div>
      </form>
    </Sheet>
  )
}

function SplitBar({ report }) {
  const income = report.summary.income
  const total = Math.max(income, report.summary.planned) || 1
  const parts = GROUPS.map((g) => ({ ...g, value: report.groups[g.key].planned }))
  const left = Math.max(0, income - report.summary.planned)
  return (
    <div className="split">
      <div className="split-bar">
        {parts.map((p) => p.value > 0 && (
          <div key={p.key} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.label}: ${money(p.value)}`} />
        ))}
        {left > 0 && <div className="split-left" style={{ width: `${(left / total) * 100}%` }} title={`Left to assign: ${money(left)}`} />}
        {income > 0 && <span className="split-guide" style={{ left: '50%' }} title="50% Needs guide" />}
        {income > 0 && <span className="split-guide" style={{ left: '80%' }} title="+30% Wants guide" />}
      </div>
      <div className="split-legend">
        {parts.map((p) => {
          const g = report.groups[p.key]
          return (
            <div key={p.key} className="split-item">
              <span className="dot" style={{ background: p.color, width: 10, height: 10 }} />
              <span>{p.label}</span>
              <strong>{money(g.planned)}</strong>
              {g.share !== null && <span className={`muted small ${p.key !== 'savings' && g.share > g.guide + 0.1 ? 'warn-text' : ''}`}>
                {pct(g.share)} · guide {pct(g.guide)}</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const TIP_ICON = { bad: AlertTriangle, warn: AlertTriangle, ok: CheckCircle2, info: Info }

function Suggestions({ report, scope, onChange }) {
  const { notify } = useApp()
  if (!report.suggestions.length) return null
  const act = async (a) => {
    try {
      if (a.kind === 'set_amount') await patch(`/planner/lines/${a.line_id}`, { amount: a.amount })
      if (a.kind === 'add_category') {
        await post('/planner/lines', { scope, kind: 'category', category_name: a.category_name, amount: a.amount, group: a.group })
      }
      if (a.kind === 'add_savings') await post('/planner/lines', { scope, kind: 'custom', label: 'Savings', group: 'savings', amount: a.amount })
      notify('Plan updated')
      onChange()
    } catch (e) {
      notify(e.message, 'error')
    }
  }
  const actionLabel = (a) => (a.kind === 'set_amount' ? `Set to ${money(a.amount)}` : a.kind === 'add_category' ? `Add (${money(a.amount)})` : 'Add to Savings')
  return (
    <Card title={<span className="row"><Lightbulb size={16} /> Suggestions</span>}>
      <div className="tips">
        {report.suggestions.map((t, i) => {
          const Icon = TIP_ICON[t.tone] || Info
          return (
            <div key={i} className={`tip ${t.tone}`}>
              <Icon size={16} className="tip-icon" />
              <span className="tip-text">{t.message}</span>
              {t.action && <button className="btn small secondary" onClick={() => act(t.action)}>{actionLabel(t.action)}</button>}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

export default function Planner() {
  const { today, family, meta, notify } = useApp()
  const [scope, setScope] = useState('personal')
  const [month, setMonth] = useState(today.slice(0, 7))
  const [months, setMonths] = useState(3)
  const [adding, setAdding] = useState(null) // group key
  const { data, error, reload } = useFetch('/planner' + query({ scope, month, months }))

  const colorFor = (name) => meta.categories.find((c) => c.name.toLowerCase() === (name || '').toLowerCase())?.color || '#94a3b8'
  const updatePlan = async (changes, message) => {
    try {
      await patch('/planner', { scope, ...changes })
      if (message) notify(message)
      reload()
    } catch (e) {
      notify(e.message, 'error')
    }
  }
  const startFromSpending = async () => {
    const res = await post('/planner/start', { scope })
    notify(res.added ? `Added ${res.added} categories from your spending` : 'No recent spending to start from')
    reload()
  }
  const restore = async (lineId) => { await post(`/planner/lines/${lineId}/restore`); reload() }

  const isCurrentMonth = month === today.slice(0, 7)
  return (
    <div className="page">
      <PageHeader title="Budget Planner"
        subtitle={scope === 'household' ? 'Shared plan — compared against everyone\'s spending. Anyone in the family can edit it.' : 'Give every dollar of your income a job.'}
        actions={family.length > 1 && (
          <Segmented value={scope} onChange={setScope} size="sm" options={[{ value: 'personal', label: 'My plan' }, { value: 'household', label: 'Household' }]} />
        )} />

      <div className="row between wrap">
        <MonthSwitcher month={month} onChange={setMonth} />
        <label className="row small muted">
          Compare with
          <select className="input auto slim" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            <option value={1}>last month</option>
            <option value={3}>3-month average</option>
            <option value={6}>6-month average</option>
            <option value={12}>12-month average</option>
          </select>
        </label>
      </div>

      <ErrorNote error={error} onRetry={reload} />
      {!data ? <div className="center-pad"><Spinner /></div> : (
        <>
          <Card className="plan-summary">
            <div className="plan-figures">
              <AmountInput big label="Monthly income (take-home)" value={data.plan.income}
                onSave={(income) => updatePlan({ income }, 'Income saved')} placeholder="Enter income" />
              <div className="plan-figure">
                <span className="amount-block-label">Planned</span>
                <span className="plan-num">{money(data.summary.planned)}</span>
              </div>
              <div className={`plan-figure ${data.summary.left_to_assign < -0.005 ? 'neg' : data.summary.left_to_assign > 0.5 ? 'pos' : 'zero'}`}>
                <span className="amount-block-label">{data.summary.left_to_assign < -0.005 ? 'Over-planned by' : 'Left to assign'}</span>
                <span className="plan-num">{money(Math.abs(data.summary.left_to_assign))}</span>
              </div>
            </div>
            <SplitBar report={data} />
            <div className="plan-cap">
              <span className="muted small">
                {isCurrentMonth ? 'Spent so far this month' : 'Spent that month'}: <strong>{money(data.summary.spent_this_month)}</strong>
                {data.plan.overall_cap ? <> of your {money(data.plan.overall_cap)} overall limit</> : null}
              </span>
              <AmountInput label="Overall spending limit (optional)" value={data.plan.overall_cap}
                onSave={(cap) => updatePlan({ overall_cap: cap || null }, cap ? 'Overall limit saved' : 'Overall limit removed')} placeholder="None" />
            </div>
          </Card>

          {data.lines.length === 0 ? (
            <Empty icon={<Sparkles size={30} />} title="Your plan is empty"
              action={
                <div className="row wrap" style={{ justifyContent: 'center' }}>
                  <button className="btn primary" onClick={startFromSpending}><Sparkles size={16} /> Start from my spending</button>
                  <button className="btn secondary" onClick={() => setAdding('needs')}><Plus size={16} /> Add manually</button>
                </div>
              }>
              Start from your spending to get a card for each category you've used recently, set to your average. Bills and subscriptions are added automatically.
            </Empty>
          ) : (
            <Suggestions report={data} scope={scope} onChange={reload} />
          )}

          {data.lines.length > 0 && GROUPS.map((g) => {
            const lines = data.lines.filter((l) => l.group_name === g.key)
            const info = data.groups[g.key]
            return (
              <section key={g.key} className="plan-group">
                <header className="plan-group-head">
                  <div>
                    <h2><span className="dot" style={{ background: g.color, width: 10, height: 10 }} /> {g.label}</h2>
                    <p className="muted small">{g.hint}</p>
                  </div>
                  <div className="right">
                    <strong>{money(info.planned)}</strong>
                    <div className="muted small">{money(info.spent)} spent{info.share !== null ? ` · ${pct(info.share)} of income` : ''}</div>
                  </div>
                </header>
                <div className="line-grid">
                  {lines.map((l) => (
                    <LineCard key={l.line_id} line={l} months={data.history_months || months} monthProgress={data.month_progress}
                      colorFor={colorFor} onChange={reload} />
                  ))}
                  <button className="line-card add-card" onClick={() => setAdding(g.key)}>
                    <Plus size={22} />
                    <span>Add to {g.label}</span>
                  </button>
                </div>
              </section>
            )
          })}

          {data.hidden.length > 0 && (
            <Card title="Removed from the plan">
              <p className="muted small">Bills and subscriptions you removed. They stay out of the plan until you restore them.</p>
              {data.hidden.map((h) => (
                <div key={h.line_id} className="mini-row">
                  <span className="tx-main"><span className="tx-title">{h.name}</span><span className="tx-detail">{KIND_LABEL[h.kind]}</span></span>
                  <button className="btn small secondary" onClick={() => restore(h.line_id)}><RotateCcw size={14} /> Restore</button>
                </div>
              ))}
            </Card>
          )}
        </>
      )}

      {adding && data && <AddLineSheet scope={scope} group={adding} report={data} onClose={() => setAdding(null)} onAdded={reload} />}
    </div>
  )
}
