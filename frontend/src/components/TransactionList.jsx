// A list of transactions grouped by day. Tapping one opens it for editing.
import { Receipt, Repeat } from 'lucide-react'
import { relativeDay } from '../format'
import { useApp } from '../state'
import { CategoryIcon, Money } from './ui'

export function TransactionRow({ tx }) {
  const { openSheet } = useApp()
  const isBill = tx.kind === 'bill'
  const open = () => {
    if (isBill) openSheet({ type: 'bill-payment', payment: tx })
    else openSheet({ type: 'transaction', entry: tx })
  }
  const title = tx.merchant || tx.category || 'Spending'
  const detail = [isBill ? 'Bill' : tx.merchant ? tx.category : null, tx.card].filter(Boolean).join(' · ')
  return (
    <button className="tx-row" onClick={open}>
      {isBill ? (
        <span className="cat-icon" style={{ '--c': 'var(--muted)' }}><Receipt size={16} /></span>
      ) : (
        <CategoryIcon icon={tx.category_icon} color={tx.category_color} />
      )}
      <span className="tx-main">
        <span className="tx-title">
          {title}
          {tx.recurring_id && <Repeat size={12} className="muted" aria-label="Subscription" />}
        </span>
        <span className="tx-detail">{detail}{tx.notes ? ` · ${tx.notes}` : ''}</span>
      </span>
      <Money value={tx.amount} signed className="tx-amount" />
    </button>
  )
}

export default function TransactionList({ items, grouped = true }) {
  const { today } = useApp()
  if (!grouped) {
    return <div className="tx-list">{items.map((t) => <TransactionRow key={`${t.kind}-${t.id}`} tx={t} />)}</div>
  }
  const groups = []
  for (const t of items) {
    const last = groups[groups.length - 1]
    if (last && last.date === t.date) last.items.push(t)
    else groups.push({ date: t.date, items: [t] })
  }
  return (
    <div className="tx-list">
      {groups.map((g) => (
        <div key={g.date} className="tx-group">
          <div className="tx-day">
            <span>{relativeDay(g.date, today)}</span>
            <Money value={g.items.reduce((s, t) => s + t.amount, 0)} signed />
          </div>
          {g.items.map((t) => <TransactionRow key={`${t.kind}-${t.id}`} tx={t} />)}
        </div>
      ))}
    </div>
  )
}
