import { CloudRain, Sun, Thermometer, Wind } from 'lucide-react'
import type { ReactNode } from 'react'
import { useI18n } from '../i18n/useI18n'
import type { DiurnalPeriod, Meteorology } from '../types/api'
import { WeatherGlyph } from './WeatherGlyph'

interface WeatherOverviewProps {
  effectiveTemperature: number
  meteorology: Meteorology
  personalOffset?: number | null
  isSeniorMode?: boolean
}

function formatCelsius(value: number): string {
  return `${value.toFixed(1)}°C`
}

interface MetricProps {
  icon: ReactNode
  label: string
  value: string
}

function Metric({ icon, label, value }: MetricProps) {
  return (
    <div className="rounded-2xl bg-white/80 p-2 ring-1 ring-white md:p-3">
      <span className="weather-metric-label flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {icon}
        {label}
      </span>
      <span className="weather-metric-value mt-1 block text-lg font-semibold text-slate-950">{value}</span>
    </div>
  )
}

function periodLabel(period: string, labels: { morning: string; afternoon: string; evening: string }): string {
  if (period === 'morning') {
    return labels.morning
  }
  if (period === 'afternoon') {
    return labels.afternoon
  }
  if (period === 'evening') {
    return labels.evening
  }
  return period
}

function DiurnalRow({ periods }: { periods: DiurnalPeriod[] }) {
  const { messages } = useI18n()
  if (periods.length === 0) {
    return null
  }
  const labels = {
    morning: messages.weather.morning,
    afternoon: messages.weather.afternoon,
    evening: messages.weather.evening,
  }
  return (
    <div className="mt-3 grid grid-cols-3 gap-1.5">
      {periods.map((period) => (
        <div
          key={period.period}
          className="flex min-w-0 items-center justify-center gap-1 rounded-full bg-white/15 px-1.5 py-1 text-xs font-semibold text-white"
        >
          <span className="truncate">{periodLabel(period.period, labels)}</span>
          <WeatherGlyph code={period.weather_code} size={16} />
          <span className="shrink-0">{Math.round(period.temperature)}°</span>
        </div>
      ))}
    </div>
  )
}

function calibrationLabel(
  offset: number,
  isSeniorMode: boolean,
  senior: (degrees: string) => string,
  standard: (degrees: string) => string,
): string {
  const degrees = `${offset.toFixed(1)}°C`
  return isSeniorMode ? senior(degrees) : standard(degrees)
}

export function WeatherOverview({
  effectiveTemperature,
  meteorology,
  personalOffset = null,
  isSeniorMode = false,
}: WeatherOverviewProps) {
  const { messages } = useI18n()
  const calibratedOffset = typeof personalOffset === 'number' ? personalOffset : 0
  const showCalibration = calibratedOffset !== 0
  return (
    <section
      aria-label="Weather overview"
      className="rounded-3xl bg-gradient-to-br from-sky-600 via-sky-700 to-indigo-800 p-3.5 text-white shadow-sm md:p-5"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="weather-metric-label text-sm font-medium text-sky-100">{messages.weather.airTemperature}</p>
          <p className="mt-1 text-4xl font-semibold tracking-tight md:text-5xl">{formatCelsius(meteorology.air_temperature)}</p>
        </div>
        <p>
          <span className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-2 text-slate-950 shadow-sm ring-1 ring-slate-200">
            <span className="weather-metric-label text-xs font-semibold uppercase tracking-wide text-slate-500">
              {messages.weather.feelsLike}
            </span>
            <span className="weather-metric-value text-lg font-semibold">{formatCelsius(effectiveTemperature)}</span>
          </span>
        </p>
      </div>
      <DiurnalRow periods={meteorology.diurnal ?? []} />
      {showCalibration ? (
        <p className="calibration-badge mt-3 inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-sm font-medium text-slate-950">
          <Thermometer aria-hidden="true" size={16} />
          {calibrationLabel(calibratedOffset, isSeniorMode, messages.weather.calibratedSenior, messages.weather.calibrated)}
        </p>
      ) : null}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 md:mt-4 md:gap-3">
        <Metric
          icon={<Thermometer aria-hidden="true" className="text-sky-600" size={18} />}
          label={messages.weather.air}
          value={formatCelsius(meteorology.air_temperature)}
        />
        <Metric
          icon={<Wind aria-hidden="true" className="text-indigo-500" size={18} />}
          label={messages.weather.wind}
          value={`${meteorology.wind_speed.toFixed(1)} m/s`}
        />
        <Metric
          icon={<CloudRain aria-hidden="true" className="text-blue-500" size={18} />}
          label={messages.weather.rain}
          value={`${Math.round(meteorology.rain_probability)}%`}
        />
        <Metric
          icon={<Sun aria-hidden="true" className="text-amber-500" size={18} />}
          label={messages.weather.uv}
          value={meteorology.uv_index.toFixed(1)}
        />
      </div>
    </section>
  )
}
