import { Copy, MessageCircle, Trash2 } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import type { SavedPackingItem, SavedTrip } from '../../types/api'

const MONTH_KEYS = [
  'january',
  'february',
  'march',
  'april',
  'may',
  'june',
  'july',
  'august',
  'september',
  'october',
  'november',
  'december',
] as const

type ShareLine = {
  name: string
  checked: boolean
}

function shortDate(isoDate: string, months: Record<(typeof MONTH_KEYS)[number], string>): string {
  const parsed = new Date(`${isoDate}T12:00:00Z`)
  if (Number.isNaN(parsed.getTime())) {
    return isoDate
  }
  const day = String(parsed.getUTCDate()).padStart(2, '0')
  const month = months[MONTH_KEYS[parsed.getUTCMonth()] ?? 'january']
  return `${day} ${month}`
}

function checklistText(title: string, startDate: string, endDate: string, items: ShareLine[], months: Record<(typeof MONTH_KEYS)[number], string>): string {
  const heading = `🧳 ${title} (${shortDate(startDate, months)} - ${shortDate(endDate, months)})`
  const lines = items.map((item) => {
    const mark = item.checked ? '[x]' : '[ ]'
    return `- ${mark} ${item.name}`
  })
  return [heading, ...lines].join('\n')
}

/** WhatsApp and clipboard actions for one packing list. */
export function ChecklistShare({
  title,
  startDate,
  endDate,
  items,
  onCopied,
  onCopyFailed,
}: {
  title: string
  startDate: string
  endDate: string
  items: ShareLine[]
  onCopied: () => void
  onCopyFailed: () => void
}) {
  const { messages } = useI18n()
  const text = checklistText(title, startDate, endDate, items, messages.travel.months)

  function shareWhatsapp() {
    const url = `https://wa.me/?text=${encodeURIComponent(text)}`
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  function copyList() {
    void navigator.clipboard.writeText(text).then(onCopied).catch(onCopyFailed)
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <button
        type="button"
        onClick={shareWhatsapp}
        className="inline-flex min-h-12 items-center gap-2 rounded-md border border-emerald-700 bg-emerald-600 px-3 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700"
      >
        <MessageCircle aria-hidden="true" className="h-4 w-4" />
        {messages.travel.shareWhatsapp}
      </button>
      <button
        type="button"
        onClick={copyList}
        className="inline-flex min-h-12 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-950 shadow-sm hover:bg-slate-50"
      >
        <Copy aria-hidden="true" className="h-4 w-4" />
        {messages.travel.copyChecklist}
      </button>
    </div>
  )
}

/** Saved trips accordion. Checkbox changes are reported to the parent. */
export function SavedTrips({
  trips,
  onToggle,
  onDelete,
  onCopied,
  onCopyFailed,
}: {
  trips: SavedTrip[]
  onToggle: (tripId: string, itemId: string, checked: boolean) => void
  onDelete: (tripId: string) => void
  onCopied: () => void
  onCopyFailed: () => void
}) {
  const { messages } = useI18n()

  return (
    <section className="rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200/80" aria-label={messages.travel.myTrips}>
      <h2 className="text-lg font-semibold text-slate-950">{messages.travel.myTrips}</h2>
      {trips.length === 0 ? <p className="mt-2 text-sm text-slate-600">{messages.travel.noTrips}</p> : null}
      <div className="mt-3 space-y-2">
        {trips.map((trip) => (
          <details key={trip.id} className="rounded-2xl border border-slate-200 px-3 py-2">
            <summary className="min-h-12 cursor-pointer list-none text-base font-semibold text-slate-950">
              {messages.travel.tripTitle(trip.destination_city)}
              <span className="mt-0.5 block text-sm font-medium text-slate-500">
                {trip.start_date} – {trip.end_date}
              </span>
            </summary>
            <p className="mt-2 text-sm leading-relaxed text-slate-700">{trip.summary_text}</p>
            <ChecklistShare
              title={messages.travel.tripTitle(trip.destination_city)}
              startDate={trip.start_date}
              endDate={trip.end_date}
              items={trip.packing_items}
              onCopied={onCopied}
              onCopyFailed={onCopyFailed}
            />
            <ul className="mt-3 space-y-2">
              {trip.packing_items.map((item) => (
                <SavedItemRow
                  key={item.id}
                  item={item}
                  onToggle={(checked) => onToggle(trip.id, item.id, checked)}
                />
              ))}
            </ul>
            <button
              type="button"
              onClick={() => onDelete(trip.id)}
              className="mt-3 inline-flex min-h-12 items-center gap-2 rounded-md border border-rose-200 px-3 text-sm font-semibold text-rose-800 hover:bg-rose-50"
            >
              <Trash2 aria-hidden="true" className="h-4 w-4" />
              {messages.travel.deleteTrip}
            </button>
          </details>
        ))}
      </div>
    </section>
  )
}

function SavedItemRow({ item, onToggle }: { item: SavedPackingItem; onToggle: (checked: boolean) => void }) {
  const text = item.name
  return (
    <li>
      <label className="flex min-h-12 items-center gap-3 rounded-2xl border border-slate-200 px-3 text-base font-semibold text-slate-950">
        <input
          type="checkbox"
          checked={item.checked}
          onChange={(event) => onToggle(event.target.checked)}
          className="h-6 w-6 accent-blue-700"
        />
        <span className={item.checked ? 'text-slate-500 line-through' : ''}>{text}</span>
      </label>
    </li>
  )
}
