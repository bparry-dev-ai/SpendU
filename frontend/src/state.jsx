// App-wide state shared by every page:
//   - who is signed in (user, family, today's date in their timezone)
//   - their cards / categories / bills ("meta"), used by every picker
//   - a "version" number that bumps whenever data changes, so open pages refetch
//   - the global Add sheet and toast messages
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { get } from './api'

const AppContext = createContext(null)
export const useApp = () => useContext(AppContext)

export function AppProvider({ children }) {
  const [session, setSession] = useState(undefined) // undefined = still checking, null = signed out
  const [meta, setMeta] = useState({ cards: [], categories: [], bills: [] })
  const [version, setVersion] = useState(0)
  const [sheet, setSheet] = useState(null) // { type: 'transaction' | 'bill-payment', ... }
  const [toast, setToast] = useState(null)
  const toastTimer = useRef()

  const loadMeta = useCallback(() => get('/meta').then(setMeta).catch(() => {}), [])

  useEffect(() => {
    get('/auth/me')
      .then((s) => { setSession(s); loadMeta() })
      .catch(() => setSession(null))
    const onSignedOut = () => setSession(null)
    window.addEventListener('spendu:signed-out', onSignedOut)
    return () => window.removeEventListener('spendu:signed-out', onSignedOut)
  }, [loadMeta])

  const signedIn = useCallback((s) => { setSession(s); loadMeta() }, [loadMeta])

  // Call after any change: reloads pickers and tells open pages to refetch.
  const changed = useCallback(() => { setVersion((v) => v + 1); loadMeta() }, [loadMeta])

  const notify = useCallback((message, tone = 'ok') => {
    clearTimeout(toastTimer.current)
    setToast({ message, tone })
    toastTimer.current = setTimeout(() => setToast(null), 3200)
  }, [])

  const value = {
    session, setSession, signedIn, meta, setMeta, loadMeta, version, changed,
    sheet, openSheet: setSheet, closeSheet: () => setSheet(null), toast, notify,
    today: session?.today, user: session?.user, family: session?.family || [],
  }
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

// Fetch a GET endpoint; refetches when `path` changes or data changes anywhere.
export function useFetch(path) {
  const { version } = useApp()
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    if (!path) return
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    get(path)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState((s) => ({ ...s, error, loading: false })))
    return () => { alive = false }
  }, [path, version, nonce])
  return { ...state, reload: () => setNonce((n) => n + 1), setData: (data) => setState((s) => ({ ...s, data })) }
}

export const activeCards = (meta) => meta.cards.filter((c) => !c.archived)
export const activeCategories = (meta) => meta.categories.filter((c) => !c.archived)

// ----- Theme -----
// The choice ('system' | 'light' | 'dark') is saved in localStorage. What's
// actually showing is always written to <html data-theme="light|dark">, which
// both styles.css and Tailwind's dark: classes key off. index.html does the
// same before first paint.
const THEME_KEY = 'spendu-theme'
const THEME_EVENT = 'spendu:theme-changed'
const systemDark = window.matchMedia('(prefers-color-scheme: dark)')

function storedTheme() {
  try { return localStorage.getItem(THEME_KEY) || 'system' } catch { return 'system' }
}

const resolveIsDark = (pref) => (pref === 'system' ? systemDark.matches : pref === 'dark')

function applyTheme(pref) {
  const isDark = resolveIsDark(pref)
  document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
  try { localStorage.setItem(THEME_KEY, pref) } catch { /* private mode */ }
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { pref, isDark } }))
}

// Follow the phone/computer setting while the choice is "System".
systemDark.addEventListener('change', () => { if (storedTheme() === 'system') applyTheme('system') })

export function useTheme() {
  const [state, setState] = useState(() => {
    const pref = storedTheme()
    return { pref, isDark: resolveIsDark(pref) }
  })
  useEffect(() => {
    const onChange = (e) => setState(e.detail)
    window.addEventListener(THEME_EVENT, onChange)
    return () => window.removeEventListener(THEME_EVENT, onChange)
  }, [])
  const toggleTheme = useCallback(() => applyTheme(state.isDark ? 'light' : 'dark'), [state.isDark])
  return { theme: state.pref, isDark: state.isDark, setTheme: applyTheme, toggleTheme }
}
