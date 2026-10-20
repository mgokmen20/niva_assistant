import { useCallback, useEffect, useState, type FormEvent } from 'react'
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

const fieldClass =
  'mt-1 min-h-12 w-full rounded-2xl border border-slate-300 bg-white px-3 font-semibold text-slate-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800'

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

function ChoiceCards<T extends string>({
  legend,
  name,
  options,
  value,
  onChange,
  columns,
}: {
  legend: string
  name: string
  options: readonly { value: T; label: string; hint?: string }[]
  value: T
  onChange: (value: T) => void
  columns: string
}) {
  return (
    <fieldset>
      <legend className="text-sm font-semibold text-slate-800">{legend}</legend>
      <div className={`mt-2 grid gap-2 ${columns}`}>
        {options.map((option) => {
          const selected = value === option.value
          return (
            <label
              key={option.value}
              className={`flex min-h-12 cursor-pointer flex-col justify-center rounded-2xl border px-3 py-2 text-sm font-semibold transition hover:border-indigo-400 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-indigo-800 ${
                selected ? 'border-indigo-800 bg-indigo-800 text-white' : 'border-slate-300 bg-white text-slate-900'
              }`}
            >
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={selected}
                onChange={() => onChange(option.value)}
                className="sr-only"
              />
              <span>{option.label}</span>
              {option.hint ? (
                <span className={`text-xs font-medium ${selected ? 'text-indigo-100' : 'text-slate-500'}`}>
                  {option.hint}
                </span>
              ) : null}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
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
          className="inline-flex min-h-12 items-center rounded-full bg-white px-4 text-sm font-semibold text-slate-950 ring-1 ring-slate-300 transition hover:bg-slate-50 hover:ring-slate-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
        >
          {messages.profile.back}
        </button>
      </div>

      {token === null ? (
        <section className="rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200/80 md:p-6">
          <h2 className="text-lg font-semibold">{messages.profile.signInTitle}</h2>
          <p className="mt-2 text-sm text-slate-600">
            {messages.profile.signInBody}
          </p>
          <button
            type="button"
            onClick={() => openAuthModal()}
            className="mt-4 min-h-12 rounded-full bg-indigo-800 px-5 font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
          >
            {messages.profile.signIn}
          </button>
        </section>
      ) : null}

      {error ? (
        <p className="rounded-2xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-900" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-950" role="status">
          {notice}
        </p>
      ) : null}
      {loading ? (
        <p className="rounded-3xl bg-white px-4 py-8 text-center text-slate-600 shadow-sm ring-1 ring-slate-200/80" role="status">
          {messages.profile.loading}
        </p>
      ) : null}

      {token !== null && profile !== null ? (
        <div className="grid items-start gap-5 lg:grid-cols-2">
          <div className="space-y-3 md:space-y-5">
            <section className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200/80">
              <h2 className="text-lg font-semibold">{messages.profile.personal}</h2>
              <label className="mt-4 block text-sm font-semibold" htmlFor="profile-language">
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
              <form className="mt-4 space-y-3" onSubmit={(event) => void savePersonal(event)}>
                <label className="block text-sm font-semibold" htmlFor="profile-first-name">
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
                <label className="block text-sm font-semibold" htmlFor="profile-last-name">
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
                <label className="block text-sm font-semibold" htmlFor="profile-email">
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
                <label className="block text-sm font-semibold" htmlFor="profile-phone">
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
                <button
                  type="submit"
                  disabled={submitting}
                  className="min-h-12 w-full rounded-full bg-indigo-800 font-semibold text-white transition hover:bg-indigo-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800 disabled:opacity-60"
                >
                  {messages.profile.savePersonal}
                </button>
              </form>
            </section>

            <section className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200/80">
              <h2 className="text-lg font-semibold">{messages.profile.security}</h2>
              <form className="mt-4 space-y-3" onSubmit={(event) => void savePassword(event)}>
                <label className="block text-sm font-semibold" htmlFor="profile-current-password">
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
                <label className="block text-sm font-semibold" htmlFor="profile-new-password">
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
                <label className="block text-sm font-semibold" htmlFor="profile-confirm-password">
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
                <button
                  type="submit"
                  disabled={submitting}
                  className="min-h-12 w-full rounded-full bg-indigo-800 font-semibold text-white transition hover:bg-indigo-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800 disabled:opacity-60"
                >
                  {messages.profile.changePassword}
                </button>
              </form>
            </section>
          </div>

          <section className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200/80">
            <h2 className="text-lg font-semibold">{messages.profile.thermal}</h2>
            <div
              className="profile-offset mt-4 rounded-2xl bg-slate-50 px-4 py-4 ring-1 ring-slate-200"
              aria-live="polite"
            >
              <p className="text-sm font-semibold text-slate-600">{messages.profile.activeDeviation}</p>
              <p className="mt-1 text-4xl font-semibold tracking-tight text-slate-950">
                ΔT {formatOffset(profile.active_offset)}
              </p>
              <p className="mt-1 text-sm font-medium text-slate-600">
                {messages.profile.baseline(formatOffset(profile.baseline_offset))}
              </p>
            </div>
            <button
              type="button"
              disabled={submitting}
              onClick={() => void resetOffset()}
              className="mt-3 min-h-12 w-full rounded-full bg-white font-semibold text-slate-950 ring-1 ring-slate-300 transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800 disabled:opacity-60"
            >
              {messages.profile.resetCalibration}
            </button>
            <form className="mt-5 space-y-4" onSubmit={(event) => void saveThermal(event)}>
              <ChoiceCards
                legend={messages.profile.sensitivity}
                name="profile-sensitivity"
                options={[
                  { value: 'cold_sensitive', label: messages.profile.coldEasily, hint: messages.profile.baselineCold },
                  { value: 'balanced', label: messages.profile.balanced, hint: messages.profile.baselineZero },
                  { value: 'warm_sensitive', label: messages.profile.warmEasily, hint: messages.profile.baselineWarm },
                ]}
                value={thermalPreference}
                onChange={setThermalPreference}
                columns="sm:grid-cols-3"
              />
              <ChoiceCards
                legend={messages.profile.routine}
                name="profile-routine"
                options={[
                  { value: 'mostly_indoor', label: messages.profile.indoors },
                  { value: 'mostly_outdoor', label: messages.profile.outdoors },
                ]}
                value={environmentRoutine}
                onChange={setEnvironmentRoutine}
                columns="sm:grid-cols-2"
              />
              <ChoiceCards
                legend={messages.profile.gender}
                name="profile-gender"
                options={[
                  { value: 'men', label: messages.profile.men },
                  { value: 'women', label: messages.profile.women },
                  { value: 'neutral', label: messages.profile.other },
                ]}
                value={gender}
                onChange={setGender}
                columns="sm:grid-cols-3"
              />
              <label className="block text-sm font-semibold" htmlFor="profile-birth-year">
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
              <button
                type="submit"
                disabled={submitting}
                className="min-h-12 w-full rounded-full bg-indigo-800 font-semibold text-white transition hover:bg-indigo-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800 disabled:opacity-60"
              >
                {messages.profile.saveThermal}
              </button>
            </form>
          </section>
        </div>
      ) : null}
    </div>
  )
}
