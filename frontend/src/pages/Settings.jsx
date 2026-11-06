import { browserSupportsWebAuthn, startRegistration } from '@simplewebauthn/browser'
import { Archive, ArchiveRestore, Download, LogOut, Plus, ScanFace, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { del, patch, post } from '../api'
import { Card, ConfirmButton, Field, PageHeader, Segmented } from '../components/ui'
import { fmtDate } from '../format'
import { useApp, useFetch } from '../state'

const SWATCHES = ['#6366f1', '#14b8a6', '#f59e0b', '#ec4899', '#22c55e', '#3b82f6', '#ef4444', '#a855f7', '#06b6d4', '#84cc16', '#f97316', '#64748b']

function ThemePicker() {
  const read = () => { try { return localStorage.getItem('spendu-theme') || 'system' } catch { return 'system' } }
  const [theme, setTheme] = useState(read)
  useEffect(() => {
    if (theme === 'system') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
    try { localStorage.setItem('spendu-theme', theme) } catch { /* private mode */ }
  }, [theme])
  return <Segmented value={theme} onChange={setTheme} options={[{ value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]} />
}

function LookupManager({ kind, items, idKey, label, withIcon }) {
  const { setMeta, changed, notify } = useApp()
  const [name, setName] = useState('')
  const [editing, setEditing] = useState(null)

  const run = async (fn, msg) => {
    try {
      const res = await fn()
      setMeta((m) => ({ ...m, cards: res.cards, categories: res.categories, bills: res.bills }))
      changed()
      if (msg) notify(msg)
      return true
    } catch (e) {
      notify(e.message, 'error')
      return false
    }
  }
  const add = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    if (await run(() => post(`/${kind}`, { name }), `${label} added`)) setName('')
  }

  return (
    <div className="stack-sm">
      <form className="row" onSubmit={add}>
        <input className="input" value={name} maxLength={50} placeholder={`New ${label.toLowerCase()} name`} onChange={(e) => setName(e.target.value)} />
        <button className="btn primary"><Plus size={16} /> Add</button>
      </form>
      {items.map((item) => {
        const id = item[idKey]
        const isEditing = editing?.id === id
        return (
          <div key={id} className={`lookup-row ${item.archived ? 'archived' : ''}`}>
            <div className="swatch-wrap">
              <button className="swatch" style={{ background: item.color }} aria-label="Change colour"
                onClick={() => setEditing(isEditing ? null : { id, name: item.name, icon: item.icon || '' })} />
            </div>
            {isEditing ? (
              <form className="lookup-edit" onSubmit={async (e) => {
                e.preventDefault()
                const body = { name: editing.name }
                if (withIcon) body.icon = editing.icon
                if (await run(() => patch(`/${kind}/${id}`, body), 'Saved')) setEditing(null)
              }}>
                {withIcon && <input className="input emoji" value={editing.icon} maxLength={4} placeholder="🙂" onChange={(e) => setEditing({ ...editing, icon: e.target.value })} aria-label="Emoji icon" />}
                <input className="input" value={editing.name} maxLength={50} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                <div className="swatches">
                  {SWATCHES.map((c) => (
                    <button type="button" key={c} className={`swatch sm ${item.color === c ? 'on' : ''}`} style={{ background: c }}
                      onClick={() => run(() => patch(`/${kind}/${id}`, { color: c }))} aria-label={`Colour ${c}`} />
                  ))}
                </div>
                <div className="row">
                  <ConfirmButton className="btn small danger-ghost" onConfirm={() => run(() => del(`/${kind}/${id}`), `${label} deleted`)}>
                    <Trash2 size={14} /> Delete
                  </ConfirmButton>
                  <span className="spacer" />
                  <button type="button" className="btn small ghost" onClick={() => setEditing(null)}>Cancel</button>
                  <button className="btn small primary">Save</button>
                </div>
              </form>
            ) : (
              <>
                <button className="lookup-name" onClick={() => setEditing({ id, name: item.name, icon: item.icon || '' })}>
                  {item.icon ? `${item.icon} ` : ''}{item.name}{item.archived ? <span className="muted small"> · archived</span> : null}
                </button>
                <button className="icon-btn" title={item.archived ? 'Unarchive' : 'Archive (hide from pickers)'}
                  onClick={() => run(() => patch(`/${kind}/${id}`, { archived: !item.archived }), item.archived ? 'Restored' : 'Archived')}>
                  {item.archived ? <ArchiveRestore size={16} /> : <Archive size={16} />}
                </button>
              </>
            )}
          </div>
        )
      })}
    </div>
  )
}

function Passkeys() {
  const { notify } = useApp()
  const { data, reload } = useFetch('/auth/passkeys')
  const supported = browserSupportsWebAuthn()
  const add = async () => {
    try {
      const options = await post('/auth/passkey/register/begin')
      const attestation = await startRegistration(options)
      await post('/auth/passkey/register/complete', attestation)
      notify('Face ID added — use it next time you sign in')
      reload()
    } catch (e) {
      if (e.name === 'NotAllowedError') return
      if (e.name === 'InvalidStateError') return notify('This device already has a passkey for SpendU.')
      notify(e.message || 'Could not add Face ID on this device.', 'error')
    }
  }
  return (
    <div className="stack-sm">
      {data?.passkeys.map((p, i) => (
        <div key={p.credential_id} className="lookup-row">
          <ScanFace size={18} className="muted" />
          <span className="lookup-name static">Passkey {i + 1} <span className="muted small">· added {fmtDate(p.created, { month: 'short', day: 'numeric', year: 'numeric' })}</span></span>
          <ConfirmButton className="btn small danger-ghost" onConfirm={async () => { await del(`/auth/passkeys/${encodeURIComponent(p.credential_id)}`); reload() }}>Remove</ConfirmButton>
        </div>
      ))}
      {supported ? (
        <button className="btn secondary" onClick={add}><ScanFace size={16} /> Add Face ID / passkey on this device</button>
      ) : (
        <p className="muted small">Passkeys need HTTPS on a real domain (e.g. via Tailscale) and a supported browser.</p>
      )}
    </div>
  )
}

function PasswordForm() {
  const { notify } = useApp()
  const [form, setForm] = useState({ current: '', new: '', confirm: '' })
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (form.new !== form.confirm) return setError("New passwords don't match.")
    try {
      await post('/auth/password', form)
      setForm({ current: '', new: '', confirm: '' })
      notify('Password changed')
    } catch (err) {
      setError(err.message)
    }
  }
  return (
    <form className="stack-sm" onSubmit={submit}>
      <input className="input" type="password" autoComplete="current-password" placeholder="Current password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} required />
      <input className="input" type="password" autoComplete="new-password" placeholder="New password (8+ characters)" value={form.new} onChange={(e) => setForm({ ...form, new: e.target.value })} required minLength={8} />
      <input className="input" type="password" autoComplete="new-password" placeholder="Confirm new password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} required />
      {error && <p className="form-error">{error}</p>}
      <button className="btn secondary">Change password</button>
    </form>
  )
}

