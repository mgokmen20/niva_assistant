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
    <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/85 pt-[env(safe-area-inset-top)] backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-4 py-3 sm:px-6">
        <button
          type="button"
          onClick={onOpenWeather}
          aria-label={view === 'profile' ? messages.profile.back : messages.header.weather}
          className="flex min-h-12 min-w-0 items-center gap-3 rounded-2xl pr-2 text-left transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
        >
          <span
            aria-hidden="true"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-500 to-indigo-600 text-white shadow-sm"
          >
            <CloudSun size={22} />
          </span>
          <span className="min-w-0">
            <span className="block text-xl font-semibold leading-none tracking-tight text-slate-950">Niva</span>
            <span className="brand-subtitle mt-1 hidden text-xs font-medium text-slate-500 md:block">{messages.header.companion}</span>
          </span>
        </button>
        <div className="hidden items-center justify-end gap-2 md:flex">
          <LanguageSwitch />
          <UserNav
            view={view}
            onOpenProfile={onOpenProfile}
            onOpenWorkspace={onOpenWorkspace}
            onOpenTravel={onOpenTravel}
          />
          <SeniorSwitch />
        </div>
        <button
          type="button"
          className="inline-flex h-12 min-h-12 w-12 min-w-12 items-center justify-center rounded-2xl bg-slate-50 text-slate-950 ring-1 ring-slate-200 md:hidden"
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
              className="mt-4 min-h-12 w-full rounded-2xl bg-indigo-800 px-4 text-sm font-semibold text-white"
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
    <div className="inline-flex min-h-12 items-center rounded-full bg-slate-50 p-1 ring-1 ring-slate-200" role="group" aria-label={messages.header.language}>
      {APP_LANGUAGES.map((code) => {
        const selected = language === code
        return (
          <button
            key={code}
            type="button"
            aria-pressed={selected}
            onClick={() => void setLanguage(code)}
            className={`min-h-12 min-w-12 rounded-full px-3 text-sm font-semibold transition duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-950 ${
              selected ? 'bg-slate-950 text-white' : 'text-slate-700 hover:bg-white'
            }`}
          >
            {LANGUAGE_LABEL[code]}
          </button>
        )
      })}
    </div>
  )
}

function SeniorSwitch() {
  const { isSeniorMode, toggleSeniorMode } = useSeniorMode()
  const { messages } = useI18n()
  return (
    <button
      type="button"
      role="switch"
      aria-checked={isSeniorMode}
      aria-label={messages.header.seniorMode}
      onClick={toggleSeniorMode}
      className="flex min-h-12 w-full items-center justify-between gap-3 rounded-full bg-slate-50 px-3 ring-1 ring-slate-200 transition duration-300 hover:ring-slate-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black md:w-auto md:justify-start"
    >
      <span className={isSeniorMode ? 'text-xl font-bold text-black' : 'text-sm font-semibold text-slate-700'}>
        {messages.header.seniorMode}
      </span>
      <span
        aria-hidden="true"
        className={`relative h-7 w-12 shrink-0 rounded-full transition-colors duration-300 ${
          isSeniorMode ? 'bg-black' : 'bg-slate-300'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform duration-300 ease-out ${
            isSeniorMode ? 'translate-x-5' : 'translate-x-0'
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
      className={`min-h-12 rounded-2xl px-4 text-left text-base font-semibold ${
        current ? 'bg-blue-700 text-white' : 'bg-slate-50 text-slate-950 ring-1 ring-slate-200'
      }`}
    >
      {label}
    </button>
  )
}
