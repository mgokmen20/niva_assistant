import { useCallback, useEffect, useRef, useState } from 'react'
import { AudioMuteToggle } from './components/AudioMuteToggle'
import { ClothingLayersView } from './components/ClothingLayersView'
import { AdminWorkspace } from './pages/AdminWorkspace'
import { ProfilePage } from './pages/ProfilePage'
import { useAppView } from './navigation/useAppView'
import { canOpenWorkspace } from './utils/accountRole'
import { FeedbackControls } from './components/FeedbackControls'
import { Header } from './components/Header'
import { MobileNav } from './components/MobileNav'
import { SevenDayForecast } from './components/SevenDayForecast'
import { TravelPlanner } from './components/travel/TravelPlanner'
import { LocationPicker } from './components/LocationPicker'
import { RecommendationInvite } from './components/RecommendationInvite'
import { VoiceQueryControl } from './components/VoiceQueryControl'
import { VoiceSummaryBanner } from './components/VoiceSummaryBanner'
import { WeatherOverview } from './components/WeatherOverview'
import { useAuth } from './context/AuthContext'
import { useI18n } from './i18n/useI18n'
import { useSeniorMode } from './context/SeniorModeContext'
import { ApiError, fetchCurrentRecommendation, fetchCurrentWeather } from './services/api'
import type { ActiveLocation, Meteorology, RecommendationResponse } from './types/api'
import { readStoredLocation, storeLocation } from './utils/activeLocation'
import { deviceLocationMessage, resolveDeviceLocation } from './utils/deviceLocation'
import { readAudioMuted } from './utils/audioMute'

function readWorkspaceNotice(): string | null {
  const state = window.history.state as { notice?: unknown } | null
  return typeof state?.notice === 'string' && state.notice.trim() !== '' ? state.notice : null
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }
  return 'Something went wrong. Try again.'
}

