import { ArrowDownRight, ArrowUpRight, CheckCircle2, ChevronRight, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PaceChart } from '../components/charts'
import PendingSubscriptions from '../components/PendingSubscriptions'
import TransactionList from '../components/TransactionList'
import { BillStatus } from './Bills'
import { LimitRow } from './Planner'
import { Badge, Card, CategoryIcon, Empty, ErrorNote, Money, Progress, Spinner } from '../components/ui'
import { daysUntil, fmtDate, money, monthName, toDate } from '../format'
import { useApp, useFetch } from '../state'

// How the month is going against the budget from the Planner.
//   weekly   what's left, spread evenly over the weeks that remain
//   onPace   the share of the budget used is no more than the share of the
//            month gone by (with 5% of slack)
function budgetPace(budget, spent, today) {
  const d = toDate(today)
  const daysInMonth = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()
  const day = d.getDate()
  const daysLeft = daysInMonth - day + 1 // counting today
  const remaining = budget - spent
  return {
    day, daysInMonth, daysLeft, remaining,
    weekly: Math.max(0, remaining) / Math.max(1, daysLeft / 7),
    daily: Math.max(0, remaining) / daysLeft,
    used: Math.min(1, spent / budget),
    over: remaining < 0,
    onPace: spent / budget <= day / daysInMonth + 0.05,
  }
}

