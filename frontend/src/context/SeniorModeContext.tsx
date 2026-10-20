import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

const STORAGE_KEY = 'niva.seniorMode'

interface SeniorModeContextValue {
  isSeniorMode: boolean
  toggleSeniorMode: () => void
}

const SeniorModeContext = createContext<SeniorModeContextValue | null>(null)

function readStoredPreference(): boolean {
  return window.localStorage.getItem(STORAGE_KEY) === 'true'
}

export function SeniorModeProvider({ children }: { children: ReactNode }) {
  const [isSeniorMode, setIsSeniorMode] = useState(readStoredPreference)

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, String(isSeniorMode))
    document.documentElement.classList.toggle('senior-mode', isSeniorMode)
  }, [isSeniorMode])

  const toggleSeniorMode = useCallback(() => {
    setIsSeniorMode((current) => !current)
  }, [])

  return (
    <SeniorModeContext.Provider value={{ isSeniorMode, toggleSeniorMode }}>
      {children}
    </SeniorModeContext.Provider>
  )
}

// The hook belongs with this provider. Fast Refresh still updates the component export.
// eslint-disable-next-line react-refresh/only-export-components
export function useSeniorMode(): SeniorModeContextValue {
  const value = useContext(SeniorModeContext)
  if (value === null) {
    throw new Error('useSeniorMode must be used within SeniorModeProvider.')
  }
  return value
}
