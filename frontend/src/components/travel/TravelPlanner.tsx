import { useEffect, useId, useRef, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useI18n } from '../../i18n/useI18n'
import { ApiError, deleteSavedTrip, fetchSavedTrips, fetchTravelPlan, saveTrip, searchLocations, updateTripChecks } from '../../services/api'
import type { LocationMatch, SavedTrip, TravelPlan } from '../../types/api'
import { utcIsoDate } from '../../utils/utcDate'
import { TripOutlook } from './TripOutlook'
import { ChecklistShare, SavedTrips } from './TravelView'

const SEARCH_DELAY_MS = 300
const MIN_QUERY_LENGTH = 2
const MAX_TRIP_DAYS = 16

const CATEGORIES = ['base', 'mid', 'outer', 'accessory'] as const

type Destination = {
  name: string
  latitude: number
  longitude: number
}

function inclusiveDays(start: string, end: string): number {
  const startDate = new Date(`${start}T12:00:00Z`)
  const endDate = new Date(`${end}T12:00:00Z`)
  return Math.round((endDate.getTime() - startDate.getTime()) / 86_400_000) + 1
}

function errorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }
  return fallback
}

/** Signed-in packing planner. Saved trips persist checklist ticks. */
export function TravelPlanner() {
  const { token } = useAuth()
  const { language, messages } = useI18n()
  const listId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const today = utcIsoDate(0)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<LocationMatch[]>([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const [destination, setDestination] = useState<Destination | null>(null)
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(utcIsoDate(3))
  const [formError, setFormError] = useState<string | null>(null)
  const [planning, setPlanning] = useState(false)
  const [plan, setPlan] = useState<TravelPlan | null>(null)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [savedTripId, setSavedTripId] = useState<string | null>(null)
  const [trips, setTrips] = useState<SavedTrip[]>([])
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const noticeTimer = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
      }
      abortRef.current?.abort()
      if (noticeTimer.current !== null) {
        window.clearTimeout(noticeTimer.current)
      }
    }
  }, [])

  useEffect(() => {
    if (token === null) {
      return
    }
    let cancelled = false
    void fetchSavedTrips(token)
      .then((rows) => {
        if (!cancelled) {
          setTrips(rows)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFormError(messages.common.tryAgain)
        }
      })
    return () => {
      cancelled = true
    }
  }, [token, messages.common.tryAgain])

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
    }
  }, [])

  function runSearch(text: string) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setSearching(true)
    setOpen(true)
    void searchLocations(text, controller.signal)
      .then((matches) => {
        if (!controller.signal.aborted) {
          setResults(matches)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setResults([])
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSearching(false)
        }
      })
  }

  function onQueryChange(value: string) {
    setQuery(value)
    setDestination(null)
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
    }
    const text = value.trim()
    if (text.length < MIN_QUERY_LENGTH) {
      abortRef.current?.abort()
      setResults([])
      setOpen(false)
      setSearching(false)
      return
    }
    timerRef.current = window.setTimeout(() => {
      runSearch(text)
    }, SEARCH_DELAY_MS)
  }

  function selectPlace(place: LocationMatch) {
    const region = [place.admin1, place.country].filter((part): part is string => part !== null && part !== '' && part !== place.name)
    const name = [place.name, ...region].join(', ').slice(0, 120)
    setDestination({ name, latitude: place.latitude, longitude: place.longitude })
    setQuery(place.name)
    setResults([])
    setOpen(false)
  }

  function validate(): string | null {
    if (destination === null) {
      return messages.travel.chooseCity
    }
    if (startDate < today) {
      return messages.travel.past
    }
    if (endDate < startDate) {
      return messages.travel.rangeInvalid
    }
    if (inclusiveDays(startDate, endDate) > MAX_TRIP_DAYS || inclusiveDays(today, endDate) > MAX_TRIP_DAYS) {
      return messages.travel.tooLong
    }
    return null
  }

  function planTrip() {
    const problem = validate()
    setFormError(problem)
    if (problem !== null || destination === null || token === null) {
      return
    }
    setPlanning(true)
    void fetchTravelPlan(
      destination.latitude,
      destination.longitude,
      destination.name,
      startDate,
      endDate,
      token,
      language,
    )
      .then((payload) => {
        setPlan(payload)
        setChecked({})
        setSavedTripId(null)
      })
      .catch((error: unknown) => {
        setFormError(errorText(error, messages.common.tryAgain))
      })
      .finally(() => {
        setPlanning(false)
      })
  }

  function showNotice(text: string) {
    setNotice(text)
    if (noticeTimer.current !== null) {
      window.clearTimeout(noticeTimer.current)
    }
    noticeTimer.current = window.setTimeout(() => {
      setNotice(null)
    }, 2500)
  }

  function itemLabel(itemId: string): string {
    return messages.travel.items[itemId as keyof typeof messages.travel.items] ?? itemId
  }

  function toggleCurrent(itemId: string) {
    const nextChecked = checked[itemId] !== true
    setChecked((current) => ({ ...current, [itemId]: nextChecked }))
    if (savedTripId === null || token === null) {
      return
    }
    void updateTripChecks(savedTripId, [{ id: itemId, checked: nextChecked }], token)
      .then((updated) => {
        setTrips((current) => current.map((trip) => (trip.id === updated.id ? updated : trip)))
      })
      .catch((error: unknown) => {
        setChecked((current) => ({ ...current, [itemId]: !nextChecked }))
        setFormError(errorText(error, messages.common.tryAgain))
      })
  }

  function saveCurrent() {
    if (plan === null || token === null || saving) {
      return
    }
    setSaving(true)
    void saveTrip(
      {
        destination_city: plan.city_name,
        start_date: plan.start_date,
        end_date: plan.end_date,
        summary_text: plan.summary,
        packing_items: plan.items.map((item) => ({
          id: item.item_id,
          name: itemLabel(item.item_id),
          category: item.category,
          quantity: 1,
          checked: checked[item.item_id] === true,
        })),
      },
      token,
    )
      .then(async (saved) => {
        setSavedTripId(saved.id)
        const rows = await fetchSavedTrips(token)
        setTrips(rows)
        showNotice(messages.travel.tripSaved)
      })
      .catch((error: unknown) => {
        setFormError(errorText(error, messages.common.tryAgain))
      })
      .finally(() => {
        setSaving(false)
      })
  }

  function toggleSaved(tripId: string, itemId: string, nextChecked: boolean) {
    if (token === null) {
      return
    }
    setTrips((current) =>
      current.map((trip) =>
        trip.id === tripId
          ? {
              ...trip,
              packing_items: trip.packing_items.map((item) => (item.id === itemId ? { ...item, checked: nextChecked } : item)),
            }
          : trip,
      ),
    )
    if (tripId === savedTripId) {
      setChecked((current) => ({ ...current, [itemId]: nextChecked }))
    }
    void updateTripChecks(tripId, [{ id: itemId, checked: nextChecked }], token)
      .then((updated) => {
        setTrips((current) => current.map((trip) => (trip.id === updated.id ? updated : trip)))
      })
      .catch((error: unknown) => {
        setFormError(errorText(error, messages.common.tryAgain))
        void fetchSavedTrips(token).then(setTrips).catch(() => undefined)
      })
  }

  function removeTrip(tripId: string) {
    if (token === null) {
      return
    }
    void deleteSavedTrip(tripId, token)
      .then(() => {
        setTrips((current) => current.filter((trip) => trip.id !== tripId))
        if (savedTripId === tripId) {
          setSavedTripId(null)
        }
        showNotice(messages.travel.tripDeleted)
      })
      .catch((error: unknown) => {
        setFormError(errorText(error, messages.common.tryAgain))
      })
  }

  const categoryLabel: Record<(typeof CATEGORIES)[number], string> = {
    base: messages.travel.base,
    mid: messages.travel.mid,
    outer: messages.travel.outer,
    accessory: messages.travel.accessories,
  }

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold text-slate-950">{messages.travel.title}</h1>
      <form
        className="space-y-4 rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200/80"
        onSubmit={(event) => {
          event.preventDefault()
          planTrip()
        }}
      >
        <div ref={rootRef} className="relative">
          <label htmlFor="travel-city" className="text-sm font-semibold text-slate-800">
            {messages.travel.destination}
          </label>
          <input
            id="travel-city"
            value={query}
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            autoComplete="off"
            placeholder={messages.travel.destinationPlaceholder}
            onChange={(event) => onQueryChange(event.target.value)}
            className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3 text-base text-slate-950"
          />
          {open ? (
            <ul id={listId} role="listbox" className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-2xl bg-white py-1 shadow-lg ring-1 ring-slate-200">
              {searching ? <li className="px-3 py-3 text-sm text-slate-600">{messages.forecast.loading}</li> : null}
              {results.map((place) => (
                <li key={place.id}>
                  <button
                    type="button"
                    className="min-h-12 w-full px-3 text-left text-sm font-semibold text-slate-950 hover:bg-slate-50"
                    onClick={() => selectPlace(place)}
                  >
                    {place.name}
                    {place.country ? <span className="font-medium text-slate-500">, {place.country}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm font-semibold text-slate-800">
            {messages.travel.start}
            <input
              type="date"
              value={startDate}
              min={today}
              onChange={(event) => setStartDate(event.target.value)}
              className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3 text-base"
            />
          </label>
          <label className="text-sm font-semibold text-slate-800">
            {messages.travel.end}
            <input
              type="date"
              value={endDate}
              min={startDate}
              onChange={(event) => setEndDate(event.target.value)}
              className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3 text-base"
            />
          </label>
        </div>
        {formError ? (
          <p className="text-sm font-semibold text-rose-800" role="alert">
            {formError}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={planning}
            className="min-h-12 min-w-0 flex-1 rounded-md border border-blue-600 bg-blue-600 px-4 font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-60"
          >
            {planning ? messages.travel.planning : messages.travel.plan}
          </button>
          {plan ? (
            <button
              type="button"
              disabled={saving}
              onClick={saveCurrent}
              className="min-h-12 min-w-0 flex-1 rounded-md border border-slate-900 bg-slate-950 px-4 font-semibold text-white shadow-sm hover:bg-slate-800 disabled:opacity-60"
            >
              {saving ? messages.travel.savingTrip : messages.travel.saveTrip}
            </button>
          ) : null}
        </div>
      </form>
      <SavedTrips trips={trips} onToggle={toggleSaved} onDelete={removeTrip} onCopied={() => showNotice(messages.travel.copied)} onCopyFailed={() => setFormError(messages.common.tryAgain)} />
      {plan ? (
        <div className="space-y-4">
          <TripOutlook days={plan.days} />
          <section className="rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200/80" aria-label={messages.travel.summary}>
            <h2 className="text-lg font-semibold text-slate-950">{messages.travel.summary}</h2>
            <p className="mt-2 text-base leading-relaxed text-slate-800">{plan.summary}</p>
          </section>
          <section className="rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200/80" aria-label={messages.travel.checklist}>
            <h2 className="text-lg font-semibold text-slate-950">{messages.travel.checklist}</h2>
            <ChecklistShare
              title={messages.travel.tripTitle(plan.city_name)}
              startDate={plan.start_date}
              endDate={plan.end_date}
              items={plan.items.map((item) => ({
                name: itemLabel(item.item_id),
                checked: checked[item.item_id] === true,
              }))}
              onCopied={() => showNotice(messages.travel.copied)}
              onCopyFailed={() => setFormError(messages.common.tryAgain)}
            />
            <div className="mt-3 space-y-4">
              {CATEGORIES.map((category) => {
                const rows = plan.items.filter((item) => item.category === category)
                if (rows.length === 0) {
                  return null
                }
                return (
                  <div key={category}>
                    <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">{categoryLabel[category]}</h3>
                    <ul className="mt-2 space-y-2">
                      {rows.map((item) => (
                        <PackingRow
                          key={item.item_id}
                          label={itemLabel(item.item_id)}
                          checked={checked[item.item_id] === true}
                          onToggle={() => toggleCurrent(item.item_id)}
                        />
                      ))}
                    </ul>
                  </div>
                )
              })}
            </div>
          </section>
        </div>
      ) : null}
      {notice ? (
        <p role="status" className="feedback-toast fixed bottom-24 left-1/2 z-30 -translate-x-1/2 rounded-full bg-slate-950 px-4 py-3 text-sm font-semibold text-white shadow-lg">
          {notice}
        </p>
      ) : null}
    </section>
  )
}

function PackingRow({
  label,
  checked,
  onToggle,
}: {
  label: string
  checked: boolean
  onToggle: () => void
}) {
  return (
    <li>
      <label className="flex min-h-12 items-center gap-3 rounded-2xl border border-slate-200 px-3 text-base font-semibold text-slate-950">
        <input type="checkbox" checked={checked} onChange={onToggle} className="h-6 w-6 accent-blue-700" />
        <span className={checked ? 'text-slate-500 line-through' : ''}>{label}</span>
      </label>
    </li>
  )
}
