// Insights: where the money goes (breakdown), how it changes (trends), and
// when it happens (calendar).
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { useState } from 'react'
import { query } from '../api'
import { BarChart, DonutChart } from '../components/charts'
import TransactionList from '../components/TransactionList'
import { Card, CategoryIcon, Dot, Empty, ErrorNote, Money, MonthSwitcher, PageHeader, Segmented, Sheet, Spinner, Stat } from '../components/ui'
import { addDays, fmtDate, fmtDateLong, money, monthLabel, moneyShort, shiftMonth, toDate } from '../format'
import { useApp, useFetch } from '../state'

const PERIODS = [
  { value: 'this_month', label: 'This month' },
  { value: 'last_month', label: 'Last month' },
  { value: '3_months', label: '3 months' },
  { value: 'this_year', label: 'This year' },
  { value: 'custom', label: 'Custom' },
]

function periodRange(p, today, custom) {
  const m = today.slice(0, 7)
  if (p === 'this_month') return { start: `${m}-01`, end: today }
  if (p === 'last_month') return { start: `${shiftMonth(m, -1)}-01`, end: addDays(`${m}-01`, -1) }
  if (p === '3_months') return { start: `${shiftMonth(m, -2)}-01`, end: today }
  if (p === 'this_year') return { start: `${today.slice(0, 4)}-01-01`, end: today }
  return custom
}

