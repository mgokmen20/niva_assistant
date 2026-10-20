import { useEffect, useState } from 'react'
import { Check } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/useI18n'
import { useSeniorMode } from '../context/SeniorModeContext'
import { ApiError, submitFeedback } from '../services/api'
import type { ThermalRating } from '../types/api'

interface FeedbackControlsProps {
  recommendationId: string | null
  onCalibrated?: () => void
}

const RATINGS: { rating: ThermalRating; idle: string; selected: string }[] = [
  {
    rating: 'TOO_COLD',
    idle: 'bg-sky-50 text-sky-950 ring-sky-700',
    selected: 'bg-sky-800 text-white ring-sky-950',
  },
  {
    rating: 'PERFECT',
    idle: 'bg-emerald-50 text-emerald-950 ring-emerald-700',
    selected: 'bg-emerald-800 text-white ring-emerald-950',
  },
  {
    rating: 'TOO_WARM',
    idle: 'bg-rose-50 text-rose-950 ring-rose-700',
    selected: 'bg-rose-800 text-white ring-rose-950',
  },
]

function messageFrom(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }
  return fallback
}

export function FeedbackControls({ recommendationId, onCalibrated }: FeedbackControlsProps) {
  const { user, token, openAuthModal } = useAuth()
  const { isSeniorMode } = useSeniorMode()
  const { messages } = useI18n()
  const [pendingRating, setPendingRating] = useState<ThermalRating | null>(null)
  const [selectedRating, setSelectedRating] = useState<ThermalRating | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [guestPrompt, setGuestPrompt] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    if (toast === null) {
      return
    }
    const timer = window.setTimeout(() => setToast(null), 5200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const labels: Record<ThermalRating, string> = {
    TOO_COLD: messages.feedback.tooCold,
    PERFECT: messages.feedback.perfect,
    TOO_WARM: messages.feedback.tooWarm,
  }

  async function handleRate(rating: ThermalRating) {
    if (pendingRating !== null) {
      return
    }
    if (user === null || token === null) {
      setSelectedRating(rating)
      setToast(null)
      setGuestPrompt(true)
      setMessage(messages.feedback.signInPrompt)
      return
    }
    if (recommendationId === null) {
      setGuestPrompt(false)
      setMessage(messages.feedback.needsRecommendation)
      return
    }
    setPendingRating(rating)
    setGuestPrompt(false)
    setMessage(null)
    try {
      await submitFeedback(recommendationId, rating, true, token)
      setSelectedRating(rating)
      setToast(messages.feedback.toast)
      onCalibrated?.()
    } catch (error) {
      setGuestPrompt(false)
      setToast(null)
      setMessage(messageFrom(error, messages.common.tryAgain))
    } finally {
      setPendingRating(null)
    }
  }

  return (
    <section aria-label={messages.feedback.question} className="space-y-3">
      <h2 className="text-lg font-semibold text-slate-950">{messages.feedback.question}</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        {RATINGS.map(({ rating, idle, selected }) => {
          const isSelected = selectedRating === rating
          return (
            <button
              key={rating}
              type="button"
              disabled={pendingRating !== null}
              aria-pressed={isSelected}
              onClick={() => void handleRate(rating)}
              className={`feedback-choice inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-5 text-base font-semibold shadow-sm ring-2 transition duration-150 hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-950 active:scale-95 disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-60 ${
                isSelected ? `feedback-selected ${selected}` : idle
              }`}
            >
              {isSelected ? <Check aria-hidden="true" size={18} strokeWidth={3} /> : null}
              {pendingRating === rating ? messages.feedback.sending : labels[rating]}
            </button>
          )
        })}
      </div>
      {toast ? (
        <div
          className={`feedback-toast rounded-2xl px-4 py-3 text-sm font-semibold shadow-sm ring-1 ring-slate-900 ${
            isSeniorMode ? 'bg-white text-black' : 'bg-slate-950 text-white'
          }`}
          role="status"
          aria-live="polite"
        >
          <p className="flex items-start gap-2">
            <Check aria-hidden="true" className="mt-0.5 shrink-0" size={18} strokeWidth={3} />
            <span>{toast}</span>
          </p>
        </div>
      ) : null}
      {message ? (
        <div className="rounded-2xl bg-white px-3 py-3 text-sm font-medium text-slate-950 ring-2 ring-slate-900" role="alert">
          <p>{message}</p>
          {guestPrompt ? (
            <button
              type="button"
              onClick={() => openAuthModal()}
              className="mt-2 min-h-12 rounded-full bg-slate-950 px-4 font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
            >
              {messages.feedback.signIn}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
