import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import {
  ACCESS_TOKEN_EXPIRES_KEY,
  ACCESS_TOKEN_STORAGE_KEY,
  USER_PROFILE_STORAGE_KEY,
  fetchCurrentUser,
  loginAccount,
  registerAccount,
  type RegisterAccountInput,
} from '../services/api'
import type { AccountRole, Gender, UserProfile } from '../types/api'
import { accountRole } from '../utils/accountRole'

interface AuthContextValue {
  user: UserProfile | null
  role: AccountRole
  gender: Gender
  token: string | null
  sessionReady: boolean
  authModalOpen: boolean
  authIntent: 'sign-in' | 'register'
  openAuthModal: (intent?: 'sign-in' | 'register') => void
  closeAuthModal: () => void
  signIn: (email: string, password: string, rememberMe: boolean) => Promise<void>
  register: (input: RegisterAccountInput) => Promise<void>
  signOut: () => void
  applyProfile: (profile: UserProfile) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

type AuthStore = 'local' | 'session'
type AuthIntent = 'sign-in' | 'register'

const REMEMBER_ME_DAYS = 30

function browserStorage(store: AuthStore): Storage {
  return store === 'session' ? window.sessionStorage : window.localStorage
}

function readStoredSession(): { token: string | null; store: AuthStore } {
  const sessionToken = window.sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  if (sessionToken !== null && sessionToken.trim() !== '') {
    return { token: sessionToken, store: 'session' }
  }
  const localToken = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  if (localToken !== null && localToken.trim() !== '' && rememberedTokenIsCurrent()) {
    return { token: localToken, store: 'local' }
  }
  if (localToken !== null) {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
    window.localStorage.removeItem(USER_PROFILE_STORAGE_KEY)
    window.localStorage.removeItem(ACCESS_TOKEN_EXPIRES_KEY)
  }
  return { token: null, store: 'local' }
}

function clearStoredSession() {
  window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  window.localStorage.removeItem(USER_PROFILE_STORAGE_KEY)
  window.localStorage.removeItem(ACCESS_TOKEN_EXPIRES_KEY)
  window.sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  window.sessionStorage.removeItem(USER_PROFILE_STORAGE_KEY)
  window.sessionStorage.removeItem(ACCESS_TOKEN_EXPIRES_KEY)
}

function rememberedTokenIsCurrent(): boolean {
  const expiresAt = window.localStorage.getItem(ACCESS_TOKEN_EXPIRES_KEY)
  if (expiresAt === null) {
    return false
  }
  const expires = Date.parse(expiresAt)
  return !Number.isNaN(expires) && expires > Date.now()
}

function writeStoredSession(token: string, profile: UserProfile, rememberMe: boolean) {
  clearStoredSession()
  const store = browserStorage(rememberMe ? 'local' : 'session')
  store.setItem(ACCESS_TOKEN_STORAGE_KEY, token)
  store.setItem(USER_PROFILE_STORAGE_KEY, JSON.stringify(profile))
  if (rememberMe) {
    const expiresAt = new Date(Date.now() + REMEMBER_ME_DAYS * 24 * 60 * 60 * 1000).toISOString()
    store.setItem(ACCESS_TOKEN_EXPIRES_KEY, expiresAt)
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const initialSession = readStoredSession()
  const [user, setUser] = useState<UserProfile | null>(null)
  const [token, setToken] = useState<string | null>(initialSession.token)
  const [authStore, setAuthStore] = useState<AuthStore>(initialSession.store)
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [authIntent, setAuthIntent] = useState<AuthIntent>('sign-in')
  const [sessionReady, setSessionReady] = useState(() => readStoredSession().token === null)

  useEffect(() => {
    const stored = readStoredSession()
    if (stored.token === null) {
      return
    }
    let active = true
    void fetchCurrentUser(stored.token)
      .then((profile) => {
        if (active) {
          setUser(profile)
          setToken(stored.token)
          setAuthStore(stored.store)
          browserStorage(stored.store).setItem(USER_PROFILE_STORAGE_KEY, JSON.stringify(profile))
        }
      })
      .catch(() => {
        if (!active) {
          return
        }
        clearStoredSession()
        setToken(null)
        setUser(null)
      })
      .finally(() => {
        if (active) {
          setSessionReady(true)
        }
      })
    return () => {
      active = false
    }
  }, [])

  const openAuthModal = useCallback((intent: AuthIntent = 'sign-in') => {
    setAuthIntent(intent)
    setAuthModalOpen(true)
  }, [])

  const closeAuthModal = useCallback(() => {
    setAuthModalOpen(false)
  }, [])

  const signIn = useCallback(async (email: string, password: string, rememberMe: boolean) => {
    const accessToken = await loginAccount(email, password, rememberMe)
    const profile = await fetchCurrentUser(accessToken)
    writeStoredSession(accessToken, profile, rememberMe)
    setAuthStore(rememberMe ? 'local' : 'session')
    setToken(accessToken)
    setUser(profile)
    setAuthModalOpen(false)
  }, [])

  const register = useCallback(
    async (input: RegisterAccountInput) => {
      await registerAccount(input)
      await signIn(input.email, input.password, true)
    },
    [signIn],
  )

  const signOut = useCallback(() => {
    clearStoredSession()
    setToken(null)
    setUser(null)
  }, [])

  const applyProfile = useCallback(
    (profile: UserProfile) => {
      setUser(profile)
      if (token !== null) {
        browserStorage(authStore).setItem(USER_PROFILE_STORAGE_KEY, JSON.stringify(profile))
      }
    },
    [authStore, token],
  )

  const gender: Gender = user?.gender ?? 'neutral'
  const role = accountRole(user?.role)

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        gender,
        token,
        sessionReady,
        authModalOpen,
        authIntent,
        openAuthModal,
        closeAuthModal,
        signIn,
        register,
        signOut,
        applyProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

// The hook belongs with this provider. Fast Refresh still updates the component export.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (value === null) {
    throw new Error('useAuth must be used within AuthProvider.')
  }
  return value
}
