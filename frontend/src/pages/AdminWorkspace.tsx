import { useEffect, useMemo, type ReactNode } from 'react'
import { ArrowLeft, CloudSun, LayoutDashboard, LineChart, Users } from 'lucide-react'
import { OverviewTab } from '../components/admin/OverviewTab'
import { TrendsTab } from '../components/admin/TrendsTab'
import { UsersTab } from '../components/admin/UsersTab'
import { fieldClass, pillActive, pillIdle, primaryButton } from '../components/admin/workspaceStyles'
import { WorkspaceProvider, useWorkspace, type WorkspacePreset } from '../context/WorkspaceContext'
import type { AnalyticsGender } from '../types/api'
import { useAuth } from '../context/AuthContext'
import { useTranslation } from '../i18n/useI18n'

const RANGES: Exclude<WorkspacePreset, 'custom'>[] = ['today', '7d', '30d']

function formatToday(language: string): string {
  const locale = language === 'de' ? 'de-CH' : language === 'tr' ? 'tr-TR' : 'en-GB'
  return new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date())
}

/** Management shell with a navy sidebar and a light content area. */
export function AdminWorkspace({
  suggestedCity,
  onExit,
}: {
  suggestedCity: string
  onExit: () => void
}) {
  const choices = useMemo(
    () => (suggestedCity.trim() === '' ? [] : [suggestedCity.trim()]),
    [suggestedCity],
  )
  return (
    <WorkspaceProvider cityChoices={choices}>
      <WorkspaceFrame onExit={onExit} />
    </WorkspaceProvider>
  )
}

function WorkspaceFrame({ onExit }: { onExit: () => void }) {
  const { user, role } = useAuth()
  const { t } = useTranslation()
  const { tab, setTab } = useWorkspace()
  const name = user === null ? t('workspace.signedInMember') : `${user.first_name} ${user.last_name}`.trim()
  const email = user?.email ?? ''

  useEffect(() => {
    if (role !== 'admin' && tab === 'users') {
      setTab('overview')
    }
  }, [role, setTab, tab])

  return (
    <div className="workspace-shell flex min-h-[calc(100dvh-5rem)] flex-col bg-slate-100 lg:flex-row">
      <aside className="workspace-sidebar flex w-full shrink-0 flex-col bg-[#0b1329] text-white lg:w-72">
        <div className="flex items-center gap-3 px-4 py-5">
          <span
            aria-hidden="true"
            className="flex h-11 w-11 items-center justify-center rounded-2xl bg-sky-500 text-white"
          >
            <CloudSun size={22} />
          </span>
          <span>
            <span className="block text-lg font-semibold leading-none">Niva</span>
            <span className="mt-1 block text-sm font-medium text-slate-300">{t('workspace.nav')}</span>
          </span>
        </div>
        <div className="mx-4 rounded-2xl bg-white/10 px-3 py-3">
          <p className="truncate text-sm font-semibold">{name}</p>
          <p className="truncate text-xs font-medium text-slate-300">{email}</p>
          <p className="mt-2 inline-flex rounded-full bg-sky-400/20 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-sky-100">
            {role === 'admin'
              ? t('workspace.accounts.roleAdmin')
              : role === 'partner'
                ? t('workspace.accounts.rolePartner')
                : t('workspace.accounts.roleUser')}
          </p>
        </div>
        <nav className="workspace-nav mt-4 flex flex-1 flex-col gap-2 px-3" aria-label={t('workspace.nav')}>
          <WorkspaceLink
            label={t('workspace.dashboard')}
            icon={<LayoutDashboard size={18} aria-hidden="true" />}
            current={tab === 'overview'}
            onSelect={() => setTab('overview')}
          />
          {role === 'admin' ? (
            <WorkspaceLink
              label={t('workspace.users')}
              icon={<Users size={18} aria-hidden="true" />}
              current={tab === 'users'}
              onSelect={() => setTab('users')}
            />
          ) : null}
          <WorkspaceLink
            label={t('workspace.trends')}
            icon={<LineChart size={18} aria-hidden="true" />}
            current={tab === 'trends'}
            onSelect={() => setTab('trends')}
          />
          <button
            type="button"
            onClick={onExit}
            className="mt-auto mb-4 inline-flex min-h-12 items-center gap-2 rounded-2xl px-3 text-left text-sm font-semibold text-slate-100 transition hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            <ArrowLeft size={18} aria-hidden="true" />
            {t('workspace.back')}
          </button>
        </nav>
      </aside>
      <section className="min-w-0 flex-1">
        <WorkspaceToolbar firstName={user?.first_name ?? t('workspace.guestName')} />
        <WorkspacePanel />
      </section>
    </div>
  )
}