export default function Settings() {
  const { user, meta, setSession, notify } = useApp()
  const zones = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : [user.timezone]

  const setTimezone = async (tz) => {
    try {
      setSession(await patch('/auth/settings', { timezone: tz }))
      notify(`Timezone set to ${tz.replace('_', ' ')}`)
    } catch (e) {
      notify(e.message, 'error')
    }
  }
  const logout = async () => {
    await post('/auth/logout')
    setSession(null)
  }

  return (
    <div className="page narrow">
      <PageHeader title="Settings" subtitle={`Signed in as ${user.username}`} />

      <Card title="Appearance"><ThemePicker /></Card>

      <Card title="Timezone">
        <Field label="Decides what 'today' means for due dates and this week/month" hint={`Your browser is in ${Intl.DateTimeFormat().resolvedOptions().timeZone}.`}>
          <select className="input" value={user.timezone} onChange={(e) => setTimezone(e.target.value)}>
            {!zones.includes(user.timezone) && <option value={user.timezone}>{user.timezone}</option>}
            {zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, ' ')}</option>)}
          </select>
        </Field>
      </Card>

      <Card title="Cards"><LookupManager kind="cards" items={meta.cards} idKey="card_id" label="Card" /></Card>
      <Card title="Categories"><LookupManager kind="categories" items={meta.categories} idKey="category_id" label="Category" withIcon /></Card>

      <Card title="Face ID / passkeys"><Passkeys /></Card>
      <Card title="Password"><PasswordForm /></Card>

      <Card title="Your data">
        <p className="muted small">Download all your transactions and bill payments as a spreadsheet-friendly CSV.</p>
        <a className="btn secondary" href="/api/export.csv" download><Download size={16} /> Export everything</a>
      </Card>

      <button className="btn danger-ghost block" onClick={logout}><LogOut size={16} /> Sign out</button>
      <p className="muted small center">SpendU v2</p>
    </div>
  )
}