export default function App() {
  const { isSeniorMode } = useSeniorMode()
  const { language, messages } = useI18n()
  const { user, role, token, sessionReady, openAuthModal } = useAuth()
  const { view, showProfile, showWeather, showWorkspace, showTravel } = useAppView()
  const [accessNotice, setAccessNotice] = useState<string | null>(readWorkspaceNotice)
  const firstName = user?.first_name ?? null
  const [location, setLocation] = useState<ActiveLocation | null>(null)
  const [locating, setLocating] = useState(true)
  const [startupNotice, setStartupNotice] = useState<string | null>(null)
  const [weather, setWeather] = useState<Meteorology | null>(null)
  const [weatherLoading, setWeatherLoading] = useState(false)
  const [weatherError, setWeatherError] = useState<string | null>(null)
  const [recommendation, setRecommendation] = useState<RecommendationResponse | null>(null)
  const [recommending, setRecommending] = useState(false)
  const [recommendError, setRecommendError] = useState<string | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [invitePurpose, setInvitePurpose] = useState<'recommendation' | 'travel'>('recommendation')
  const [voicePlayToken, setVoicePlayToken] = useState(0)
  const [voiceAutoPlay, setVoiceAutoPlay] = useState(false)
  const [voiceReply, setVoiceReply] = useState<string | null>(null)
  const summaryLanguage = useRef(language)
  const userPickedLocation = useRef(false)

  const applyLocation = useCallback((next: ActiveLocation, fromUser: boolean) => {
    if (fromUser) {
      userPickedLocation.current = true
      setStartupNotice(null)
    }
    setLocation(next)
    setLocating(false)
    setWeather(null)
    setRecommendation(null)
    setWeatherLoading(true)
    setWeatherError(null)
    setRecommendError(null)
  }, [])

  const selectLocation = useCallback(
    (next: ActiveLocation) => {
      applyLocation(next, true)
    },
    [applyLocation],
  )

  const applyVoiceAnswer = useCallback((text: string) => {
    setVoiceAutoPlay(false)
    setVoiceReply(text)
  }, [])

  const requestSignIn = useCallback(() => {
    setInvitePurpose('recommendation')
    setInviteOpen(true)
  }, [])

  const openTravel = useCallback(() => {
    if (!sessionReady || token === null) {
      setInvitePurpose('travel')
      setInviteOpen(true)
      return
    }
    showTravel()
  }, [sessionReady, showTravel, token])

  const loadRecommendation = useCallback(() => {
    if (token === null) {
      setInviteOpen(true)
      return
    }
    if (location === null) {
      return
    }
    setRecommending(true)
    setRecommendError(null)
    void fetchCurrentRecommendation(location.lat, location.lon, location.name, firstName, token, language)
      .then((payload) => {
        const speak = !readAudioMuted()
        summaryLanguage.current = language
        setVoiceReply(null)
        setRecommendation(payload)
        setVoiceAutoPlay(speak)
        setVoicePlayToken((current) => current + 1)
      })
      .catch((error: unknown) => {
        setRecommendError(errorText(error))
      })
      .finally(() => {
        setRecommending(false)
      })
  }, [firstName, language, location, token])

  useEffect(() => {
    if (token === null || location === null || recommendation === null || summaryLanguage.current === language) {
      return
    }
    let active = true
    void fetchCurrentRecommendation(location.lat, location.lon, location.name, firstName, token, language)
      .then((payload) => {
        if (!active) {
          return
        }
        summaryLanguage.current = language
        setVoiceReply(null)
        setRecommendation(payload)
        if (!readAudioMuted()) {
          setVoiceAutoPlay(true)
          setVoicePlayToken((current) => current + 1)
        }
      })
      .catch(() => {
        // Keep the summary already on screen when a language refresh fails.
      })
    return () => {
      active = false
    }
  }, [firstName, language, location, recommendation, token])

  useEffect(() => {
    if (location !== null) {
      storeLocation(location)
    }
  }, [location])

  useEffect(() => {
    let active = true
    void resolveDeviceLocation()
      .then((next) => {
        if (!active || userPickedLocation.current) {
          return
        }
        applyLocation(next, false)
      })
      .catch((error: unknown) => {
        if (!active || userPickedLocation.current) {
          return
        }
        setLocating(false)
        setStartupNotice(deviceLocationMessage(error))
        const stored = readStoredLocation()
        if (stored !== null) {
          applyLocation(stored, false)
        }
      })
    return () => {
      active = false
    }
  }, [applyLocation])

  useEffect(() => {
    const syncNotice = () => {
      setAccessNotice(readWorkspaceNotice())
    }
    window.addEventListener('popstate', syncNotice)
    return () => {
      window.removeEventListener('popstate', syncNotice)
    }
  }, [])

  const guestTravel = view === 'travel' && sessionReady && token === null

  useEffect(() => {
    if (view !== 'workspace' || !sessionReady || canOpenWorkspace(role)) {
      return
    }
    window.history.pushState(
      { view: 'weather', notice: 'The workspace is available to partners and admins.' },
      '',
      '/',
    )
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, [role, sessionReady, view])

  useEffect(() => {
    if (location === null) {
      return
    }
    let active = true
    void fetchCurrentWeather(location.lat, location.lon)
      .then((payload) => {
        if (!active) {
          return
        }
        setWeather(payload)
        setWeatherError(null)
      })
      .catch((error: unknown) => {
        if (!active) {
          return
        }
        setWeather(null)
        setWeatherError(errorText(error))
      })
      .finally(() => {
        if (active) {
          setWeatherLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [location])

  return (
    <div
      className={`min-h-screen bg-gradient-to-b from-sky-50 via-white to-indigo-50/40 text-slate-950 ${
        isSeniorMode ? 'senior-mode' : ''
      }`}
    >
      <Header
        view={view}
        onOpenProfile={showProfile}
        onOpenWeather={showWeather}
        onOpenWorkspace={showWorkspace}
        onOpenTravel={openTravel}
      />
      <main className={view === 'workspace' ? 'pb-24 font-sans md:pb-0' : 'mx-auto max-w-6xl space-y-3 px-3.5 py-3.5 pb-28 font-sans md:space-y-5 md:px-6 md:py-5 md:pb-5'}>
        {view === 'workspace' && !sessionReady ? (
          <p className="px-4 py-8 text-center text-slate-600" role="status">
            Checking workspace access…
          </p>
        ) : null}
        {view === 'workspace' && sessionReady && canOpenWorkspace(role) ? (
          <AdminWorkspace suggestedCity={location?.name ?? ''} onExit={showWeather} />
        ) : null}
        {view === 'profile' ? <ProfilePage key={token ?? 'guest'} onBack={showWeather} /> : null}
        {view === 'travel' && token !== null ? <TravelPlanner /> : null}
        {view === 'weather' ? (
        <>
        {accessNotice ? (
          <p className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-950 ring-1 ring-amber-200" role="status">
            <span>{accessNotice}</span>
            <button
              type="button"
              onClick={() => {
                window.history.replaceState({ view: 'weather', notice: null }, '', '/')
                setAccessNotice(null)
              }}
              className="min-h-12 rounded-full bg-white px-4 font-semibold text-slate-950 ring-1 ring-amber-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
            >
              {messages.weather.dismiss}
            </button>
          </p>
        ) : null}
        <div className="grid items-start gap-3 md:gap-5 lg:grid-cols-2">
          <div className="space-y-3 md:space-y-4">
            <LocationPicker
              location={location}
              locating={locating}
              startupNotice={startupNotice}
              onChange={selectLocation}
            />
            {weatherLoading && location !== null ? (
              <p className="rounded-3xl bg-white px-4 py-8 text-center text-slate-600 shadow-sm ring-1 ring-slate-200/80" role="status">
                {messages.weather.checking(location.name)}
              </p>
            ) : null}
            {weatherError ? (
              <section className="rounded-3xl bg-white p-4 shadow-sm ring-1 ring-rose-100" role="alert">
                <h2 className="text-lg font-semibold text-rose-900">{messages.weather.unavailable}</h2>
                <p className="mt-2 text-sm text-rose-800">{weatherError}</p>
                <button
                  type="button"
                  onClick={() => {
                    if (location !== null) {
                      selectLocation(location)
                    }
                  }}
                  className="mt-4 min-h-12 w-full rounded-md border border-blue-600 bg-blue-600 px-4 font-semibold text-white shadow-sm transition duration-150 hover:bg-blue-700"
                >
                  {messages.weather.tryAgain}
                </button>
              </section>
            ) : null}
            {weather ? (
              <WeatherOverview
                effectiveTemperature={recommendation?.effective_temperature ?? weather.apparent_temperature}
                meteorology={recommendation?.meteorology ?? weather}
                personalOffset={recommendation?.personal_offset}
                isSeniorMode={isSeniorMode}
              />
            ) : null}
            <div className="flex w-full items-center gap-2">
              <button
                type="button"
                onClick={loadRecommendation}
                disabled={recommending || weather === null}
                className="min-h-12 min-w-0 flex-1 overflow-hidden rounded-md border border-blue-600 bg-blue-600 px-3 text-base font-semibold text-white shadow-sm transition duration-150 hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:opacity-60"
              >
                {recommending ? messages.recommendation.preparing : messages.recommendation.get}
              </button>
              <AudioMuteToggle />
            </div>
            {recommendError ? (
              <p className="rounded-2xl bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-950" role="alert">
                {recommendError}
              </p>
            ) : null}
            <VoiceQueryControl
              latitude={location?.lat ?? null}
              longitude={location?.lon ?? null}
              cityName={location?.name ?? ''}
              token={token}
              onAuthRequired={requestSignIn}
              onAnswer={applyVoiceAnswer}
            />
          </div>
          <div>
            {recommendation ? (
              <ClothingLayersView layers={recommendation.clothing_layers} isSeniorMode={isSeniorMode} />
            ) : (
              <section className="rounded-3xl bg-white p-5 text-slate-700 shadow-sm ring-1 ring-slate-200/80">
                <h2 className="text-lg font-semibold text-slate-950">{messages.recommendation.todaysOutfit}</h2>
                <p className="mt-2 text-sm">{messages.recommendation.requestOutfit}</p>
              </section>
            )}
          </div>
        </div>
        {(recommendation !== null || voiceReply !== null) && token !== null ? (
          <section
            aria-label="Voice summary and comfort feedback"
            className="grid items-start gap-4 rounded-3xl bg-white/80 p-4 ring-1 ring-slate-200/80 lg:grid-cols-[minmax(0,1.4fr)_minmax(16rem,1fr)]"
          >
            <VoiceSummaryBanner
              summary={voiceReply ?? recommendation?.voice_summary ?? ''}
              token={token}
              language={language}
              autoPlayToken={voicePlayToken}
              autoPlay={voiceAutoPlay}
            />
            {recommendation !== null ? (
              <FeedbackControls
                recommendationId={recommendation.recommendation_id}
                onCalibrated={loadRecommendation}
              />
            ) : null}
          </section>
        ) : null}
        {weather && location !== null ? (
          <SevenDayForecast key={`${location.lat},${location.lon}`} latitude={location.lat} longitude={location.lon} />
        ) : null}
        </>
        ) : null}
        {inviteOpen || guestTravel ? (
          <RecommendationInvite
            title={invitePurpose === 'travel' || guestTravel ? messages.travel.signInTitle : undefined}
            body={invitePurpose === 'travel' || guestTravel ? messages.travel.signInBody : undefined}
            signInLabel={invitePurpose === 'travel' || guestTravel ? messages.travel.login : undefined}
            registerLabel={invitePurpose === 'travel' || guestTravel ? messages.travel.register : undefined}
            dismissLabel={invitePurpose === 'travel' || guestTravel ? messages.travel.notNow : undefined}
            onClose={() => {
              setInviteOpen(false)
              if (token === null && view === 'travel') {
                showWeather()
              }
            }}
            onSignIn={() => {
              setInviteOpen(false)
              openAuthModal('sign-in')
            }}
            onRegister={() => {
              setInviteOpen(false)
              openAuthModal('register')
            }}
          />
        ) : null}
      </main>
      <MobileNav
        view={view}
        onOpenWeather={showWeather}
        onOpenTravel={openTravel}
        onOpenProfile={showProfile}
        onOpenWorkspace={showWorkspace}
      />
    </div>
  )
}
