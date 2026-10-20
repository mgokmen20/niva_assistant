import { useCallback, useEffect, useState } from 'react'

/** Top-level screens. The URL path is the source of truth for back/forward. */
export type AppView = 'weather' | 'profile' | 'workspace' | 'travel'

const PROFILE_PATH = '/profile'
const WORKSPACE_PATH = '/admin'
const TRAVEL_PATH = '/travel'

export function viewFromPath(pathname: string): AppView {
  if (pathname === PROFILE_PATH) {
    return 'profile'
  }
  if (pathname === WORKSPACE_PATH) {
    return 'workspace'
  }
  if (pathname === TRAVEL_PATH) {
    return 'travel'
  }
  return 'weather'
}

function pathForView(view: AppView): string {
  if (view === 'profile') {
    return PROFILE_PATH
  }
  if (view === 'workspace') {
    return WORKSPACE_PATH
  }
  if (view === 'travel') {
    return TRAVEL_PATH
  }
  return '/'
}

/**
 * Switch between weather and profile without a router package.
 * pushState records each visit so the browser back and forward buttons work.
 */
export function useAppView() {
  const [view, setView] = useState<AppView>(() => viewFromPath(window.location.pathname))

  useEffect(() => {
    const syncFromHistory = () => {
      setView(viewFromPath(window.location.pathname))
    }
    window.addEventListener('popstate', syncFromHistory)
    return () => {
      window.removeEventListener('popstate', syncFromHistory)
    }
  }, [])

  const showView = useCallback((next: AppView) => {
    const path = pathForView(next)
    if (window.location.pathname !== path) {
      window.history.pushState({ view: next }, '', path)
    }
    setView(next)
  }, [])

  const showWeather = useCallback(() => {
    showView('weather')
  }, [showView])

  const showProfile = useCallback(() => {
    showView('profile')
  }, [showView])

  const showWorkspace = useCallback(() => {
    showView('workspace')
  }, [showView])

  const showTravel = useCallback(() => {
    showView('travel')
  }, [showView])

  return { view, showWeather, showProfile, showWorkspace, showTravel }
}
