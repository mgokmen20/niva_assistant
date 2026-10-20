import { useState } from 'react'
import { Mic } from 'lucide-react'
import { AskNivaModal } from './AskNivaModal'
import { useI18n } from '../i18n/useI18n'

interface VoiceQueryControlProps {
  latitude: number
  longitude: number
  cityName: string
  token?: string | null
  onAuthRequired: () => void
}

/** Opens the Ask Niva dialog. Coordinates stay with the selected place. */
export function VoiceQueryControl({
  cityName,
  token = null,
  onAuthRequired,
}: VoiceQueryControlProps) {
  const { messages } = useI18n()
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-white shadow-sm transition duration-150 hover:bg-blue-700"
        onClick={() => {
          if (token === null || token === '') {
            onAuthRequired()
            return
          }
          setOpen(true)
        }}
      >
        <Mic aria-hidden="true" size={22} />
        <span>{messages.recommendation.askNiva}</span>
      </button>
      {open ? (
        <AskNivaModal
          cityName={cityName}
          token={token}
          onAuthRequired={onAuthRequired}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )
}
