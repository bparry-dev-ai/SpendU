// Subscriptions whose date has arrived. Confirm logs the charge as spending
// (change the amount first if the price went up); Skip moves to next time.
import { Check, SkipForward } from 'lucide-react'
import { useState } from 'react'
import { post } from '../api'
import { fmtDate } from '../format'
import { useApp } from '../state'
import { CategoryIcon } from './ui'

function PendingRow({ item }) {
  const { changed, notify } = useApp()
  const [amount, setAmount] = useState(item.amount.toFixed(2))
  const [busy, setBusy] = useState(false)
  const priceChanged = Number(amount) !== item.amount

  const confirm = async () => {
    setBusy(true)
    try {
      await post(`/recurring/${item.recurring_id}/confirm`, { amount, update_amount: priceChanged })
      notify(`${item.name} added to spending`)
      changed()
    } catch (e) {
      notify(e.message, 'error')
      setBusy(false)
    }
  }
  const skip = async () => {
    setBusy(true)
    await post(`/recurring/${item.recurring_id}/skip`)
    notify(`Skipped ${item.name} this time`)
    changed()
  }

  return (
    <div className="pending-row">
      <CategoryIcon icon={item.category_icon} color={item.category_color} />
      <div className="tx-main">
        <span className="tx-title">{item.name}</span>
        <span className="tx-detail">Due {fmtDate(item.next_date)} · {item.card}</span>
      </div>
      <div className="mini-amount">
        <span>$</span>
        <input type="number" inputMode="decimal" step="0.01" value={amount} aria-label={`${item.name} amount`}
          onChange={(e) => setAmount(e.target.value)} />
      </div>
      <button className="icon-btn ok" disabled={busy} onClick={confirm} title={priceChanged ? 'Confirm and save new price' : 'Confirm'}
        aria-label={`Confirm ${item.name}`}><Check size={18} /></button>
      <button className="icon-btn" disabled={busy} onClick={skip} title="Skip this time" aria-label={`Skip ${item.name}`}>
        <SkipForward size={16} />
      </button>
    </div>
  )
}

export default function PendingSubscriptions({ items }) {
  if (!items?.length) return null
  return <div className="pending-list">{items.map((i) => <PendingRow key={i.recurring_id} item={i} />)}</div>
}