function WorkspaceLink({
  label,
  icon,
  current,
  onSelect,
}: {
  label: string
  icon: ReactNode
  current: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      aria-current={current ? 'page' : undefined}
      onClick={onSelect}
      className={`inline-flex min-h-12 items-center gap-2 rounded-2xl px-3 text-left text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white ${
        current ? 'bg-white text-[#0b1329]' : 'text-slate-100 hover:bg-white/10'
      }`}
    >
      {icon}
      {label}
    </button>
  )
}

function WorkspaceToolbar({ firstName }: { firstName: string }) {
  const { language, t } = useTranslation()
  const {
    preset,
    setPreset,
    startDate,
    endDate,
    setStartDate,
    setEndDate,
    rangeReady,
    city,
    setCity,
    cityChoices,
    gender,
    setGender,
    requestRefresh,
    refreshKey,
  } = useWorkspace()
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-4 sm:px-6">
      <p className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm">
        {formatToday(language)}
      </p>
      <h1 className="text-xl font-semibold text-slate-950">{t('workspace.welcome', firstName)}</h1>
      <div className="workspace-range flex flex-wrap gap-2" role="group" aria-label={t('workspace.dateRange')}>
        {RANGES.map((option) => {
          const label = option === 'today' ? t('workspace.today') : option === '7d' ? t('workspace.last7') : t('workspace.last30')
          return (
            <button
              key={option}
              type="button"
              aria-pressed={preset === option}
              onClick={() => setPreset(option)}
              className={preset === option ? pillActive : pillIdle}
            >
              {label}
            </button>
          )
        })}
        <button
          type="button"
          aria-pressed={preset === 'custom'}
          onClick={() => setPreset('custom')}
          className={preset === 'custom' ? pillActive : pillIdle}
        >
          {t('workspace.custom')}
        </button>
      </div>
      {preset === 'custom' ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-sm font-semibold text-slate-700" htmlFor="workspace-start">
            {t('workspace.start')}
            <input
              id="workspace-start"
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              className={`mt-1 block ${fieldClass}`}
            />
          </label>
          <label className="text-sm font-semibold text-slate-700" htmlFor="workspace-end">
            {t('workspace.end')}
            <input
              id="workspace-end"
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              className={`mt-1 block ${fieldClass}`}
            />
          </label>
        </div>
      ) : null}
      {preset === 'custom' && !rangeReady ? (
        <p className="text-sm font-semibold text-rose-800" role="alert">
          {t('workspace.rangeInvalid')}
        </p>
      ) : null}
      <label className="text-sm font-semibold text-slate-700" htmlFor="workspace-city">
        {t('workspace.city')}
        <select
          id="workspace-city"
          value={city ?? ''}
          onChange={(event) => setCity(event.target.value === '' ? null : event.target.value)}
          className={`ml-2 ${fieldClass}`}
        >
          <option value="">{t('workspace.allCities')}</option>
          {cityChoices.map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm font-semibold text-slate-700" htmlFor="workspace-gender">
        {t('workspace.gender')}
        <select
          id="workspace-gender"
          value={gender}
          onChange={(event) => setGender(event.target.value as AnalyticsGender)}
          className={`ml-2 ${fieldClass}`}
        >
          <option value="all">{t('workspace.allGenders')}</option>
          <option value="male">{t('workspace.men')}</option>
          <option value="female">{t('workspace.women')}</option>
          <option value="other">{t('workspace.other')}</option>
        </select>
      </label>
      <button type="button" onClick={requestRefresh} className={primaryButton}>
        {t('workspace.fetch')}
      </button>
      {refreshKey > 0 ? (
        <p className="text-sm font-medium text-slate-600" role="status">
          {t(
            'workspace.refreshStatus',
            refreshKey,
            preset === 'custom'
              ? `${startDate} – ${endDate}`
              : preset === 'today'
                ? t('workspace.today')
                : preset === '7d'
                  ? t('workspace.last7')
                  : t('workspace.last30'),
            city ?? t('workspace.allCities'),
          )}
        </p>
      ) : null}
    </div>
  )
}

function WorkspacePanel() {
  const { tab } = useWorkspace()
  const { role } = useAuth()
  if (tab === 'users' && role === 'admin') {
    return <UsersTab />
  }
  if (tab === 'trends') {
    return <TrendsTab />
  }
  return <OverviewTab />
}