function Breakdown() {
  const { today } = useApp()
  const [period, setPeriod] = useState('this_month')
  const [custom, setCustom] = useState({ start: `${today.slice(0, 7)}-01`, end: today })
  const [includeBills, setIncludeBills] = useState(false)
  const range = periodRange(period, today, custom)
  const { data, error, reload } = useFetch('/analytics/summary' + query({ ...range, include_bills: includeBills ? 1 : '' }))

  return (
    <div className="stack">
      <div className="toolbar wrap">
        <select className="input auto" value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        {period === 'custom' && (
          <>
            <input className="input auto" type="date" value={custom.start} onChange={(e) => setCustom({ ...custom, start: e.target.value })} />
            <input className="input auto" type="date" value={custom.end} onChange={(e) => setCustom({ ...custom, end: e.target.value })} />
          </>
        )}
        <label className="check"><input type="checkbox" checked={includeBills} onChange={(e) => setIncludeBills(e.target.checked)} /> Include bills</label>
      </div>
      <ErrorNote error={error} onRetry={reload} />
      {!data ? <div className="center-pad"><Spinner /></div> : (
        <>
          <div className="stats-row card pad">
            <Stat label={includeBills ? 'Spending + bills' : 'Spending'} value={money(data.total)} sub={`${fmtDate(data.start)} – ${fmtDate(data.end)}`} />
            <Stat label="Refunds" value={money(data.refunds_total)} tone="credit" />
            {!includeBills && <Stat label="Bills (separate)" value={money(data.bills_total)}
              sub={data.bill_refunds_total ? `after ${money(data.bill_refunds_total)} bill refunds` : undefined} />}
          </div>
          {data.by_category.length === 0 ? <Empty icon="📊" title="No spending in this period" /> : (
            <div className="grid-2 cards">
              <Card title="By category">
                <DonutChart items={data.by_category} center={<><span className="muted small">Total</span><strong>{moneyShort(data.total)}</strong></>} />
                <div className="legend">
                  {data.by_category.map((c) => (
                    <div key={c.name} className="legend-row">
                      <CategoryIcon icon={c.icon} color={c.color} size={28} />
                      <span className="legend-name">{c.name}<span className="muted small"> · {c.count}</span></span>
                      <span className="muted small">{data.total > 0 ? Math.round((c.total / data.total) * 100) : 0}%</span>
                      <Money value={c.total} />
                    </div>
                  ))}
                </div>
              </Card>
              <div className="stack">
                <Card title="By card">
                  <BarChart horizontal height={Math.max(120, data.by_card.length * 46)} labels={data.by_card.map((c) => c.name)}
                    datasets={[{ data: data.by_card.map((c) => c.total), backgroundColor: data.by_card.map((c) => c.color) }]} />
                  <div className="legend">
                    {data.by_card.map((c) => (
                      <div key={c.card_id} className="legend-row">
                        <Dot color={c.color} /><span className="legend-name">{c.name}<span className="muted small"> · {c.count} transactions</span></span>
                        <Money value={c.total} />
                      </div>
                    ))}
                  </div>
                </Card>
                {data.top_merchants.length > 0 && (
                  <Card title="Top merchants">
                    {data.top_merchants.map((m) => (
                      <div key={m.name} className="legend-row">
                        <span className="legend-name">{m.name}<span className="muted small"> · {m.count}×</span></span>
                        <Money value={m.total} />
                      </div>
                    ))}
                  </Card>
                )}
              </div>
              {data.daily.length > 1 && data.daily.length <= 120 && (
                <Card title="Day by day" className="span-2">
                  <BarChart height={200} labels={data.daily.map((d) => fmtDate(d.date))}
                    datasets={[{ label: 'Spent', data: data.daily.map((d) => d.total), backgroundColor: 'rgba(91,91,214,0.75)' }]} />
                </Card>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Trends() {
  const [months, setMonths] = useState(12)
  const { data, error, reload } = useFetch(`/analytics/trends?months=${months}`)
  if (error) return <ErrorNote error={error} onRetry={reload} />
  if (!data) return <div className="center-pad"><Spinner /></div>
  const labels = data.months.map((m) => monthLabel(m, true))
  const n = data.spending.length
  const avg = data.spending.slice(0, -1).reduce((a, b) => a + b, 0) / Math.max(1, n - 1)

  return (
    <div className="stack">
      <div className="toolbar">
        <Segmented size="sm" value={months} onChange={setMonths} options={[{ value: 6, label: '6 months' }, { value: 12, label: '12 months' }, { value: 24, label: '2 years' }]} />
      </div>
      <div className="stats-row card pad">
        <Stat label="This month so far" value={money(data.spending[n - 1])} />
        <Stat label="Last month" value={money(data.spending[n - 2])} />
        <Stat label={`Monthly average (${n - 1} mo)`} value={money(avg)} />
      </div>
      <Card title="Spending by category, per month">
        <BarChart stacked height={300} labels={labels}
          datasets={data.categories.map((c) => ({ label: c.name, data: c.values, backgroundColor: c.color, borderRadius: 2 }))} />
      </Card>
      <Card title="Spending vs bills">
        <BarChart height={240} labels={labels} datasets={[
          { label: 'Spending', data: data.spending, backgroundColor: 'rgba(91,91,214,0.8)' },
          { label: 'Bills', data: data.bills, backgroundColor: 'rgba(148,163,184,0.8)' },
        ]} />
      </Card>
      <Card title="This month vs last month">
        {data.compare.length === 0 ? <p className="muted small">No spending in the last two months.</p> : (
          <table className="table">
            <thead><tr><th>Category</th><th className="num">Last month</th><th className="num">This month</th><th className="num">Change</th></tr></thead>
            <tbody>
              {data.compare.map((c) => (
                <tr key={c.name}>
                  <td><Dot color={c.color} /> {c.name}</td>
                  <td className="num">{money(c.last_month)}</td>
                  <td className="num">{money(c.this_month)}</td>
                  <td className={`num ${c.change > 0 ? 'up' : 'down'}`}>
                    {c.change > 0 ? <ArrowUpRight size={14} /> : c.change < 0 ? <ArrowDownRight size={14} /> : null}
                    {money(Math.abs(c.change))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

function DayDetail({ day, onClose }) {
  const { data } = useFetch(`/transactions?start=${day}&end=${day}&page_size=100`)
  return (
    <Sheet title={fmtDateLong(day)} onClose={onClose}>
      {!data ? <Spinner /> : data.items.length === 0 ? <p className="muted">Nothing on this day.</p> : <TransactionList items={data.items} grouped={false} />}
    </Sheet>
  )
}

function Calendar() {
  const { today } = useApp()
  const [month, setMonth] = useState(today.slice(0, 7))
  const [day, setDay] = useState(null)
  const { data, error, reload } = useFetch(`/analytics/calendar?month=${month}`)
  if (error) return <ErrorNote error={error} onRetry={reload} />

  const first = toDate(`${month}-01`)
  const lead = (first.getDay() + 6) % 7 // Monday-first grid
  const daysInMonth = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
  const max = data ? Math.max(1, ...Object.values(data.days).map((d) => d.spent)) : 1

  return (
    <div className="stack">
      <div className="row between wrap">
        <MonthSwitcher month={month} onChange={setMonth} />
        {data && <span className="muted">Spent <strong>{money(data.total)}</strong></span>}
      </div>
      {!data ? <div className="center-pad"><Spinner /></div> : (
        <div className="card pad">
          <div className="calendar">
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="cal-head">{d}</div>)}
            {Array.from({ length: lead }, (_, i) => <div key={`x${i}`} />)}
            {Array.from({ length: daysInMonth }, (_, i) => {
              const date = `${month}-${String(i + 1).padStart(2, '0')}`
              const info = data.days[date]
              const bills = data.bills.filter((b) => b.due_date === date)
              const subs = data.subscriptions.filter((s) => s.date === date)
              const heat = info ? 0.12 + 0.6 * (info.spent / max) : 0
              return (
                <button key={date} className={`cal-day ${date === today ? 'today' : ''}`} onClick={() => setDay(date)}
                  style={info && info.spent > 0 ? { '--heat': heat } : undefined}>
                  <span className="cal-num">{i + 1}</span>
                  {info && <span className="cal-amt">{moneyShort(info.spent)}</span>}
                  <span className="cal-marks">
                    {bills.map((b) => <span key={b.bill_id} className={`cal-mark bill ${b.status}`} title={`${b.name} (${b.status.replace('_', ' ')})`} />)}
                    {subs.map((s) => <span key={s.name} className="cal-mark sub" title={`${s.name} renews`} />)}
                  </span>
                </button>
              )
            })}
          </div>
          <div className="cal-legend muted small">
            <span><span className="cal-mark bill paid" /> Bill paid</span>
            <span><span className="cal-mark bill upcoming" /> Bill due</span>
            <span><span className="cal-mark bill overdue" /> Overdue</span>
            <span><span className="cal-mark sub" /> Subscription</span>
          </div>
        </div>
      )}
      {data && (data.bills.length > 0 || data.subscriptions.length > 0) && (
        <Card title="Due this month">
          {[...data.bills.map((b) => ({ ...b, date: b.due_date, type: 'Bill' })), ...data.subscriptions.map((s) => ({ ...s, type: 'Subscription' }))]
            .sort((a, b) => a.date.localeCompare(b.date))
            .map((x) => (
              <div key={x.type + x.name} className="history-row">
                <span>{fmtDate(x.date)}</span><span>{x.name} <span className="muted small">· {x.type}{x.status ? ` · ${x.status.replace('_', ' ')}` : ''}</span></span>
                {x.amount ? <Money value={x.amount} /> : <span />}
              </div>
            ))}
        </Card>
      )}
      {day && <DayDetail day={day} onClose={() => setDay(null)} />}
    </div>
  )
}

export default function Insights() {
  const [tab, setTab] = useState('breakdown')
  return (
    <div className="page">
      <PageHeader title="Insights" subtitle="Your spending by category, card, month and day." />
      <Segmented value={tab} onChange={setTab} options={[
        { value: 'breakdown', label: 'Breakdown' }, { value: 'trends', label: 'Trends' }, { value: 'calendar', label: 'Calendar' },
      ]} />
      {tab === 'breakdown' && <Breakdown />}
      {tab === 'trends' && <Trends />}
      {tab === 'calendar' && <Calendar />}
    </div>
  )
}
