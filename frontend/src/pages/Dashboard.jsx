import { ArrowDownRight, ArrowUpRight, ChevronRight, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PaceChart } from '../components/charts'
import PendingSubscriptions from '../components/PendingSubscriptions'
import TransactionList from '../components/TransactionList'
import { BillStatus } from './Bills'
import { BudgetRow } from './Budgets'
import { Card, CategoryIcon, Empty, ErrorNote, Money, Progress, Spinner } from '../components/ui'
import { fmtDate, fmtDateLong, money, monthName } from '../format'
import { useApp, useFetch } from '../state'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

export default function Dashboard() {
  const { user, family, today, openSheet, meta } = useApp()
  const { data, error, reload } = useFetch('/dashboard')

  if (error) return <ErrorNote error={error} onRetry={reload} />
  if (!data) return <div className="center-pad"><Spinner /></div>

  const s = data.spending
  const diff = s.month - s.last_month_to_date
  const name = user.username.charAt(0).toUpperCase() + user.username.slice(1)
  const billsSummary = data.bills.summary
  const isNewUser = meta.cards.length === 0 && meta.categories.length === 0
  const unscheduled = meta.bills.filter((b) => b.active && b.due_day == null).length

  return (
    <div className="page dashboard">
      <div className="page-head">
        <div>
          <p className="muted">{fmtDateLong(today)}</p>
          <h1>{greeting()}, {name}</h1>
        </div>
      </div>

      {isNewUser && (
        <Card className="welcome">
          <h2>Welcome to SpendU 👋</h2>
          <p className="muted">Start by adding a transaction — you can create your cards and categories right in the form.</p>
          <button className="btn primary" onClick={() => openSheet({ type: 'transaction' })}><Plus size={16} /> Add your first transaction</button>
        </Card>
      )}

      <div className="dash-grid">
        <Card className="hero">
          <span className="hero-label">Spent in {monthName(data.month)}</span>
          <span className="hero-value">{money(s.month)}</span>
          <span className={`hero-compare ${diff > 0 ? 'up' : 'down'}`}>
            {s.last_month_to_date === 0 && s.month === 0 ? 'Nothing spent yet this month' : (
              <>
                {diff > 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
                {money(Math.abs(diff))} {diff > 0 ? 'more' : 'less'} than this time last month
              </>
            )}
          </span>
          <PaceChart thisMonth={data.pace.this_month} lastMonth={data.pace.last_month} />
          <div className="hero-stats">
            <div><span className="muted small">This week ({fmtDate(s.week_start)}–{fmtDate(s.week_end)})</span><strong>{money(s.week)}</strong></div>
            <div><span className="muted small">Bills paid</span><strong>{money(s.bills_paid)}</strong></div>
            {family.length > 1 && (
              <div><span className="muted small">Family this month</span><strong>{money(s.family_month)}</strong></div>
            )}
          </div>
        </Card>

        <div className="dash-side">
          {data.pending_recurring.length > 0 && (
            <Card title="Subscriptions to confirm" action={<Link to="/subscriptions" className="link">All</Link>}>
              <PendingSubscriptions items={data.pending_recurring} />
            </Card>
          )}

          <Card title={`${monthName(data.month)} bills`} action={<Link to="/bills" className="link">Checklist <ChevronRight size={14} /></Link>}>
            {billsSummary.count === 0 ? (
              <Empty title={unscheduled ? `${unscheduled} bill${unscheduled === 1 ? '' : 's'} need a due day` : 'No bills set up yet'}>
                <Link to="/bills" className="link">
                  {unscheduled ? 'Add due days to start the monthly checklist' : 'Set up your monthly bills'}
                </Link>
              </Empty>
            ) : (
              <>
                <div className="bills-progress">
                  <span><strong>{billsSummary.paid}</strong> of {billsSummary.count} paid</span>
                  <span className="muted">{money(billsSummary.remaining)} left to pay</span>
                </div>
                <Progress value={billsSummary.paid / billsSummary.count} tone="ok" />
                <div className="mini-list">
                  {data.bills.open.map((b) => (
                    <div key={b.bill_id} className="mini-row">
                      <span className="tx-main">
                        <span className="tx-title">{b.name}</span>
                        <span className="tx-detail">Due {fmtDate(b.due_date)}{b.expected ? ` · ${money(b.expected)}` : ''}</span>
                      </span>
                      <BillStatus status={b.status} />
                      <button className="btn small secondary" onClick={() => openSheet({ type: 'bill-payment', bill: b, month: data.month })}>Pay</button>
                    </div>
                  ))}
                  {data.bills.open.length === 0 && <p className="muted small">All paid for this month 🎉</p>}
                </div>
              </>
            )}
          </Card>
        </div>

        <Card title="Budgets" action={<Link to="/budgets" className="link">Manage</Link>}>
          {data.budgets.length === 0 ? (
            <Empty title="No budgets yet"><Link to="/budgets" className="link">Create a monthly budget</Link></Empty>
          ) : (
            <div className="stack-sm">{data.budgets.map((b) => <BudgetRow key={b.budget_id} b={b} compact />)}</div>
          )}
        </Card>

        <Card title="Top categories" action={<Link to="/insights" className="link">Insights</Link>}>
          {data.top_categories.length === 0 ? <p className="muted small">No spending this month yet.</p> : (
            <div className="stack-sm">
              {data.top_categories.map((c) => (
                <div key={c.name} className="cat-bar">
                  <CategoryIcon icon={c.icon} color={c.color} size={30} />
                  <div className="cat-bar-main">
                    <div className="cat-bar-top"><span>{c.name}</span><Money value={c.total} /></div>
                    <div className="cat-bar-track"><div style={{ width: `${(c.total / data.top_categories[0].total) * 100}%`, background: c.color }} /></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Recent" action={<Link to="/activity" className="link">See all</Link>} className="span-2">
          {data.recent.length === 0 ? <p className="muted small">No transactions yet.</p> : <TransactionList items={data.recent} />}
        </Card>
      </div>
    </div>
  )
}
