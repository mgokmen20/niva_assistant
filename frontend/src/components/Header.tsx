import { useEffect, useId, useState } from 'react'
import { CloudSun, Menu, X } from 'lucide-react'
import type { AppView } from '../navigation/useAppView'
import { useI18n } from '../i18n/useI18n'
import { useAuth } from '../context/AuthContext'
import { useSeniorMode } from '../context/SeniorModeContext'
import { APP_LANGUAGES, type AppLanguage } from '../i18n/types'
import { canOpenWorkspace } from '../utils/accountRole'
import { UserNav } from './UserNav'

const LANGUAGE_LABEL: Record<AppLanguage, string> = {
  en: 'EN',
  de: 'DE',
  tr: 'TR',
}

/** Brand mark, desktop navigation, and the mobile menu. */
export function Header({
  view,
  onOpenProfile,
  onOpenWeather,
  onOpenWorkspace,
  onOpenTravel,
}: {
  view: AppView
  onOpenProfile: () => void
  onOpenWeather: () => void
  onOpenWorkspace: () => void
  onOpenTravel: () => void
}) {
  const { messages } = useI18n()
  const { user, role, signOut, openAuthModal } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuId = useId()
  const showWorkspace = user !== null && canOpenWorkspace(role)

  useEffect(() => {
    if (!menuOpen) {
      return
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  function closeMenu() {
    setMenuOpen(false)
  }

  function openDestination(navigate: () => void) {
    closeMenu()
    navigate()
  }

  return (
    <header className="sticky top-0 z-20 border-b border-gray-200 bg-white pt-[env(safe-area-inset-top)]">
      <div className="mx-auto flex max-w-6xl flex-nowrap items-center justify-between gap-2 overflow-hidden px-4 py-2 sm:px-6">
        <button
          type="button"
          onClick={onOpenWeather}
          aria-label={view === 'profile' ? messages.profile.back : messages.header.weather}
          className="flex shrink-0 items-center gap-2 rounded-md pr-1 text-left transition-colors hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          <span
            aria-hidden="true"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-blue-600 text-white"
          >
            <CloudSun size={18} />
          </span>
          <span className="min-w-0">
            <span className="block text-lg font-semibold leading-none tracking-tight text-slate-950">Niva</span>
            <span className="brand-subtitle mt-0.5 hidden whitespace-nowrap text-xs font-medium text-slate-500 lg:block">{messages.header.companion}</span>
          </span>
        </button>
        <div className="hidden min-w-0 flex-nowrap items-center justify-end gap-2 md:flex">
          <LanguageSwitch />
          <UserNav
            view={view}
            onOpenProfile={onOpenProfile}
            onOpenWorkspace={onOpenWorkspace}
            onOpenTravel={onOpenTravel}
          />
          <SeniorSwitch compact />
        </div>
        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-md text-gray-700 transition-colors hover:bg-gray-100 md:hidden"
          aria-expanded={menuOpen}
          aria-controls={menuId}
          aria-label={menuOpen ? messages.header.closeMenu : messages.header.menu}
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <X size={24} aria-hidden="true" /> : <Menu size={24} aria-hidden="true" />}
        </button>
      </div>
      {menuOpen ? (
        <div className="md:hidden">
          <button
            type="button"
            aria-label={messages.header.closeMenu}
            className="fixed inset-0 z-40 bg-slate-900/40"
            onClick={closeMenu}
          />
          <nav
            id={menuId}
            aria-label={messages.header.menu}
            className="absolute inset-x-0 z-50 max-h-[calc(100dvh-4rem)] overflow-y-auto border-b border-slate-200 bg-white px-4 py-4 shadow-xl"
          >
            <LanguageSwitch />
            <div className="mt-4 grid gap-2">
              <MenuLink label={messages.header.home} current={view === 'weather'} onClick={() => openDestination(onOpenWeather)} />
              <MenuLink label={messages.header.travel} current={view === 'travel'} onClick={() => openDestination(onOpenTravel)} />
              <MenuLink label={messages.header.profile} current={view === 'profile'} onClick={() => openDestination(onOpenProfile)} />
              {showWorkspace ? (
                <MenuLink
                  label={messages.header.workspace}
                  current={view === 'workspace'}
                  onClick={() => openDestination(onOpenWorkspace)}
                />
              ) : null}
            </div>
            <div className="mt-4">
              <SeniorSwitch />
            </div>
            <button
              type="button"
              className={`mt-4 w-full rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
                user === null
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'text-gray-600 hover:bg-red-50 hover:text-red-600'
              }`}
              onClick={() => {
                closeMenu()
                if (user === null) {
                  openAuthModal()
                  return
                }
                signOut()
              }}
            >
              {user === null ? messages.header.signIn : messages.header.signOut}
            </button>
          </nav>
        </div>
      ) : null}
    </header>
  )
}

function LanguageSwitch() {
  const { language, setLanguage, messages } = useI18n()
  return (
    <div className="inline-flex shrink-0 items-center gap-0.5" role="group" aria-label={messages.header.language}>
      {APP_LANGUAGES.map((code) => {
        const selected = language === code
        return (
          <button
            key={code}
            type="button"
            aria-pressed={selected}
            onClick={() => void setLanguage(code)}
            className={`whitespace-nowrap text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 ${
              selected
                ? 'bg-blue-50 text-blue-600 font-semibold rounded-md px-2 py-1'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md px-2 py-1'
            }`}
          >
            {LANGUAGE_LABEL[code]}
          </button>
        )
      })}
    </div>
  )
}

function SeniorSwitch({ compact = false }: { compact?: boolean }) {
  const { isSeniorMode, toggleSeniorMode } = useSeniorMode()
  const { messages } = useI18n()
  return (
    <button
      type="button"
      role="switch"
      aria-checked={isSeniorMode}
      aria-label={messages.header.seniorMode}
      onClick={toggleSeniorMode}
      className="flex w-full shrink-0 items-center justify-between gap-2 whitespace-nowrap rounded-md px-2 py-1 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 md:w-auto md:justify-start"
    >
      <span className={compact ? 'hidden whitespace-nowrap lg:inline' : 'whitespace-nowrap'}>{messages.header.seniorMode}</span>
      <span
        aria-hidden="true"
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors duration-300 ${
          isSeniorMode ? 'bg-blue-600' : 'bg-gray-300'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-300 ease-out ${
            isSeniorMode ? 'translate-x-4' : 'translate-x-0'
          }`}
        />
      </span>
    </button>
  )
}

function MenuLink({ label, current, onClick }: { label: string; current: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-current={current ? 'page' : undefined}
      onClick={onClick}
      className={`whitespace-nowrap rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
        current ? 'bg-gray-100 text-gray-900' : 'text-gray-700 hover:bg-gray-100 hover:text-gray-900'
      }`}
    >
      {label}
    </button>
  )
}
