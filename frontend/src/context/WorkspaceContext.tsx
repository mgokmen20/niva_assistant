import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { AnalyticsGender } from '../types/api'
import { utcIsoDate } from '../utils/utcDate'

/** Rolling windows offered by the workspace filter bar. */
export type WorkspaceRange = 1 | 7 | 30

/** Named ranges plus an explicit calendar span. */
export type WorkspacePreset = 'today' | '7d' | '30d' | 'custom'

/** Sidebar destinations inside the management shell. */
export type WorkspaceTab = 'overview' | 'users' | 'trends'

/** Query fields sent to the analytics routes. */
export interface AnalyticsWindowParams {
  days?: number
  startDate?: string
  endDate?: string
  gender?: AnalyticsGender
}

interface WorkspaceContextValue {
  preset: WorkspacePreset
  days: WorkspaceRange
  startDate: string
  endDate: string
  rangeReady: boolean
  rangeLabel: string
  city: string | null
  cityChoices: readonly string[]
  gender: AnalyticsGender
  tab: WorkspaceTab
  refreshKey: number
  setPreset: (preset: WorkspacePreset) => void
  setStartDate: (value: string) => void
  setEndDate: (value: string) => void
  setCity: (city: string | null) => void
  setGender: (gender: AnalyticsGender) => void
  setTab: (tab: WorkspaceTab) => void
  requestRefresh: () => void
  analyticsWindow: () => AnalyticsWindowParams
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

const PRESET_DAYS: Record<Exclude<WorkspacePreset, 'custom'>, WorkspaceRange> = {
  today: 1,
  '7d': 7,
  '30d': 30,
}

const PRESET_LABEL: Record<Exclude<WorkspacePreset, 'custom'>, string> = {
  today: 'Today',
  '7d': 'Last 7 Days',
  '30d': 'Last 30 Days',
}

function rangeIsReady(preset: WorkspacePreset, startDate: string, endDate: string): boolean {
  if (preset !== 'custom') {
    return true
  }
  return /^\d{4}-\d{2}-\d{2}$/.test(startDate) && /^\d{4}-\d{2}-\d{2}$/.test(endDate) && startDate <= endDate
}

/** Share the date range, city, and active tab across the workspace shell. */
export function WorkspaceProvider({
  children,
  cityChoices,
}: {
  children: ReactNode
  cityChoices: readonly string[]
}) {
  const [preset, setPreset] = useState<WorkspacePreset>('7d')
  const [startDate, setStartDate] = useState(() => utcIsoDate(-6))
  const [endDate, setEndDate] = useState(() => utcIsoDate(0))
  const [city, setCity] = useState<string | null>(null)
  const [gender, setGender] = useState<AnalyticsGender>('all')
  const [tab, setTab] = useState<WorkspaceTab>('overview')
  const [refreshKey, setRefreshKey] = useState(0)
  const days = preset === 'custom' ? 7 : PRESET_DAYS[preset]
  const rangeReady = rangeIsReady(preset, startDate, endDate)
  const rangeLabel = preset === 'custom' ? `${startDate} to ${endDate}` : PRESET_LABEL[preset]

  const requestRefresh = useCallback(() => {
    setRefreshKey((current) => current + 1)
  }, [])

  const analyticsWindow = useCallback((): AnalyticsWindowParams => {
    const selected = gender === 'all' ? {} : { gender }
    if (preset === 'custom') {
      return { startDate, endDate, ...selected }
    }
    return { days, ...selected }
  }, [days, endDate, gender, preset, startDate])

  const value = useMemo(
    () => ({
      preset,
      days,
      startDate,
      endDate,
      rangeReady,
      rangeLabel,
      city,
      cityChoices,
      gender,
      tab,
      refreshKey,
      setPreset,
      setStartDate,
      setEndDate,
      setCity,
      setGender,
      setTab,
      requestRefresh,
      analyticsWindow,
    }),
    [
      analyticsWindow,
      city,
      cityChoices,
      gender,
      days,
      endDate,
      preset,
      rangeLabel,
      rangeReady,
      refreshKey,
      requestRefresh,
      startDate,
      tab,
    ],
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

// The hook belongs with this provider. Fast Refresh still updates the component export.
// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspace(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext)
  if (value === null) {
    throw new Error('useWorkspace must be used within WorkspaceProvider.')
  }
  return value
}
