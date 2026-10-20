import { useEffect, useId, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../services/api'
import type { EnvironmentRoutine, Gender, ThermalPreference } from '../types/api'

type AuthTab = 'sign-in' | 'register'

const GENDERS: { value: Gender; label: string }[] = [
  { value: 'men', label: 'Men' },
  { value: 'women', label: 'Women' },
  { value: 'neutral', label: 'Other' },
]

const SENSITIVITIES: { value: ThermalPreference; label: string }[] = [
  { value: 'cold_sensitive', label: 'Feel cold easily' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'warm_sensitive', label: 'Feel warm easily' },
]

const ROUTINES: { value: EnvironmentRoutine; label: string }[] = [
  { value: 'mostly_indoor', label: 'Mostly indoors (office/home)' },
  { value: 'mostly_outdoor', label: 'Mostly outdoors / Commuting' },
]

const BIRTH_YEAR_MIN = 1900

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }
  return 'Something went wrong. Try again.'
}

function ChoiceGroup<T extends string>({
  legend,
  name,
  options,
  value,
  onChange,
}: {
  legend: string
  name: string
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <fieldset>
      <legend className="text-sm font-semibold">{legend}</legend>
      <div className="mt-2 grid gap-2">
        {options.map((option) => {
          const selected = value === option.value
          return (
            <label
              key={option.value}
              className={`flex min-h-12 cursor-pointer items-center rounded-2xl border px-3 text-sm font-semibold ${
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
              {option.label}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

export function AuthModal() {
  const { authModalOpen, authIntent } = useAuth()
  if (!authModalOpen) {
    return null
  }
  return <AuthDialog key={authIntent} initialTab={authIntent} />
}

function AuthDialog({ initialTab }: { initialTab: AuthTab }) {
  const { authModalOpen, closeAuthModal, signIn, register } = useAuth()
  const titleId = useId()
  const [tab, setTab] = useState<AuthTab>(initialTab)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [birthYear, setBirthYear] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [gender, setGender] = useState<Gender>('neutral')
  const [thermalPreference, setThermalPreference] = useState<ThermalPreference>('balanced')
  const [environmentRoutine, setEnvironmentRoutine] = useState<EnvironmentRoutine>('mostly_indoor')
  const [rememberMe, setRememberMe] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!authModalOpen) {
      return
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeAuthModal()
      }
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKey)
    }
  }, [authModalOpen, closeAuthModal])

  async function handleSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (email.trim() === '' || password === '') {
      setError('Enter your email and password.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await signIn(email.trim(), password, rememberMe)
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (firstName.trim() === '' || lastName.trim() === '') {
      setError('Enter your first and last name.')
      return
    }
    if (email.trim() === '' || !email.includes('@')) {
      setError('Enter a valid email address.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    const year = Number(birthYear)
    const currentYear = new Date().getFullYear()
    if (!Number.isInteger(year) || year < BIRTH_YEAR_MIN || year > currentYear) {
      setError('Enter a valid birth year.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await register({
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        email: email.trim(),
        password,
        birthDate: `${year}-01-01`,
        gender,
        phoneNumber: phoneNumber.trim(),
        thermalPreference,
        environmentRoutine,
      })
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 p-4 sm:items-center">
      <div className="absolute inset-0" onClick={closeAuthModal} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 max-h-[92dvh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white p-5 text-slate-950 shadow-2xl ring-1 ring-slate-200"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id={titleId} className="text-xl font-semibold">
            Your Niva account
          </h2>
          <button
            type="button"
            onClick={closeAuthModal}
            className="min-h-12 rounded-full px-4 text-sm font-semibold text-slate-700 ring-1 ring-slate-300"
          >
            Close
          </button>
        </div>

        <div role="tablist" aria-label="Account" className="mt-4 grid grid-cols-2 gap-2">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'sign-in'}
            onClick={() => {
              setTab('sign-in')
              setError(null)
            }}
            className={`min-h-12 rounded-full text-sm font-semibold ${
              tab === 'sign-in' ? 'bg-slate-950 text-white' : 'bg-slate-100 text-slate-800'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'register'}
            onClick={() => {
              setTab('register')
              setError(null)
            }}
            className={`min-h-12 rounded-full text-sm font-semibold ${
              tab === 'register' ? 'bg-slate-950 text-white' : 'bg-slate-100 text-slate-800'
            }`}
          >
            Register
          </button>
        </div>

        {error ? (
          <p className="mt-4 rounded-2xl bg-rose-50 px-3 py-3 text-sm font-medium text-rose-900" role="alert">
            {error}
          </p>
        ) : null}

        {tab === 'sign-in' ? (
          <form className="mt-4 space-y-3" onSubmit={(event) => void handleSignIn(event)}>
            <label className="block text-sm font-semibold" htmlFor="niva-sign-in-email">
              Email
              <input
                id="niva-sign-in-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
                required
              />
            </label>
            <label className="block text-sm font-semibold" htmlFor="niva-sign-in-password">
              Password
              <input
                id="niva-sign-in-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
                required
              />
            </label>
            <label className="flex min-h-12 items-center gap-3 text-sm font-semibold" htmlFor="niva-remember-me">
              <input
                id="niva-remember-me"
                type="checkbox"
                checked={rememberMe}
                onChange={(event) => setRememberMe(event.target.checked)}
                className="h-6 w-6"
              />
              Remember me
            </label>
            <button
              type="submit"
              disabled={submitting}
              className="min-h-12 w-full rounded-full bg-indigo-800 font-semibold text-white disabled:opacity-60"
            >
              {submitting ? 'Signing in…' : 'Sign In'}
            </button>
          </form>
        ) : (
          <form className="mt-4 space-y-3" onSubmit={(event) => void handleRegister(event)}>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm font-semibold" htmlFor="niva-first-name">
                First Name
                <input
                  id="niva-first-name"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                  className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
                  required
                />
              </label>
              <label className="block text-sm font-semibold" htmlFor="niva-last-name">
                Last Name
                <input
                  id="niva-last-name"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                  className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
                  required
                />
              </label>
            </div>
            <label className="block text-sm font-semibold" htmlFor="niva-register-email">
              Email
              <input
                id="niva-register-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
                required
              />
            </label>
            <label className="block text-sm font-semibold" htmlFor="niva-register-password">
              Password
              <input
                id="niva-register-password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
                minLength={8}
                required
              />
            </label>
            <label className="block text-sm font-semibold" htmlFor="niva-phone">
              Phone Number
              <input
                id="niva-phone"
                type="tel"
                autoComplete="tel"
                value={phoneNumber}
                onChange={(event) => setPhoneNumber(event.target.value)}
                className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
                placeholder="Optional"
              />
            </label>
            <label className="block text-sm font-semibold" htmlFor="niva-birth-year">
              Birth Year
              <input
                id="niva-birth-year"
                type="number"
                inputMode="numeric"
                min={BIRTH_YEAR_MIN}
                max={new Date().getFullYear()}
                value={birthYear}
                onChange={(event) => setBirthYear(event.target.value)}
                className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
                required
              />
            </label>
            <fieldset>
              <legend className="text-sm font-semibold">Gender</legend>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {GENDERS.map((option) => {
                  const selected = gender === option.value
                  return (
                    <label
                      key={option.value}
                      className={`flex min-h-12 cursor-pointer items-center justify-center rounded-2xl border px-2 text-sm font-semibold ${
                        selected
                          ? 'border-indigo-800 bg-indigo-800 text-white'
                          : 'border-slate-300 bg-white text-slate-900'
                      }`}
                    >
                      <input
                        type="radio"
                        name="gender"
                        value={option.value}
                        checked={selected}
                        onChange={() => setGender(option.value)}
                        className="sr-only"
                      />
                      {option.label}
                    </label>
                  )
                })}
              </div>
            </fieldset>
            <ChoiceGroup
              legend="How do you usually feel?"
              name="sensitivity"
              options={SENSITIVITIES}
              value={thermalPreference}
              onChange={setThermalPreference}
            />
            <ChoiceGroup
              legend="Daily routine"
              name="routine"
              options={ROUTINES}
              value={environmentRoutine}
              onChange={setEnvironmentRoutine}
            />
            <button
              type="submit"
              disabled={submitting}
              className="min-h-12 w-full rounded-full bg-indigo-800 font-semibold text-white disabled:opacity-60"
            >
              {submitting ? 'Creating account…' : 'Create account'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
