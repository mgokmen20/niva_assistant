import { useEffect, useRef, useState } from 'react'
import { Mic } from 'lucide-react'
import { useI18n } from '../i18n/useI18n'
import type { AppLanguage } from '../i18n/types'
import { ApiError, askNiva } from '../services/api'
import { readAudioMuted } from '../utils/audioMute'

interface VoiceQueryControlProps {
  latitude: number
  longitude: number
  cityName: string
  token?: string | null
  onAuthRequired: () => void
  onAnswer: (text: string) => void
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

interface SpeechRecognitionErrorEventLike {
  readonly error?: string
}

interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionLike
}

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

/** One-tap speech: listen, ask the voice endpoint, then speak the reply. */
export function VoiceQueryControl({
  latitude,
  longitude,
  cityName,
  token = null,
  onAuthRequired,
  onAnswer,
}: VoiceQueryControlProps) {
  const { language, messages } = useI18n()
  const copy = messages.recommendation
  const [listening, setListening] = useState(false)
  const [asking, setAsking] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const heardRef = useRef('')
  const failedRef = useRef(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const noticeTimer = useRef<number | null>(null)
  const tokenRef = useRef(token)
  const placeRef = useRef({ latitude, longitude, cityName })

  useEffect(() => {
    tokenRef.current = token
    placeRef.current = { latitude, longitude, cityName }
  }, [cityName, latitude, longitude, token])

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
      audioRef.current?.pause()
      if (noticeTimer.current !== null) {
        window.clearTimeout(noticeTimer.current)
      }
    }
  }, [])

  function showNotice(text: string) {
    setNotice(text)
    if (noticeTimer.current !== null) {
      window.clearTimeout(noticeTimer.current)
    }
    noticeTimer.current = window.setTimeout(() => {
      setNotice(null)
      noticeTimer.current = null
    }, 4000)
  }

  async function ask(question: string) {
    const spoken = question.trim()
    const bearer = tokenRef.current
    if (spoken === '' || bearer === null || bearer === '') {
      return
    }
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      showNotice(copy.offline)
      return
    }
    setAsking(true)
    setNotice(null)
    const audio = audioRef.current
    if (audio) {
      audio.pause()
    }
    try {
      const place = placeRef.current
      const reply = await askNiva(spoken, place.latitude, place.longitude, place.cityName, bearer)
      onAnswer(reply.answer_text)
      if (reply.audio_base64.trim() !== '' && !readAudioMuted() && audio) {
        audio.src = `data:audio/mp3;base64,${reply.audio_base64}`
        try {
          await audio.play()
        } catch {
          audio.pause()
        }
      }
    } catch (caught) {
      showNotice(messageFrom(caught))
    } finally {
      setAsking(false)
    }
  }

  function startListening() {
    if (tokenRef.current === null || tokenRef.current === '') {
      onAuthRequired()
      return
    }
    const Constructor = recognitionConstructor()
    if (!Constructor) {
      showNotice(copy.voiceUnsupported)
      return
    }
    recognitionRef.current?.abort()
    const recognition = new Constructor()
    recognition.lang = speechLocale(language)
    recognition.interimResults = true
    recognition.continuous = false
    heardRef.current = ''
    failedRef.current = false
    recognition.onresult = (event) => {
      const shown = visibleTranscript(event)
      if (shown !== '') {
        heardRef.current = shown
      }
    }
    recognition.onerror = (event) => {
      failedRef.current = true
      setListening(false)
      const code = event.error ?? ''
      if (code === 'aborted') {
        return
      }
      if (code === 'not-allowed' || code === 'service-not-allowed') {
        showNotice(copy.micDenied)
        return
      }
      showNotice(copy.speechMissed)
    }
    recognition.onend = () => {
      setListening(false)
      if (failedRef.current) {
        return
      }
      const spoken = heardRef.current.trim()
      if (spoken === '') {
        showNotice(copy.speechMissed)
        return
      }
      void ask(spoken)
    }
    recognitionRef.current = recognition
    try {
      recognition.start()
      setListening(true)
      setNotice(null)
    } catch {
      setListening(false)
      showNotice(copy.speechMissed)
    }
  }

  function onMicClick() {
    if (asking) {
      return
    }
    if (listening) {
      recognitionRef.current?.stop()
      return
    }
    startListening()
  }

  const status = listening ? copy.listening : asking ? copy.askThinking : null

  return (
    <>
      <button
        type="button"
        className={`voice-mic flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-4 text-white shadow-sm transition duration-150 disabled:opacity-60 ${
          listening ? 'bg-rose-600 hover:bg-rose-700' : 'bg-blue-600 hover:bg-blue-700'
        }`}
        aria-pressed={listening}
        aria-label={listening ? copy.stopListening : copy.askNivaVoice}
        disabled={asking}
        onClick={onMicClick}
      >
        {listening ? <VoiceWave /> : <Mic aria-hidden="true" size={22} />}
        <span>{listening ? copy.listening : copy.askNivaVoice}</span>
      </button>
      {status ? (
        <p
          className="fixed inset-x-4 bottom-24 z-40 mx-auto flex max-w-sm items-center justify-center gap-2 rounded-full bg-slate-950 px-4 py-3 text-sm font-semibold text-white shadow-lg md:bottom-6"
          role="status"
        >
          {listening ? <VoiceWave /> : null}
          {status}
        </p>
      ) : null}
      {notice ? (
        <p
          className="fixed inset-x-4 bottom-24 z-40 mx-auto max-w-sm rounded-2xl bg-rose-950 px-4 py-3 text-center text-sm font-semibold text-white shadow-lg md:bottom-6"
          role="alert"
        >
          {notice}
        </p>
      ) : null}
      <audio ref={audioRef} preload="none" className="hidden" />
    </>
  )
}
