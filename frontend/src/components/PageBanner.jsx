// The synthwave horizon banner at the top of every page: "SPENDU / PAGE", a
// one-line subtitle, and the date and time. The artwork is one SVG drawn
// with a dark-mode or light-mode palette.
import { useEffect, useState } from 'react'
import { useTheme } from '../state'

const PALETTES = {
  dark: {
    sun: ['#ff007f', '#ff007f', '#ffb703'],
    stars: ['#fff', '#00e5ff', '#fff', '#fff', '#ff007f', '#fff'],
    mountainLeft: ['#1e1b4b', '#090d16'], ridgeLeft: '#8b5cf6',
    mountainRight: ['#311042', '#090d16'], ridgeRight: '#ec4899',
    horizon: ['#ff007f', '#00f59b', '#00e5ff'],
    grid: ['#00f59b', '#00e5ff', '#00e5ff'], centerLine: '#00f59b',
  },
  light: {
    sky: ['#dbeafe', '#ecfdf5', '#fef3c7'],
    sun: ['#f59e0b', '#f97316', '#ef4444'],
    stars: ['#0284c7', '#059669', '#f59e0b', '#059669', '#6366f1', '#0284c7'],
    mountainLeft: ['#a7f3d0', '#059669'], ridgeLeft: '#047857',
    mountainRight: ['#c7d2fe', '#4f46e5'], ridgeRight: '#4338ca',
    horizon: ['#f59e0b', '#10b981', '#06b6d4'],
    grid: ['#10b981', '#0d9488', '#059669'], centerLine: '#059669',
  },
}

const STARS = [[30, 14, 0.9], [80, 10, 1.2], [140, 18, 0.8], [270, 12, 1.1], [330, 20, 1.3], [380, 12, 0.8]]
const GRID_RAYS = [-25, 20, 65, 110, 155, 245, 290, 335, 380, 425] // where each floor line meets the bottom edge
const GRID_ROWS = [[51, 0.3], [56, 0.45], [64, 0.6], [76, 0.8], [91, 0.95]]
const LEFT_RIDGE = '0,48 45,24 95,40 145,20 195,48'
const RIGHT_RIDGE = '205,48 255,22 305,40 355,24 400,48'

function Gradient({ id, stops, horizontal, opacities }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2={horizontal ? 1 : 0} y2={horizontal ? 0 : 1}>
      {stops.map((color, i) => (
        <stop key={i} offset={`${(i / (stops.length - 1)) * 100}%`} stopColor={color} stopOpacity={opacities?.[i]} />
      ))}
    </linearGradient>
  )
}

function HorizonArt({ palette: p }) {
  return (
    <svg className="w-full h-full" viewBox="0 0 400 95" preserveAspectRatio="xMidYMid slice" fill="none" aria-hidden="true">
      <defs>
        {p.sky && <Gradient id="bannerSky" stops={p.sky} opacities={[0.75, 0.5, 0.4]} />}
        <Gradient id="bannerSun" stops={p.sun} />
        <Gradient id="bannerMountainLeft" stops={p.mountainLeft} opacities={[0.9, 0.95]} />
        <Gradient id="bannerMountainRight" stops={p.mountainRight} opacities={[0.9, 0.95]} />
        <Gradient id="bannerHorizon" horizontal stops={['transparent', ...p.horizon, 'transparent']} />
        <Gradient id="bannerGrid" stops={p.grid} opacities={[0.15, 0.45, 0.85]} />
      </defs>

      {p.sky && <rect width="400" height="95" fill="url(#bannerSky)" />}
      {STARS.map(([cx, cy, r], i) => <circle key={i} cx={cx} cy={cy} r={r} fill={p.stars[i]} opacity="0.6" />)}

      {/* The sliced sun */}
      <g fill="url(#bannerSun)">
        <path d="M 182 18 A 22 22 0 0 1 218 18 Z" />
        <path d="M 179 23 H 221 A 22 22 0 0 1 222.5 27 H 177.5 A 22 22 0 0 1 179 23 Z" />
        <path d="M 178 31 H 222 A 22 22 0 0 1 222.5 36 H 177.5 A 22 22 0 0 1 178 31 Z" />
        <path d="M 178 40 H 222 A 22 22 0 0 1 221 47 H 179 A 22 22 0 0 1 178 40 Z" />
      </g>

      <polygon points={LEFT_RIDGE} fill="url(#bannerMountainLeft)" />
      <polyline points={LEFT_RIDGE} stroke={p.ridgeLeft} strokeWidth="1.2" opacity="0.75" />
      <polygon points={RIGHT_RIDGE} fill="url(#bannerMountainRight)" />
      <polyline points={RIGHT_RIDGE} stroke={p.ridgeRight} strokeWidth="1.2" opacity="0.75" />

      <line x1="0" y1="48" x2="400" y2="48" stroke="url(#bannerHorizon)" strokeWidth="2" />

      {/* Perspective grid floor */}
      <g stroke="url(#bannerGrid)" strokeWidth="1.1" opacity="0.8">
        {GRID_RAYS.map((x) => <line key={x} x1="200" y1="48" x2={x} y2="95" />)}
        <line x1="200" y1="48" x2="200" y2="95" stroke={p.centerLine} strokeWidth="1.8" />
        {GRID_ROWS.map(([y, opacity]) => <line key={y} x1="0" y1={y} x2="400" y2={y} opacity={opacity} />)}
      </g>
    </svg>
  )
}

export default function PageBanner({ title, subtitle }) {
  const { isDark } = useTheme()
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000)
    return () => clearInterval(timer)
  }, [])

  return (
    <header className="page-banner">
      <HorizonArt palette={isDark ? PALETTES.dark : PALETTES.light} />
      <div className="page-banner-text">
        <div>
          <div className="page-banner-title">
            <span>SpendU</span><span>/</span><span>{title}</span>
          </div>
          <div className="page-banner-sub">{subtitle}</div>
        </div>
        <div className="page-banner-clock">
          <div>{now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}</div>
          <strong>{now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}</strong>
        </div>
      </div>
    </header>
  )
}