function Hero({ data }) {
  const { family, today } = useApp()
  const s = data.spending
  const month = monthName(data.month)
  const diff = s.month - s.last_month_to_date
  // The budget is your personal limit from the Planner if you have one,
  // otherwise the family's everyday spending plan.
  const budget = data.budget?.amount
  const budgetSpent = data.budget?.spent ?? s.month
  const whose = data.budget?.kind === 'family' ? "the family's" : 'your'
  const pace = budget ? budgetPace(budget, budgetSpent, today) : null
  const lastWeek = pace && pace.daysLeft <= 7

  return (
    <section className="card glass-card hero">
      <div className="hero-main">
        {pace ? (
          <>
            <div className="hero-top">
              <span className="hero-label"><CheckCircle2 size={15} /> Safe to spend</span>
              <Badge tone={pace.over ? 'bad' : pace.onPace ? 'ok' : 'warn'}>
                {pace.over ? 'Over budget' : pace.onPace ? 'On pace' : 'Ahead of pace'}
              </Badge>
            </div>
            <div className="hero-value num">
              {money(lastWeek ? Math.max(0, pace.remaining) : pace.weekly)}
              <small>{lastWeek ? `left in ${month}` : '/ week'}</small>
            </div>
            <p className="hero-note">
              {pace.over ? (
                <>You've spent <strong>{money(-pace.remaining)}</strong> more than {whose} {money(budget)} budget for {month}.</>
              ) : pace.onPace ? (
                <><strong>{money(pace.remaining)}</strong> of {whose} {money(budget)} {month} budget is left, with {pace.daysLeft} day{pace.daysLeft === 1 ? '' : 's'} to go.</>
              ) : (
                <>Spending is running ahead of the month. About <strong>{money(pace.daily)}</strong> a day keeps you inside your budget.</>
              )}
            </p>
          </>
        ) : (
          <>
            <span className="hero-label">Spent in {month}</span>
            <div className="hero-value num">{money(s.month)}</div>
            <p className="hero-note">
              <Link to="/planner" className="link">Plan your budget</Link> to see how much is safe to spend each week.
            </p>
          </>
        )}
      </div>

      <div className="hero-panel">
        {pace && (
          <>
            <div className="hero-row">
              <span>{data.budget.kind === 'family' ? 'Family spent' : data.budget.kind === 'personal' ? 'Personal spending' : `Spent in ${month}`}: <strong className="num">{money(budgetSpent)}</strong></span>
              <span>Budget: <strong className="num">{money(budget)}</strong></span>
            </div>
            <div className={`pace-track ${pace.over ? 'over' : ''}`}><div style={{ width: `${pace.used * 100}%` }} /></div>
            <div className="hero-row small">
              <span>Day {pace.day} of {pace.daysInMonth}</span>
              <span>{Math.round(pace.used * 100)}% of budget used</span>
            </div>
          </>
        )}
        <span className={`hero-compare ${diff > 0 ? 'up' : 'down'}`}>
          {s.last_month_to_date === 0 && s.month === 0 ? 'Nothing spent yet this month' : (
            <>
              {diff > 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
              {money(Math.abs(diff))} {diff > 0 ? 'more' : 'less'} than this time last month
            </>
          )}
        </span>
        <div className="hero-stats">
          <div><span className="muted small">This week ({fmtDate(s.week_start)}–{fmtDate(s.week_end)})</span><strong>{money(s.week)}</strong></div>
          <div><span className="muted small">Bills paid</span><strong>{money(s.bills_paid)}</strong></div>
          {family.length > 1 && (
            <div><span className="muted small">Family this month</span><strong>{money(s.family_month)}</strong></div>
          )}
        </div>
      </div>
    </section>
  )
}

export default function Dashboard() {
  const { today, openSheet, meta } = useApp()
  const { data, error, reload } = useFetch('/dashboard')

  if (error) return <ErrorNote error={error} onRetry={reload} />
  if (!data) return <div className="center-pad"><Spinner /></div>

  const billsSummary = data.bills.summary
  const isNewUser = meta.cards.length === 0 && meta.categories.length === 0
  const unscheduled = meta.bills.filter((b) => b.active && b.due_day == null).length
  const payBill = (b) => openSheet({ type: 'bill-payment', bill: b, month: data.month })
  // Unpaid bills that are overdue or due within a week.
  const dueSoon = data.bills.open.filter((b) => b.due_date && daysUntil(b.due_date, today) <= 7)

  return (
    <div className="page dashboard">
      {isNewUser && (
        <Card className="welcome glass-card">
          <h2>Welcome to SpendU 👋</h2>
          <p className="muted">Start by adding a transaction — you can create your cards and categories right in the form.</p>
          <button className="btn primary" onClick={() => openSheet({ type: 'transaction' })}><Plus size={16} /> Add your first transaction</button>
        </Card>
      )}

      <Hero data={data} />

      {dueSoon.length > 0 && (
        <section className="stack-sm">
          <div className="row between">
            <h2 className="section-label">Due soon</h2>
            <Link to="/bills" className="link">All bills <ChevronRight size={14} /></Link>
          </div>
          <div className="due-strip no-scrollbar">
            {dueSoon.map((b) => (
              <div key={b.bill_id} className="card glass-card due-tile">
                <div className="row between">
                  <BillStatus status={b.status} />
                  <span className="muted small num">{fmtDate(b.due_date)}</span>
                </div>
                <div>
                  <div className="tx-title">{b.name}</div>
                  <strong className="num">{b.expected ? money(b.expected) : 'Amount varies'}</strong>
                </div>
                <button className="btn small secondary" onClick={() => payBill(b)}><CheckCircle2 size={14} /> Mark paid</button>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="dash-grid">
        {data.pending_recurring.length > 0 && (
          <Card title="Subscriptions to confirm" action={<Link to="/subscriptions" className="link">All</Link>} className="glass-card">
            <PendingSubscriptions items={data.pending_recurring} />
          </Card>
        )}

        <Card title={`${monthName(data.month)} bills`} action={<Link to="/bills" className="link">Checklist <ChevronRight size={14} /></Link>} className="glass-card">
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
                    <button className="btn small secondary" onClick={() => payBill(b)}>Pay</button>
                  </div>
                ))}
                {data.bills.open.length === 0 && <p className="muted small">All paid for this month 🎉</p>}
              </div>
            </>
          )}
        </Card>

        <Card title="Budget" action={<Link to="/planner" className="link">Planner</Link>} className="glass-card">
          {data.budgets.length === 0 ? (
            <Empty title="No budget plan yet"><Link to="/planner" className="link">Plan your monthly budget</Link></Empty>
          ) : (
            <div className="stack-sm">{data.budgets.map((b) => <LimitRow key={b.line_id} b={b} />)}</div>
          )}
        </Card>

        <Card title="Spending pace" className="glass-card">
          <PaceChart thisMonth={data.pace.this_month} lastMonth={data.pace.last_month} />
        </Card>

        <Card title="Top categories" action={<Link to="/insights" className="link">Insights</Link>} className="glass-card">
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

        <Card title="Recent" action={<Link to="/activity" className="link">See all</Link>} className="span-2 glass-card">
          {data.recent.length === 0 ? <p className="muted small">No transactions yet.</p> : <TransactionList items={data.recent} />}
        </Card>
      </div>
    </div>
  )
}
