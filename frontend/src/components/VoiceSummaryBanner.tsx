import { useEffect, useRef, useState } from 'react'
import { Square, Volume2 } from 'lucide-react'
import { synthesizeSpeech } from '../services/api'
import type { PreferredLanguage } from '../types/api'

interface VoiceSummaryBannerProps {
  summary: string
  token: string
  language: PreferredLanguage
  autoPlayToken?: number
  autoPlay?: boolean
}

interface VoiceSummaryPlayerProps {
  summary: string
  token: string
  language: PreferredLanguage
  autoPlay: boolean
}

type SpeechPhase = 'idle' | 'playing' | 'paused'

const SPEECH_RATE = 0.96
const SPEECH_PITCH = 1.0
const PREFERRED_VOICE_NAME_HINTS = [
  'Natural',
  'Google US English',
  'Samantha',
  'Karen',
  'Daniel',
  'Premium',
] as const

function speechLocale(language: PreferredLanguage): string {
  if (language === 'de') {
    return 'de-CH'
  }
  if (language === 'tr') {
    return 'tr-TR'
  }
  return 'en-US'
}

function selectSpokenVoice(voices: SpeechSynthesisVoice[], language: PreferredLanguage): SpeechSynthesisVoice | null {
  const prefix = language === 'de' ? 'de' : language === 'tr' ? 'tr' : 'en'
  const matching = voices.filter((voice) => voice.lang.toLowerCase().startsWith(prefix))
  const pool = matching.length > 0 ? matching : voices
  for (const hint of PREFERRED_VOICE_NAME_HINTS) {
    const hintText = hint.toLowerCase()
    const match = pool.find((voice) => voice.name.toLowerCase().includes(hintText))
    if (match) {
      return match
    }
  }
  return pool[0] ?? null
}

function speechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
}

function releaseObjectUrl(urlRef: { current: string | null }) {
  if (urlRef.current !== null) {
    URL.revokeObjectURL(urlRef.current)
    urlRef.current = null
  }
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

function VoiceSummaryPlayer({ summary, token, language, autoPlay }: VoiceSummaryPlayerProps) {
  const [phase, setPhase] = useState<SpeechPhase>('idle')
  const alive = useRef(true)
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const objectUrlRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const playGeneration = useRef(0)

  function setPhaseIfMounted(next: SpeechPhase) {
    if (alive.current) {
      setPhase(next)
    }
  }

  function haltPlayback() {
    abortRef.current?.abort()
    abortRef.current = null
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
      audio.load()
    }
    releaseObjectUrl(objectUrlRef)
    if (speechSupported()) {
      window.speechSynthesis.cancel()
    }
  }

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      playGeneration.current += 1
      haltPlayback()
    }
  }, [])

  useEffect(() => {
    if (!speechSupported()) {
      return
    }
    const synth = window.speechSynthesis
    const refreshVoices = () => {
      voiceRef.current = selectSpokenVoice(synth.getVoices(), language)
    }
    refreshVoices()
    synth.addEventListener('voiceschanged', refreshVoices)
    return () => {
      synth.removeEventListener('voiceschanged', refreshVoices)
    }
  }, [language])

  function speakLocally(generation: number) {
    if (!speechSupported()) {
      setPhaseIfMounted('idle')
      return
    }
    const synth = window.speechSynthesis
    synth.cancel()
    const utterance = new SpeechSynthesisUtterance(summary)
    const voice = voiceRef.current
    const locale = speechLocale(language)
    utterance.lang = voice?.lang && voice.lang.toLowerCase().startsWith(locale.slice(0, 2)) ? voice.lang : locale
    utterance.rate = SPEECH_RATE
    utterance.pitch = SPEECH_PITCH
    if (voice) {
      utterance.voice = voice
    }
    utterance.onend = () => {
      if (playGeneration.current === generation) {
        setPhaseIfMounted('idle')
      }
    }
    utterance.onerror = () => {
      if (playGeneration.current === generation) {
        setPhaseIfMounted('idle')
      }
    }
    utterance.onpause = () => setPhaseIfMounted('paused')
    utterance.onresume = () => setPhaseIfMounted('playing')
    synth.speak(utterance)
  }

  async function playNeural(generation: number): Promise<boolean> {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      return false
    }
    const audio = audioRef.current
    if (!audio) {
      return false
    }
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const blob = await synthesizeSpeech(summary, token, language, controller.signal)
      if (!alive.current || playGeneration.current !== generation || blob.size === 0) {
        return false
      }
      releaseObjectUrl(objectUrlRef)
      const url = URL.createObjectURL(blob)
      objectUrlRef.current = url
      audio.src = url
      await audio.play()
      return playGeneration.current === generation
    } catch {
      return false
    }
  }

  async function play() {
    const generation = playGeneration.current + 1
    playGeneration.current = generation
    haltPlayback()
    setPhase('playing')
    const neural = await playNeural(generation)
    if (!alive.current || playGeneration.current !== generation) {
      return
    }
    if (neural) {
      return
    }
    speakLocally(generation)
  }

  function stop() {
    playGeneration.current += 1
    haltPlayback()
    setPhase('idle')
  }

  useEffect(() => {
    if (!autoPlay) {
      return
    }
    const timer = window.setTimeout(() => {
      void play()
    }, 0)
    return () => {
      window.clearTimeout(timer)
    }
    // This player instance is mounted for one summary and one playback request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) {
      return
    }
    const onEnded = () => {
      if (objectUrlRef.current === null) {
        return
      }
      releaseObjectUrl(objectUrlRef)
      setPhaseIfMounted('idle')
    }
    audio.addEventListener('ended', onEnded)
    return () => {
      audio.removeEventListener('ended', onEnded)
    }
  }, [])

  const playing = phase === 'playing'
  const label = playing
    ? 'Stop voice summary'
    : phase === 'paused'
      ? 'Resume voice summary'
      : 'Play voice summary'

  return (
    <section
      aria-label="Voice summary"
      className="flex items-start gap-3 rounded-3xl bg-white/90 px-4 py-4 text-slate-800 shadow-sm ring-1 ring-indigo-100"
    >
      <audio ref={audioRef} preload="none" className="hidden" />
      <button
        type="button"
        className={`voice-playback inline-flex min-h-12 min-w-12 shrink-0 items-center justify-center gap-1 rounded-full px-3 ${
          playing ? 'bg-indigo-800 text-white' : 'bg-indigo-100 text-indigo-800'
        }`}
        aria-pressed={playing}
        aria-label={label}
        onClick={playing ? stop : () => void play()}
      >
        {playing ? <Square aria-hidden="true" size={18} /> : <Volume2 aria-hidden="true" size={22} />}
        {playing ? <VoiceWave /> : null}
      </button>
      <p className="text-base leading-relaxed">{summary}</p>
    </section>
  )
}

export function VoiceSummaryBanner({
  summary,
  token,
  language,
  autoPlayToken = 0,
  autoPlay = false,
}: VoiceSummaryBannerProps) {
  return (
    <VoiceSummaryPlayer
      key={`${autoPlayToken}:${summary}`}
      summary={summary}
      token={token}
      language={language}
      autoPlay={autoPlay}
    />
  )
}
