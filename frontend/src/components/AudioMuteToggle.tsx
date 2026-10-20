import { useState } from 'react'
import { Volume2, VolumeX } from 'lucide-react'
import { useI18n } from '../i18n/useI18n'
import { readAudioMuted, writeAudioMuted } from '../utils/audioMute'

export function AudioMuteToggle() {
  const { messages } = useI18n()
  const [muted, setMuted] = useState(readAudioMuted)
  const label = muted ? messages.recommendation.audioOff : messages.recommendation.audioOn

  function toggleMute() {
    const next = !muted
    writeAudioMuted(next)
    setMuted(next)
  }

  return (
    <button
      type="button"
      onClick={toggleMute}
      aria-pressed={muted}
      aria-label={label}
      title={label}
      className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border-2 shadow-sm transition duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-950 ${
        muted
          ? 'border-slate-950 bg-white text-slate-950 hover:bg-slate-100'
          : 'border-blue-800 bg-blue-600 text-white hover:bg-blue-700'
      }`}
    >
      {muted ? <VolumeX aria-hidden="true" size={22} /> : <Volume2 aria-hidden="true" size={22} />}
    </button>
  )
}
