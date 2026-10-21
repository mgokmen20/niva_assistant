import { useEffect, useId, useRef, useState } from 'react'
import { Crosshair } from 'lucide-react'
import { useI18n } from '../i18n/useI18n'
import { ApiError, searchLocations } from '../services/api'
import type { ActiveLocation, LocationMatch } from '../types/api'
import { deviceLocationMessage, resolveDeviceLocation } from '../utils/deviceLocation'

interface LocationPickerProps {
  location: ActiveLocation | null
  locating: boolean
  startupNotice: string | null
  onChange: (location: ActiveLocation) => void
}

const SEARCH_DELAY_MS = 300
const MIN_QUERY_LENGTH = 2
const CITY_NAME_MAX_LENGTH = 120

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }
  return 'Something went wrong. Try again.'
}

function placeLabel(place: LocationMatch): string {
  const parts = [place.name]
  if (place.admin1 && place.admin1 !== place.name) {
    parts.push(place.admin1)
  }
  if (place.country) {
    parts.push(place.country)
  }
  const label = parts.join(', ')
  return label.length > CITY_NAME_MAX_LENGTH ? label.slice(0, CITY_NAME_MAX_LENGTH) : label
}

export function LocationPicker({ location, locating, startupNotice, onChange }: LocationPickerProps) {
  const { messages } = useI18n()
  const rootRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const timerRef = useRef<number | null>(null)
  const listId = useId()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<LocationMatch[]>([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [gpsError, setGpsError] = useState<string | null>(null)
  const [gpsPending, setGpsPending] = useState(false)

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
      }
      abortRef.current?.abort()
    }
  }, [])

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
    setSearchError(null)
    void searchLocations(text, controller.signal)
      .then((matches) => {
        if (controller.signal.aborted) {
          return
        }
        setResults(matches)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || (error instanceof DOMException && error.name === 'AbortError')) {
          return
        }
        setResults([])
        setSearchError(errorText(error))
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setSearching(false)
        }
      })
  }

  function onQueryChange(value: string) {
    setQuery(value)
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
    }
    const text = value.trim()
    if (text.length < MIN_QUERY_LENGTH) {
      abortRef.current?.abort()
      setResults([])
      setOpen(false)
      setSearching(false)
      setSearchError(null)
      return
    }
    timerRef.current = window.setTimeout(() => {
      runSearch(text)
    }, SEARCH_DELAY_MS)
  }

  function selectPlace(place: LocationMatch) {
    onChange({
      name: placeLabel(place),
      lat: place.latitude,
      lon: place.longitude,
    })
    setQuery('')
    setResults([])
    setOpen(false)
    setSearchError(null)
    setGpsError(null)
  }

  function useCurrentLocation() {
    setGpsPending(true)
    setGpsError(null)
    void resolveDeviceLocation()
      .then((next) => {
        onChange(next)
        setGpsPending(false)
        setQuery('')
        setOpen(false)
      })
      .catch((error: unknown) => {
        setGpsPending(false)
        setGpsError(deviceLocationMessage(error))
      })
  }

  return (
    <div ref={rootRef} className="relative w-full space-y-2 rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200/80">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="dash-label text-xs font-semibold uppercase tracking-wide text-slate-500">Location</p>
          <h1 className="truncate text-xl font-semibold leading-tight">
            {location?.name ?? (locating ? messages.weather.locating : messages.weather.searchCity)}
          </h1>
        </div>
        <button
          type="button"
          aria-label={messages.weather.currentLocation}
          title={messages.weather.currentLocation}
          disabled={gpsPending}
          onClick={useCurrentLocation}
          className="inline-flex min-h-12 min-w-12 shrink-0 items-center justify-center rounded-full bg-white text-slate-900 shadow-sm ring-1 ring-slate-300 disabled:opacity-60"
        >
          <Crosshair aria-hidden="true" size={20} />
        </button>
      </div>
      {gpsError ?? startupNotice ? (
        <p className="rounded-2xl bg-rose-50 px-3 py-3 text-sm font-medium text-rose-900" role="alert">
          {gpsError ?? startupNotice}
        </p>
      ) : null}
      <label className="sr-only" htmlFor="niva-city-search">
        Search cities
      </label>
      <input
        id="niva-city-search"
        className="location-search min-h-12 w-full rounded-2xl border border-slate-300 bg-white px-3 text-base"
        type="search"
        role="combobox"
        autoComplete="off"
        placeholder={messages.weather.searchCity}
        value={query}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        onChange={(event) => onQueryChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
        onFocus={() => {
          if (results.length > 0 || searchError || searching) {
            setOpen(true)
          }
        }}
      />
      {open ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="City matches"
          className="location-results absolute left-0 right-0 z-30 mt-2 max-h-64 overflow-auto rounded-2xl bg-white py-1 shadow-lg ring-1 ring-slate-200"
        >
          {searching ? (
            <li className="px-3 py-3 text-sm text-slate-600" role="status">
              Searching…
            </li>
          ) : null}
          {searchError ? (
            <li className="px-3 py-3 text-sm font-medium text-rose-900" role="alert">
              {searchError}
            </li>
          ) : null}
          {!searching && !searchError && results.length === 0 ? (
            <li className="px-3 py-3 text-sm text-slate-600">No cities found.</li>
          ) : null}
          {results.map((place) => (
            <li key={place.id} role="presentation">
              <button
                type="button"
                role="option"
                className="min-h-12 w-full px-3 text-left text-sm font-medium text-slate-950 hover:bg-slate-100"
                onClick={() => selectPlace(place)}
              >
                {placeLabel(place)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
