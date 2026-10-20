import { Cloud, CloudFog, CloudLightning, CloudRain, CloudSnow, CloudSun, Sun, Wind } from 'lucide-react'

/** Matches backend WIND_SHELL_MIN_MPS. A dry breezy day uses the wind icon. */
const WINDY_FROM_MPS = 5.5

type WeatherKind = 'clear' | 'partly' | 'cloud' | 'fog' | 'rain' | 'snow' | 'thunder'

function weatherKind(code: number): WeatherKind {
  if (code === 0) {
    return 'clear'
  }
  if (code === 1 || code === 2) {
    return 'partly'
  }
  if (code === 3) {
    return 'cloud'
  }
  if (code === 45 || code === 48) {
    return 'fog'
  }
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) {
    return 'rain'
  }
  if (code >= 71 && code <= 77) {
    return 'snow'
  }
  if (code >= 95) {
    return 'thunder'
  }
  return 'cloud'
}

/** Weather icon from a WMO code. Wind replaces a dry sky when the breeze is strong. */
export function WeatherGlyph({ code, windSpeed, size = 28 }: { code: number; windSpeed?: number; size?: number }) {
  const kind = weatherKind(code)
  const className = 'text-sky-700'
  const windy = windSpeed !== undefined && windSpeed >= WINDY_FROM_MPS
  const dry = kind === 'clear' || kind === 'partly' || kind === 'cloud' || kind === 'fog'
  if (windy && dry) {
    return <Wind size={size} aria-hidden="true" className={className} />
  }
  if (kind === 'clear') {
    return <Sun size={size} aria-hidden="true" className={className} />
  }
  if (kind === 'partly') {
    return <CloudSun size={size} aria-hidden="true" className={className} />
  }
  if (kind === 'fog') {
    return <CloudFog size={size} aria-hidden="true" className={className} />
  }
  if (kind === 'rain') {
    return <CloudRain size={size} aria-hidden="true" className={className} />
  }
  if (kind === 'snow') {
    return <CloudSnow size={size} aria-hidden="true" className={className} />
  }
  if (kind === 'thunder') {
    return <CloudLightning size={size} aria-hidden="true" className={className} />
  }
  return <Cloud size={size} aria-hidden="true" className={className} />
}
