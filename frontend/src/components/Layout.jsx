import {
  CalendarClock, ChartPie, FileUp, Home, LayoutGrid, ListOrdered, Plus, Receipt, Repeat, Settings, Wallet,
} from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp } from '../state'
import BillPaymentSheet from './BillPaymentSheet'
import TransactionSheet from './TransactionSheet'

export const NAV = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/activity', label: 'Activity', icon: ListOrdered },
  { to: '/bills', label: 'Bills', icon: Receipt },
  { to: '/insights', label: 'Insights', icon: ChartPie },
  { to: '/planner', label: 'Planner', icon: Wallet },
  { to: '/subscriptions', label: 'Subscriptions', icon: Repeat },
  { to: '/import', label: 'Import CSV', icon: FileUp },
  { to: '/settings', label: 'Settings', icon: Settings },
]

const MOBILE_TABS = [NAV[0], NAV[1], null, NAV[2], { to: '/more', label: 'More', icon: LayoutGrid }]
const MORE_PATHS = ['/more', '/insights', '/planner', '/subscriptions', '/import', '/settings']

export function Logo() {
  return (
    <div className="logo">
      <span className="logo-mark">S</span>
      <span className="logo-word">SpendU</span>
    </div>
  )
}

export default function Layout() {
  const { sheet, closeSheet, openSheet, toast, user } = useApp()
  const { pathname } = useLocation()

  return (
    <div className="shell">
      <aside className="sidebar">
        <Logo />
        <button className="btn primary block add-btn" onClick={() => openSheet({ type: 'transaction' })}>
          <Plus size={18} /> Add transaction
        </button>
        <nav>
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className="nav-link">
              <Icon size={18} /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot muted">
          <CalendarClock size={14} /> Signed in as {user?.username}
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>

      <nav className="tabbar">
        {MOBILE_TABS.map((tab) =>
          tab === null ? (
            <button key="add" className="tab-add" aria-label="Add transaction"
              onClick={() => openSheet({ type: 'transaction' })}>
              <Plus size={26} />
            </button>
          ) : (
            <NavLink key={tab.to} to={tab.to} end={tab.end}
              className={({ isActive }) => `tab ${isActive || (tab.to === '/more' && MORE_PATHS.includes(pathname)) ? 'active' : ''}`}>
              <tab.icon size={21} />
              <span>{tab.label}</span>
            </NavLink>
          ),
        )}
      </nav>

      {sheet?.type === 'transaction' && <TransactionSheet {...sheet} onClose={closeSheet} />}
      {sheet?.type === 'bill-payment' && <BillPaymentSheet {...sheet} onClose={closeSheet} />}
      {toast && <div className={`toast ${toast.tone}`} role="status">{toast.message}</div>}
    </div>
  )
}
