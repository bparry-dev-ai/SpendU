// Phone-only menu for the pages that don't fit in the bottom tab bar.
import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { NAV } from '../components/Layout'
import { PageHeader } from '../components/ui'

const DESCRIPTIONS = {
  '/insights': 'Charts by category and card, trends, calendar',
  '/planner': 'Plan your income: needs, wants and savings',
  '/subscriptions': 'Repeating charges to confirm',
  '/import': 'Bring in a bank statement CSV',
  '/settings': 'Cards, categories, timezone, Face ID',
}

export default function More() {
  const items = NAV.filter((n) => DESCRIPTIONS[n.to])
  return (
    <div className="page">
      <PageHeader title="More" />
      <div className="card">
        {items.map(({ to, label, icon: Icon }) => (
          <Link key={to} to={to} className="menu-row">
            <span className="menu-icon"><Icon size={18} /></span>
            <span className="tx-main"><span className="tx-title">{label}</span><span className="tx-detail">{DESCRIPTIONS[to]}</span></span>
            <ChevronRight size={18} className="muted" />
          </Link>
        ))}
      </div>
    </div>
  )
}
