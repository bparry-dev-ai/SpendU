// The frame around every page: the top bar, the page banner, and on phones
// the bottom tab bar. Also hosts the global Add sheet and toast messages.
import {
  ChartPie, ChevronDown, FileUp, Home, LayoutGrid, ListOrdered, Moon, Plus, Receipt, Repeat, Settings, Sun, Wallet, Zap,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp, useTheme } from '../state'
import BillPaymentSheet from './BillPaymentSheet'
import PageBanner from './PageBanner'
import TransactionSheet from './TransactionSheet'

// `banner` is the one-line subtitle shown in the page banner.
export const NAV = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/activity', label: 'Activity', icon: ListOrdered, banner: 'Everything spent, refunded and paid' },
  { to: '/bills', label: 'Bills', icon: Receipt, banner: 'Your monthly checklist' },
  { to: '/insights', label: 'Insights', icon: ChartPie, banner: 'Charts and trends' },
  { to: '/planner', label: 'Planner', icon: Wallet, banner: 'Income and budget plan' },
  { to: '/subscriptions', label: 'Subscriptions', icon: Repeat, banner: 'Repeating charges' },
  { to: '/import', label: 'Import CSV', icon: FileUp, banner: 'Bring in a bank statement' },
  { to: '/settings', label: 'Settings', icon: Settings, banner: 'Preferences and security' },
]
const MORE = { to: '/more', label: 'More', icon: LayoutGrid, banner: 'Everything else' }

const MOBILE_TABS = [NAV[0], NAV[1], null, NAV[2], MORE]
const MORE_PATHS = ['/more', '/insights', '/planner', '/subscriptions', '/import', '/settings']
const TOPBAR_LINKS = ['/activity', '/insights', '/planner'].map((to) => NAV.find((n) => n.to === to))

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

function bannerFor(pathname, username) {
  const page = [...NAV, MORE].find((n) => n.to === pathname)
  if (!page || page.to === '/') {
    const name = username.charAt(0).toUpperCase() + username.slice(1)
    return { title: 'Home', subtitle: `${greeting()}, ${name}` }
  }
  return { title: page.label, subtitle: page.banner }
}

export function Logo() {
  return (
    <div className="logo">
      <span className="logo-mark"><Zap size={18} fill="currentColor" /></span>
      <span className="logo-word">SpendU</span>
    </div>
  )
}

const topLink = ({ isActive }) => `topbar-link ${isActive ? 'active' : ''}`
const iconButton = ({ isActive }) => `topbar-icon ${isActive ? 'active' : ''}`

function NavMenu() {
  const { user } = useApp()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => setOpen(false), [pathname])

  // Close on a click outside the menu, or Escape.
  useEffect(() => {
    if (!open) return undefined
    const onClick = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('click', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('click', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="topbar-menu" ref={ref}>
      <button className="topbar-icon wide" onClick={() => setOpen(!open)} aria-haspopup="true" aria-expanded={open}>
        <LayoutGrid size={15} />
        <span>Menu</span>
        <ChevronDown size={13} className={open ? 'flip' : ''} />
      </button>
      {open && (
        <nav className="topbar-dropdown">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `dropdown-link ${isActive ? 'active' : ''}`}>
              <Icon size={16} /> {label}
            </NavLink>
          ))}
          <div className="dropdown-foot">Signed in as {user.username}</div>
        </nav>
      )}
    </div>
  )
}

function TopBar() {
  const { openSheet } = useApp()
  const { isDark, toggleTheme } = useTheme()

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Logo />
        {/* On phones the bottom tab bar covers Home, Add and the rest. */}
        <div className="topbar-nav">
          <NavLink to="/" end className={topLink}><Home size={15} /> Home</NavLink>
          <button className="topbar-add" onClick={() => openSheet({ type: 'transaction' })}>
            <Plus size={16} /> Add transaction
          </button>
          <nav className="topbar-links">
            {TOPBAR_LINKS.map(({ to, label }) => <NavLink key={to} to={to} className={topLink}>{label}</NavLink>)}
          </nav>
        </div>
        <span className="spacer" />
        <NavMenu />
        <button className="topbar-icon" onClick={toggleTheme}
          title={`Switch to ${isDark ? 'light' : 'dark'} mode`} aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}>
          {isDark ? <Sun size={15} /> : <Moon size={15} />}
        </button>
        <NavLink to="/settings" className={iconButton} title="Settings" aria-label="Settings">
          <Settings size={15} />
        </NavLink>
      </div>
    </header>
  )
}

export default function Layout() {
  const { sheet, closeSheet, openSheet, toast, user } = useApp()
  const { pathname } = useLocation()

  return (
    <div className="shell">
      {/* Soft colour glows behind the glass cards */}
      <div className="ambient-aurora" aria-hidden="true">
        <div className="orb-1" />
        <div className="orb-2" />
      </div>

      <TopBar />

      <main className="main">
        <div className="page-shell">
          <PageBanner {...bannerFor(pathname, user.username)} />
          <Outlet />
        </div>
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
