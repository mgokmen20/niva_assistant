import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { WardrobePanel } from '../components/WardrobePanel'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/useI18n'
import { APP_LANGUAGES, type AppLanguage } from '../i18n/types'
import { ApiError, changePassword, fetchProfile, resetCalibration, updateProfile } from '../services/api'
import { messagesFor } from '../i18n'
import type { EnvironmentRoutine, Gender, ThermalPreference, WearerProfile } from '../types/api'

const BIRTH_YEAR_MIN = 1900

const LANGUAGE_NAME: Record<AppLanguage, string> = {
  en: 'English',
  de: 'Deutsch',
  tr: 'Türkçe',
}

const primaryButtonClass =
  'bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md px-4 py-2 transition-colors disabled:opacity-60'

const fieldClass =
  'mt-1 block w-full border border-gray-300 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 rounded-md focus:outline-none'

const labelClass = 'block text-sm font-medium text-gray-700'

const cardClass = 'rounded-lg border border-slate-200 bg-white p-6 shadow-sm'

function messageFrom(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }
  return fallback
}

function formatOffset(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}°C`
}

function birthYearFrom(isoDate: string): string {
  const year = Number(isoDate.slice(0, 4))
  return Number.isInteger(year) ? String(year) : ''
}

function birthDateForSave(yearText: string, currentIso: string): string | null {
  const year = Number(yearText)
  const maxYear = new Date().getFullYear()
  if (!Number.isInteger(year) || year < BIRTH_YEAR_MIN || year > maxYear) {
    return null
  }
  const currentYear = Number(currentIso.slice(0, 4))
  if (year === currentYear && /^\d{4}-\d{2}-\d{2}$/.test(currentIso)) {
    return currentIso
  }
  return `${year}-01-01`
}

export function ProfilePage({ onBack }: { onBack: () => void }) {
  const { token, openAuthModal, applyProfile } = useAuth()
  const { language, messages, setLanguage } = useI18n()
  const [profile, setProfile] = useState<WearerProfile | null>(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [thermalPreference, setThermalPreference] = useState<ThermalPreference>('balanced')
  const [environmentRoutine, setEnvironmentRoutine] = useState<EnvironmentRoutine>('mostly_indoor')
  const [gender, setGender] = useState<Gender>('neutral')
  const [birthYear, setBirthYear] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loading, setLoading] = useState(token !== null)
  const [submitting, setSubmitting] = useState(false)
  const [tab, setTab] = useState<'settings' | 'wardrobe'>('settings')

  const applyLoaded = useCallback(
    (next: WearerProfile) => {
      setProfile(next)
      setFirstName(next.first_name)
      setLastName(next.last_name)
      setEmail(next.email)
      setPhoneNumber(next.phone_number ?? '')
      setThermalPreference(next.thermal_preference)
      setEnvironmentRoutine(next.environment_routine)
      setGender(next.gender)
      setBirthYear(birthYearFrom(next.birth_date))
      applyProfile({
        id: next.id,
        email: next.email,
        first_name: next.first_name,
        last_name: next.last_name,
        birth_date: next.birth_date,
        role: next.role,
        gender: next.gender,
      })
    },
    [applyProfile],
  )

  useEffect(() => {
    if (token === null) {
      return
    }
    let active = true
    void fetchProfile(token)
      .then((payload) => {
        if (!active) {
          return
        }
        applyLoaded(payload)
      })
      .catch((caught: unknown) => {
        if (active) {
          setError(messageFrom(caught, messages.common.tryAgain))
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [applyLoaded, messages.common.tryAgain, token])

  async function savePersonal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (token === null || profile === null) {
      return
    }
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const next = await updateProfile(token, {
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        email: email.trim(),
        phoneNumber: phoneNumber.trim(),
        thermalPreference: profile.thermal_preference,
        environmentRoutine: profile.environment_routine,
      })
      applyLoaded(next)
      setNotice(messages.profile.personalSaved)
    } catch (caught) {
      setError(messageFrom(caught, messages.common.tryAgain))
    } finally {
      setSubmitting(false)
    }
  }

  async function saveThermal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (token === null || profile === null) {
      return
    }
    const birthDate = birthDateForSave(birthYear, profile.birth_date)
    if (birthDate === null) {
      setError(messages.profile.birthYearInvalid(BIRTH_YEAR_MIN, new Date().getFullYear()))
      setNotice(null)
      return
    }
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const next = await updateProfile(token, {
        firstName: profile.first_name,
        lastName: profile.last_name,
        email: profile.email,
        phoneNumber: profile.phone_number ?? '',
        thermalPreference,
        environmentRoutine,
        gender,
        birthDate,
      })
      applyLoaded(next)
      setNotice(messages.profile.thermalSaved)
    } catch (caught) {
      setError(messageFrom(caught, messages.common.tryAgain))
    } finally {
      setSubmitting(false)
    }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (token === null) {
      return
    }
    if (newPassword.length < 8) {
      setError(messages.profile.passwordShort)
      setNotice(null)
      return
    }
    if (newPassword !== confirmPassword) {
      setError(messages.profile.passwordMismatch)
      setNotice(null)
      return
    }
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      await changePassword(token, currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setNotice(messages.profile.passwordUpdated)
    } catch (caught) {
      setError(messageFrom(caught, messages.common.tryAgain))
    } finally {
      setSubmitting(false)
    }
  }

  async function resetOffset() {
    if (token === null) {
      return
    }
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const next = await resetCalibration(token)
      applyLoaded(next)
      setNotice(messages.profile.calibrationReset)
    } catch (caught) {
      setError(messageFrom(caught, messages.common.tryAgain))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="profile-page space-y-3 md:space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950">
            {messages.profile.title}
          </h1>
          <p className="dash-label mt-1 max-w-xl text-sm text-slate-600">
            {messages.profile.intro}
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {messages.profile.back}
        </button>
      </div>

      {token === null ? (
        <section className={cardClass}>
          <h2 className="text-base font-semibold text-slate-950">{messages.profile.signInTitle}</h2>
          <p className="mt-2 text-sm text-slate-600">
            {messages.profile.signInBody}
          </p>
          <button
            type="button"
            onClick={() => openAuthModal()}
            className={`mt-6 ${primaryButtonClass}`}
          >
            {messages.profile.signIn}
          </button>
        </section>
      ) : null}

      {token !== null ? (
        <div className="md:grid md:grid-cols-[14rem_minmax(0,1fr)] md:items-start md:gap-5">
          <nav
            aria-label={messages.profile.title}
            className="flex gap-2 overflow-x-auto pb-1 md:sticky md:top-4 md:flex-col md:gap-1 md:overflow-visible md:rounded-lg md:border md:border-slate-200 md:bg-white md:p-3 md:shadow-sm"
          >
            <button
              type="button"
              id="profile-tab-settings"
              aria-controls="profile-panel-settings"
              aria-current={tab === 'settings' ? 'page' : undefined}
              onClick={() => setTab('settings')}
              className={`shrink-0 whitespace-nowrap rounded-md px-3 py-2 text-left text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 md:w-full ${
                tab === 'settings' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              {messages.profile.tabSettings}
            </button>
            <button
              type="button"
              id="profile-tab-wardrobe"
              aria-controls="profile-panel-wardrobe"
              aria-current={tab === 'wardrobe' ? 'page' : undefined}
              onClick={() => setTab('wardrobe')}
              className={`shrink-0 whitespace-nowrap rounded-md px-3 py-2 text-left text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 md:w-full ${
                tab === 'wardrobe' ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              {messages.profile.tabWardrobe}
            </button>
          </nav>
          <div className="min-w-0 space-y-3 md:space-y-5">
      {tab === 'settings' && error ? (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-900" role="alert">
          {error}
        </p>
      ) : null}
      {tab === 'settings' && notice ? (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-950" role="status">
          {notice}
        </p>
      ) : null}

      {token !== null && tab === 'settings' && loading ? (
        <p className={`${cardClass} text-center text-sm text-slate-600`} role="status">
          {messages.profile.loading}
        </p>
      ) : null}

      {token !== null && tab === 'wardrobe' ? (
        <div role="tabpanel" id="profile-panel-wardrobe" aria-labelledby="profile-tab-wardrobe">
          <WardrobePanel token={token} />
        </div>
      ) : null}

      {token !== null && tab === 'settings' && profile !== null ? (
        <div
          role="tabpanel"
          id="profile-panel-settings"
          aria-labelledby="profile-tab-settings"
          className="grid items-start gap-6 lg:grid-cols-2"
        >
          <div className="grid gap-6">
            <section className={cardClass}>
              <h2 className="text-base font-semibold text-slate-950">{messages.profile.personal}</h2>
              <form className="mt-6 grid gap-4" onSubmit={(event) => void savePersonal(event)}>
                <label className={labelClass} htmlFor="profile-language">
                  {messages.profile.preferredLanguage}
                  <select
                    id="profile-language"
                    value={language}
                    onChange={(event) => {
                      const next = event.target.value
                      if (next !== 'en' && next !== 'de' && next !== 'tr') {
                        return
                      }
                      setError(null)
                      setNotice(null)
                      void setLanguage(next)
                        .then(() => setNotice(messagesFor(next).profile.languageSaved))
                        .catch((caught: unknown) => setError(messageFrom(caught, messages.common.tryAgain)))
                    }}
                    className={fieldClass}
                  >
                    {APP_LANGUAGES.map((code) => (
                      <option key={code} value={code}>
                        {LANGUAGE_NAME[code]}
                      </option>
                    ))}
                  </select>
                </label>
                <label className={labelClass} htmlFor="profile-first-name">
                  {messages.profile.firstName}
                  <input
                    id="profile-first-name"
                    value={firstName}
                    onChange={(event) => setFirstName(event.target.value)}
                    className={fieldClass}
                    autoComplete="given-name"
                    required
                  />
                </label>
                <label className={labelClass} htmlFor="profile-last-name">
                  {messages.profile.lastName}
                  <input
                    id="profile-last-name"
                    value={lastName}
                    onChange={(event) => setLastName(event.target.value)}
                    className={fieldClass}
                    autoComplete="family-name"
                    required
                  />
                </label>
                <label className={labelClass} htmlFor="profile-email">
                  {messages.profile.email}
                  <input
                    id="profile-email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className={fieldClass}
                    autoComplete="email"
                    required
                  />
                </label>
                <label className={labelClass} htmlFor="profile-phone">
                  {messages.profile.phone}
                  <input
                    id="profile-phone"
                    type="tel"
                    value={phoneNumber}
                    onChange={(event) => setPhoneNumber(event.target.value)}
                    className={fieldClass}
                    autoComplete="tel"
                    placeholder={messages.profile.optional}
                  />
                </label>
                <div>
                  <button type="submit" disabled={submitting} className={primaryButtonClass}>
                    {messages.profile.savePersonal}
                  </button>
                </div>
              </form>
            </section>

            <section className={cardClass}>
              <h2 className="text-base font-semibold text-slate-950">{messages.profile.security}</h2>
              <form className="mt-6 grid gap-4" onSubmit={(event) => void savePassword(event)}>
                <label className={labelClass} htmlFor="profile-current-password">
                  {messages.profile.currentPassword}
                  <input
                    id="profile-current-password"
                    type="password"
                    autoComplete="current-password"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                    className={fieldClass}
                    required
                  />
                </label>
                <label className={labelClass} htmlFor="profile-new-password">
                  {messages.profile.newPassword}
                  <input
                    id="profile-new-password"
                    type="password"
                    autoComplete="new-password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    className={fieldClass}
                    minLength={8}
                    required
                  />
                </label>
                <label className={labelClass} htmlFor="profile-confirm-password">
                  {messages.profile.confirmPassword}
                  <input
                    id="profile-confirm-password"
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    className={fieldClass}
                    minLength={8}
                    required
                  />
                </label>
                <div>
                  <button type="submit" disabled={submitting} className={primaryButtonClass}>
                    {messages.profile.changePassword}
                  </button>
                </div>
              </form>
            </section>
          </div>

          <section className={cardClass}>
            <h2 className="text-base font-semibold text-slate-950">{messages.profile.thermal}</h2>
            <div
              className="profile-offset mt-6 rounded-md border border-gray-200 bg-gray-50 px-4 py-3"
              aria-live="polite"
            >
              <p className="text-sm font-medium text-gray-600">{messages.profile.activeDeviation}</p>
              <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
                ΔT {formatOffset(profile.active_offset)}
              </p>
              <p className="mt-1 text-sm text-gray-600">
                {messages.profile.baseline(formatOffset(profile.baseline_offset))}
              </p>
            </div>
            <button
              type="button"
              disabled={submitting}
              onClick={() => void resetOffset()}
              className={`mt-4 ${primaryButtonClass}`}
            >
              {messages.profile.resetCalibration}
            </button>
            <form className="mt-6 grid gap-4" onSubmit={(event) => void saveThermal(event)}>
              <label className={labelClass} htmlFor="profile-sensitivity">
                {messages.profile.sensitivity}
                <select
                  id="profile-sensitivity"
                  value={thermalPreference}
                  onChange={(event) => setThermalPreference(event.target.value as ThermalPreference)}
                  className={fieldClass}
                >
                  <option value="cold_sensitive">
                    {messages.profile.coldEasily} ({messages.profile.baselineCold})
                  </option>
                  <option value="balanced">
                    {messages.profile.balanced} ({messages.profile.baselineZero})
                  </option>
                  <option value="warm_sensitive">
                    {messages.profile.warmEasily} ({messages.profile.baselineWarm})
                  </option>
                </select>
              </label>
              <label className={labelClass} htmlFor="profile-routine">
                {messages.profile.routine}
                <select
                  id="profile-routine"
                  value={environmentRoutine}
                  onChange={(event) => setEnvironmentRoutine(event.target.value as EnvironmentRoutine)}
                  className={fieldClass}
                >
                  <option value="mostly_indoor">{messages.profile.indoors}</option>
                  <option value="mostly_outdoor">{messages.profile.outdoors}</option>
                </select>
              </label>
              <label className={labelClass} htmlFor="profile-gender">
                {messages.profile.gender}
                <select
                  id="profile-gender"
                  value={gender}
                  onChange={(event) => setGender(event.target.value as Gender)}
                  className={fieldClass}
                >
                  <option value="men">{messages.profile.men}</option>
                  <option value="women">{messages.profile.women}</option>
                  <option value="neutral">{messages.profile.other}</option>
                </select>
              </label>
              <label className={labelClass} htmlFor="profile-birth-year">
                {messages.profile.birthYear}
                <input
                  id="profile-birth-year"
                  type="number"
                  inputMode="numeric"
                  min={BIRTH_YEAR_MIN}
                  max={new Date().getFullYear()}
                  value={birthYear}
                  onChange={(event) => setBirthYear(event.target.value)}
                  className={fieldClass}
                  required
                />
              </label>
              <div>
                <button type="submit" disabled={submitting} className={primaryButtonClass}>
                  {messages.profile.saveThermal}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}
