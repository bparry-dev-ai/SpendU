// Small building blocks used across pages.
import { motion, useDragControls } from 'framer-motion'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { money, monthLabel, shiftMonth } from '../format'

export const Spinner = () => <div className="spinner" role="status" aria-label="Loading" />

export function Card({ title, action, children, className = '', pad = true }) {
  return (
    <section className={`card ${pad ? 'pad' : ''} ${className}`}>
      {(title || action) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

export function Money({ value, signed = false, className = '' }) {
  // Refunds are stored negative: show them as "+$5.00" in green.
  if (signed && value < 0) return <span className={`money credit ${className}`}>+{money(-value)}</span>
  return <span className={`money ${className}`}>{money(value)}</span>
}

export function Badge({ tone = 'neutral', children }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export function Progress({ value, tone, marker }) {
  const width = Math.min(100, Math.max(0, (value || 0) * 100))
  return (
    <div className="progress">
      <div className={`progress-fill ${tone || ''}`} style={{ width: `${width}%` }} />
      {marker !== undefined && marker > 0 && marker < 1 && (
        <div className="progress-marker" style={{ left: `${marker * 100}%` }} title="How far through the month we are" />
      )}
    </div>
  )
}

export function Segmented({ options, value, onChange, size }) {
  return (
    <div className={`segmented ${size || ''}`} role="tablist">
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={value === o.value}
          className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Field({ label, hint, children, error }) {
  return (
    <label className="field">
      {label && <span className="field-label">{label}</span>}
      {children}
      {hint && !error && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </label>
  )
}

export function Empty({ icon, title, children, action }) {
  return (
    <div className="empty">
      {icon && <div className="empty-icon">{icon}</div>}
      <p className="empty-title">{title}</p>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  )
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="error-note">
      <span>{error.message}</span>
      {onRetry && <button className="link" onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function MonthSwitcher({ month, onChange, max }) {
  return (
    <div className="month-switcher">
      <button className="icon-btn" aria-label="Previous month" onClick={() => onChange(shiftMonth(month, -1))}>
        <ChevronLeft size={18} />
      </button>
      <span>{monthLabel(month)}</span>
      <button className="icon-btn" aria-label="Next month" disabled={max && month >= max}
        onClick={() => onChange(shiftMonth(month, 1))}>
        <ChevronRight size={18} />
      </button>
    </div>
  )
}

export function Dot({ color, size = 10 }) {
  return <span className="dot" style={{ background: color, width: size, height: size }} />
}

export function CategoryIcon({ icon, color, size = 36 }) {
  return (
    <span className="cat-icon" style={{ '--c': color || 'var(--muted)', width: size, height: size }}>
      {icon || <Dot color={color} size={size / 3.2} />}
    </span>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}

// Modal: a bottom sheet on phones, a centred dialog on larger screens.
export function Sheet({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.classList.add('no-scroll')
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.classList.remove('no-scroll')
    }
  }, [onClose])

  // Dragging starts from the grab bar only, so scrolling or selecting text
  // inside the sheet never moves it. Let go far or fast enough and it closes.
  const dragControls = useDragControls()
  const handleDragEnd = (_, info) => {
    if (info.offset.y > 90 || info.velocity.y > 400) onClose()
  }

  return (
    <motion.div
      className="sheet-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        className={`sheet ${wide ? 'wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        initial={{ y: 35, opacity: 0.85, scale: 0.98 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        transition={{ type: 'spring', damping: 28, stiffness: 340 }}
        drag="y"
        dragControls={dragControls}
        dragListener={false}
        dragConstraints={{ top: 0, bottom: 0 }}
        dragElastic={{ top: 0.04, bottom: 0.6 }}
        onDragEnd={handleDragEnd}
      >
        <div className="sheet-drag-handle" title="Drag down to close" onPointerDown={(e) => dragControls.start(e)} />
        <header className="sheet-head">
          <h2>{title}</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}><X size={20} /></button>
        </header>
        <div className="sheet-body">{children}</div>
        {footer && <footer className="sheet-foot">{footer}</footer>}
      </motion.div>
    </motion.div>
  )
}

// A delete button that asks "Sure?" on the first tap instead of a browser popup.
export function ConfirmButton({ onConfirm, children = 'Delete', confirmText = 'Tap again to confirm', className = 'btn danger-ghost' }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(false), 3000)
    return () => clearTimeout(t)
  }, [armed])
  return (
    <button type="button" className={`${className} ${armed ? 'armed' : ''}`}
      onClick={() => (armed ? onConfirm() : setArmed(true))}>
      {armed ? confirmText : children}
    </button>
  )
}

export function Pills({ items, value, onChange, getKey, getLabel, getColor, extra }) {
  return (
    <div className="pills">
      {items.map((item) => {
        const key = getKey(item)
        return (
          <button key={key} type="button" className={`pill ${value === key ? 'on' : ''}`}
            style={getColor ? { '--c': getColor(item) } : undefined} onClick={() => onChange(key)}>
            {getColor && <Dot color={getColor(item)} size={8} />}
            {getLabel(item)}
          </button>
        )
      })}
      {extra}
    </div>
  )
}

export function Stat({ label, value, sub, tone }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className={`stat-value ${tone || ''}`}>{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  )
}
