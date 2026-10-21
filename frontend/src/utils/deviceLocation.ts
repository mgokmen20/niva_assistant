import { reverseLocation } from '../services/api'
import type { ActiveLocation, ReverseLocation } from '../types/api'

const CURRENT_LOCATION_LABEL = 'Current Location'
const CITY_NAME_MAX_LENGTH = 120

const GPS_OPTIONS: PositionOptions = {
  enableHighAccuracy: false,
  timeout: 10000,
  maximumAge: 60000,
}

function formatGpsPlaceName(place: ReverseLocation): string {
  const region = place.region.trim()
  const label = region !== '' && region !== place.name ? `${place.name}, ${region}` : place.name
  return label.length > CITY_NAME_MAX_LENGTH ? label.slice(0, CITY_NAME_MAX_LENGTH) : label
}

function isGeolocationError(error: unknown): error is GeolocationPositionError {
  return typeof error === 'object' && error !== null && 'code' in error && typeof error.code === 'number'
}

/** User-facing text when the browser cannot supply coordinates. */
export function deviceLocationMessage(error: unknown): string {
  if (isGeolocationError(error)) {
    if (error.code === error.PERMISSION_DENIED) {
      return 'Location permission was denied. Search for a city instead.'
    }
    if (error.code === error.TIMEOUT) {
      return 'Finding your location took too long. Try again or search for a city.'
    }
    return 'Your position could not be determined. Search for a city instead.'
  }
  return 'This browser cannot read your location. Search for a city instead.'
}

/** Read the device position, then resolve a place name for the dashboard. */
export async function resolveDeviceLocation(): Promise<ActiveLocation> {
  if (!('geolocation' in navigator)) {
    throw new Error('geolocation-unsupported')
  }
  const coords = await new Promise<GeolocationCoordinates>((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve(position.coords)
      },
      (error) => {
        reject(error)
      },
      GPS_OPTIONS,
    )
  })
  let name = CURRENT_LOCATION_LABEL
  try {
    const place = await reverseLocation(coords.latitude, coords.longitude)
    name = formatGpsPlaceName(place)
  } catch {
    name = CURRENT_LOCATION_LABEL
  }
  return { name, lat: coords.latitude, lon: coords.longitude }
}
