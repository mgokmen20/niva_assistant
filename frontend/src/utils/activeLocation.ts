import type { ActiveLocation } from '../types/api'

export const ACTIVE_LOCATION_STORAGE_KEY = 'niva.location'

const NAME_MAX_LENGTH = 120

function isLatitude(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= -90 && value <= 90
}

function isLongitude(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= -180 && value <= 180
}

export function readStoredLocation(): ActiveLocation | null {
  try {
    const raw = window.localStorage.getItem(ACTIVE_LOCATION_STORAGE_KEY)
    if (raw === null) {
      return null
    }
    const parsed = JSON.parse(raw) as Partial<ActiveLocation>
    if (
      typeof parsed.name !== 'string' ||
      parsed.name.trim() === '' ||
      parsed.name.length > NAME_MAX_LENGTH ||
      !isLatitude(parsed.lat) ||
      !isLongitude(parsed.lon)
    ) {
      return null
    }
    return { name: parsed.name, lat: parsed.lat, lon: parsed.lon }
  } catch {
    return null
  }
}

export function storeLocation(location: ActiveLocation): void {
  window.localStorage.setItem(ACTIVE_LOCATION_STORAGE_KEY, JSON.stringify(location))
}
