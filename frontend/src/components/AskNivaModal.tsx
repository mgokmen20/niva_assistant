import { useEffect, useId, useRef, useState } from 'react'
import { Mic, Send, X } from 'lucide-react'
import { useI18n } from '../i18n/useI18n'
import type { AppLanguage } from '../i18n/types'
import { ApiError, askAssistant } from '../services/api'
import { readAudioMuted } from '../utils/audioMute'

interface AskNivaModalProps {
  cityName: string
  token?: string | null
  onClose: () => void
  onAuthRequired: () => void
}

interface SpeechRecognitionAlternativeLike {
  readonly transcript: string
}

interface SpeechRecognitionResultLike {
  readonly isFinal: boolean
  readonly 0: SpeechRecognitionAlternativeLike
}

interface SpeechRecognitionEventLike {
  readonly results: ArrayLike<SpeechRecognitionResultLike>
}

interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionLike
}

interface DialogueTurn {
  role: 'you' | 'niva'
  text: string
}

const OFFLINE_MESSAGE = 'You are offline. Ask again when you are connected.'

function recognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === 'undefined') {
    return null
  }
  const host = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return host.SpeechRecognition ?? host.webkitSpeechRecognition ?? null
}

function speechLocale(language: AppLanguage): string {
  if (language === 'tr') {
    return 'tr-TR'
  }
  if (language === 'de') {
    return 'de-CH'
  }
  return 'en-US'
}

function visibleTranscript(event: SpeechRecognitionEventLike): string {
  let spoken = ''
  for (let index = 0; index < event.results.length; index += 1) {
    spoken += event.results[index]?.[0]?.transcript ?? ''
  }
  return spoken.trim()
}

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }
  return 'Something went wrong. Try again.'
}

function VoiceWave() {
  return (
    <span className="voice-wave" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  )
}

/** Typed and spoken questions for the signed-in wearer. */
export function AskNivaModal({ cityName, token = null, onClose, onAuthRequired }: AskNivaModalProps) {
  const { language, messages } = useI18n()
  const titleId = useId()
  const supported = recognitionConstructor() !== null
  const [draft, setDraft] = useState('')
  const [listening, setListening] = useState(false)
  const [asking, setAsking] = useState(false)
  const [turns, setTurns] = useState<DialogueTurn[]>([])
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const submittedRef = useRef(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const tokenRef = useRef(token)
  const cityRef = useRef(cityName)

  useEffect(() => {
    tokenRef.current = token
    cityRef.current = cityName
  }, [cityName, token])

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    const audio = audioRef.current
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      recognitionRef.current?.abort()
      audio?.pause()
    }
  }, [onClose])

  async function ask(question: string) {
    const spoken = question.trim()
    if (spoken === '') {
      return
    }
    if (tokenRef.current === null || tokenRef.current === '') {
      onAuthRequired()
      return
    }
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      setError(OFFLINE_MESSAGE)
      return
    }
    setAsking(true)
    setError(null)
    setDraft(spoken)
    setTurns((current) => [...current, { role: 'you', text: spoken }])
    const audio = audioRef.current
    if (audio) {
      audio.pause()
    }
    try {
      const reply = await askAssistant(spoken, cityRef.current, language, tokenRef.current)
      setTurns((current) => [...current, { role: 'niva', text: reply.answer_text }])
      setDraft('')
      if (reply.audio_base64.trim() !== '' && !readAudioMuted() && audio) {
        audio.src = `data:audio/mp3;base64,${reply.audio_base64}`
        try {
          await audio.play()
        } catch {
          audio.pause()
        }
      }
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setAsking(false)
    }
  }

  function stopListening() {
    recognitionRef.current?.stop()
    setListening(false)
  }

  function startListening() {
    if (tokenRef.current === null || tokenRef.current === '') {
      onAuthRequired()
      return
    }
    const Constructor = recognitionConstructor()
    if (!Constructor) {
      return
    }
    recognitionRef.current?.abort()
    const recognition = new Constructor()
    recognition.lang = speechLocale(language)
    recognition.interimResults = true
    recognition.continuous = true
    submittedRef.current = false
    recognition.onresult = (event) => {
      const shown = visibleTranscript(event)
      if (shown !== '') {
        setDraft(shown)
        setError(null)
      }
      const result = event.results[event.results.length - 1]
      if (result?.isFinal && shown !== '' && !submittedRef.current) {
        submittedRef.current = true
        recognition.stop()
        void ask(shown)
      }
    }
    recognition.onerror = () => {
      setListening(false)
    }
    recognition.onend = () => {
      setListening(false)
    }
    recognitionRef.current = recognition
    try {
      recognition.start()
      setListening(true)
    } catch {
      setListening(false)
    }
  }

  const copy = messages.recommendation

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-3 sm:items-center">
      <button type="button" className="absolute inset-0 bg-slate-950/40" aria-label={copy.askClose} onClick={onClose} />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative flex max-h-[85dvh] w-full max-w-lg flex-col gap-3 overflow-hidden rounded-3xl bg-white p-4 shadow-xl"
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id={titleId} className="text-lg font-semibold text-slate-950">
            {copy.askNiva}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={copy.askClose}
            className="inline-flex h-12 w-12 items-center justify-center rounded-xl text-slate-700 hover:bg-slate-100"
          >
            <X aria-hidden="true" size={20} />
          </button>
        </div>
        <div className="min-h-28 flex-1 space-y-2 overflow-y-auto" aria-live="polite">
          {turns.map((turn, index) => (
            <p
              key={`${turn.role}-${index}`}
              className={`rounded-2xl px-3 py-2 text-sm ${
                turn.role === 'you' ? 'bg-slate-100 text-slate-900' : 'bg-sky-50 text-slate-950'
              }`}
            >
              <span className="mr-2 font-semibold">{turn.role === 'you' ? copy.askYou : 'Niva'}</span>
              {turn.text}
            </p>
          ))}
          {asking ? (
            <p className="text-sm font-medium text-slate-600" role="status">
              {copy.askThinking}
            </p>
          ) : null}
        </div>
        {error ? (
          <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-900" role="alert">
            {error}
          </p>
        ) : null}
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (listening) {
              stopListening()
            }
            void ask(draft)
          }}
        >
          <label className="sr-only" htmlFor="ask-niva-question">
            {copy.askPlaceholder}
          </label>
          <input
            id="ask-niva-question"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={copy.askPlaceholder}
            className="min-h-12 min-w-0 flex-1 rounded-xl border border-slate-200 px-3 text-base text-slate-950"
          />
          <button
            type="submit"
            disabled={asking || draft.trim() === ''}
            aria-label={copy.askSend}
            className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white disabled:opacity-60"
          >
            <Send aria-hidden="true" size={18} />
          </button>
          <button
            type="button"
            disabled={!supported || asking}
            aria-pressed={listening}
            aria-label={listening ? copy.stopListening : copy.askNivaVoice}
            title={supported ? copy.askNivaVoice : copy.voiceUnsupported}
            onClick={listening ? stopListening : startListening}
            className={`voice-mic inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${
              listening ? 'bg-rose-600 text-white' : 'bg-slate-950 text-white'
            }`}
          >
            {listening ? <VoiceWave /> : <Mic aria-hidden="true" size={18} />}
          </button>
        </form>
        <audio ref={audioRef} preload="none" className="hidden" />
      </section>
    </div>
  )
}
