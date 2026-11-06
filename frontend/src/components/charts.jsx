// Chart.js wrappers that follow the app's light/dark theme.
import {
  ArcElement, BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LinearScale, LineElement,
  PointElement, Tooltip,
} from 'chart.js'
import { useEffect, useState } from 'react'
import { Bar, Doughnut, Line } from 'react-chartjs-2'
import { money, moneyShort } from '../format'

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, LineElement, PointElement, Filler, Tooltip, Legend)

// Re-read CSS colours when the theme changes.
function useThemeColors() {
  const read = () => {
    const s = getComputedStyle(document.documentElement)
    return {
      text: s.getPropertyValue('--muted').trim() || '#64748b',
      grid: s.getPropertyValue('--border').trim() || '#e5e7eb',
      accent: s.getPropertyValue('--accent').trim() || '#5b5bd6',
      surface: s.getPropertyValue('--surface').trim() || '#fff',
      faint: s.getPropertyValue('--faint').trim() || '#cbd5e1',
    }
  }
  const [colors, setColors] = useState(read)
  useEffect(() => {
    const update = () => setColors(read())
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', update)
    const obs = new MutationObserver(update)
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => { mq.removeEventListener('change', update); obs.disconnect() }
  }, [])
  return colors
}

const tooltip = { callbacks: { label: (ctx) => ` ${ctx.dataset.label ? ctx.dataset.label + ': ' : ''}${money(ctx.parsed.y ?? ctx.parsed)}` } }

export function DonutChart({ items, center }) {
  const c = useThemeColors()
  const data = {
    labels: items.map((i) => i.name),
    datasets: [{ data: items.map((i) => Math.max(0, i.total)), backgroundColor: items.map((i) => i.color),
      borderColor: c.surface, borderWidth: 2, hoverOffset: 6 }],
  }
  return (
    <div className="donut">
      <Doughnut data={data} options={{
        cutout: '72%', maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${money(ctx.parsed)}` } } },
      }} />
      {center && <div className="donut-center">{center}</div>}
    </div>
  )
}

export function BarChart({ labels, datasets, stacked = false, height = 240, horizontal = false }) {
  const c = useThemeColors()
  const valueAxis = { stacked, grid: { color: c.grid }, border: { display: false },
    ticks: { color: c.text, callback: (v) => moneyShort(v), maxTicksLimit: 5 } }
  const labelAxis = { stacked, grid: { display: false }, border: { display: false }, ticks: { color: c.text, maxRotation: 0, autoSkip: true } }
  return (
    <div style={{ height }}>
      <Bar data={{ labels, datasets: datasets.map((d) => ({ borderRadius: 6, maxBarThickness: 36, ...d })) }}
        options={{
          indexAxis: horizontal ? 'y' : 'x', maintainAspectRatio: false,
          plugins: { legend: { display: datasets.length > 1, position: 'bottom', labels: { color: c.text, boxWidth: 10, boxHeight: 10, useBorderRadius: true, borderRadius: 3 } },
            tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label ? ctx.dataset.label + ': ' : ''}${money(horizontal ? ctx.parsed.x : ctx.parsed.y)}` } } },
          scales: horizontal ? { x: valueAxis, y: labelAxis } : { x: labelAxis, y: valueAxis },
        }} />
    </div>
  )
}

export function PaceChart({ thisMonth, lastMonth, height = 120 }) {
  const c = useThemeColors()
  const days = Math.max(thisMonth.length, lastMonth.length)
  const labels = Array.from({ length: days }, (_, i) => i + 1)
  return (
    <div style={{ height }}>
      <Line data={{
        labels,
        datasets: [
          { label: 'This month', data: thisMonth, borderColor: c.accent, backgroundColor: c.accent + '22', fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2.5 },
          { label: 'Last month', data: lastMonth, borderColor: c.faint, borderDash: [4, 4], tension: 0.3, pointRadius: 0, borderWidth: 2 },
        ],
      }} options={{
        maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { ...tooltip, callbacks: { ...tooltip.callbacks, title: (i) => `Day ${i[0].label}` } } },
        scales: { x: { display: false }, y: { display: false, beginAtZero: true } },
      }} />
    </div>
  )
}
