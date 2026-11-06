import { browserSupportsWebAuthn, startAuthentication } from '@simplewebauthn/browser'
import { ScanFace } from 'lucide-react'
import { useState } from 'react'
import { post } from '../api'
import { Logo } from '../components/Layout'
import { useApp } from '../state'

export default function Login() {
  const { signedIn } = useApp()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const passkeys = browserSupportsWebAuthn()

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      signedIn(await post('/auth/login', { username, password, remember }))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const passkeyLogin = async () => {
    setError(null)
    try {
      const options = await post('/auth/passkey/login/begin')
      const credential = await startAuthentication(options)
      signedIn(await post('/auth/passkey/login/complete', { credential, remember: true }))
    } catch (err) {
      if (err.name === 'NotAllowedError') return // cancelled
      setError(err.message || 'Face ID sign-in failed.')
    }
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <Logo />
        <p className="muted center">Track spending, cards and bills.</p>

        {passkeys && (
          <>
            <button type="button" className="btn primary block lg" onClick={passkeyLogin}>
              <ScanFace size={20} /> Sign in with Face ID / Passkey
            </button>
            <div className="divider"><span>or use your password</span></div>
          </>
        )}

        <label className="field">
          <span className="field-label">Username</span>
          <input className="input" autoComplete="username" autoCapitalize="none" value={username}
            onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label className="field">
          <span className="field-label">Password</span>
          <input className="input" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Keep me signed in for 30 days
        </label>
        {error && <p className="form-error">{error}</p>}
        <button className={`btn block lg ${passkeys ? 'secondary' : 'primary'}`} disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
