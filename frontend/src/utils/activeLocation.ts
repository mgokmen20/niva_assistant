import type { ActiveLocation } from '../types/api'

export const ACTIVE_LOCATION_STORAGE_KEY = 'niva.location'

export const DEFAULT_LOCATION: ActiveLocation = {
  name: 'Münsingen, Bern',
  lat: 46.8732,
  lon: 7.5621,
}

const NAME_MAX_LENGTH = 120

function isLatitude(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= -90 && value <= 90
}

function isLongitude(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= -180 && value <= 180
}

export function readStoredLocation(): ActiveLocation {
  try {
    const raw = window.localStorage.getItem(ACTIVE_LOCATION_STORAGE_KEY)
    if (raw === null) {
      return DEFAULT_LOCATION
    }
    const parsed = JSON.parse(raw) as Partial<ActiveLocation>
    if (
      typeof parsed.name !== 'string' ||
      parsed.name.trim() === '' ||
      parsed.name.length > NAME_MAX_LENGTH ||
      !isLatitude(parsed.lat) ||
      !isLongitude(parsed.lon)
    ) {
      return DEFAULT_LOCATION
    }
    return { name: parsed.name, lat: parsed.lat, lon: parsed.lon }
  } catch {
    return DEFAULT_LOCATION
  }
}

export function storeLocation(location: ActiveLocation): void {
  window.localStorage.setItem(ACTIVE_LOCATION_STORAGE_KEY, JSON.stringify(location))
}
