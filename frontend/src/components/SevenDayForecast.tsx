import { useEffect, useState } from 'react'
import { useI18n } from '../i18n/useI18n'
import { fetchDailyForecast } from '../services/api'
import type { DailyForecastDay } from '../types/api'
import { WeatherGlyph } from './WeatherGlyph'

const WEEKDAY_KEYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'] as const

function weekdayKey(isoDate: string): (typeof WEEKDAY_KEYS)[number] {
  const parsed = new Date(`${isoDate}T12:00:00Z`)
  const index = Number.isNaN(parsed.getTime()) ? 0 : parsed.getUTCDay()
  return WEEKDAY_KEYS[index] ?? 'sunday'
}

function temperatureBar(day: DailyForecastDay, days: DailyForecastDay[]): { left: string; width: string } {
  const floor = Math.min(...days.map((item) => item.temperature_min))
  const ceil = Math.max(...days.map((item) => item.temperature_max))
  const span = Math.max(ceil - floor, 1)
  const start = ((day.temperature_min - floor) / span) * 100
  const size = Math.max(((day.temperature_max - day.temperature_min) / span) * 100, 18)
  const left = Math.min(start, 82)
  return { left: `${left}%`, width: `${Math.min(size, 100 - left)}%` }
}

/** Seven-day weather strip. It does not request a clothing recommendation. */
export function SevenDayForecast({ latitude, longitude }: { latitude: number; longitude: number }) {
  const { messages } = useI18n()
  const [days, setDays] = useState<DailyForecastDay[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    void fetchDailyForecast(latitude, longitude)
      .then((rows) => {
        if (!active) {
          return
        }
        setDays(rows.slice(0, 7))
        setFailed(false)
      })
      .catch(() => {
        if (!active) {
          return
        }
        setDays([])
        setFailed(true)
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [latitude, longitude])

  return (
    <section aria-label={messages.forecast.title} className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
      <h2 className="text-base font-semibold text-slate-950 md:text-lg">{messages.forecast.title}</h2>
      {loading ? (
        <p className="mt-2 text-sm text-slate-600" role="status">
          {messages.forecast.loading}
        </p>
      ) : null}
      {failed && !loading ? (
        <p className="mt-2 text-sm font-semibold text-rose-800" role="alert">
          {messages.forecast.unavailable}
        </p>
      ) : null}
      {days.length > 0 ? (
        <>
          <div className="mt-1 md:hidden">
            {days.map((day) => {
              const rain = Math.round(day.precipitation_probability)
              const bar = temperatureBar(day, days)
              const low = Math.round(day.temperature_min)
              const high = Math.round(day.temperature_max)
              return (
                <div
                  key={day.date}
                  className="forecast-day flex items-center justify-between gap-2 border-b border-slate-100 py-2.5 last:border-0"
                >
                  <p className="w-24 truncate text-sm font-medium text-slate-800">
                    {messages.forecast.weekdays[weekdayKey(day.date)]}
                  </p>
                  <p className="flex w-16 items-center gap-1.5 text-xs font-medium text-blue-600">
                    <WeatherGlyph code={day.weather_code} size={16} />
                    {messages.forecast.rainChance(rain)}
                  </p>
                  <p className="flex min-w-0 flex-1 items-center justify-end gap-2">
                    <span className="relative h-1 w-10 shrink-0 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
                      <span
                        className="absolute top-0 h-1 rounded-full bg-gradient-to-r from-sky-400 to-orange-300"
                        style={bar}
                      />
                    </span>
                    <span className="min-w-[70px] text-right text-sm font-semibold text-slate-700">
                      <span className="sr-only">{messages.forecast.low} </span>
                      {low}°
                      <span aria-hidden="true"> / </span>
                      <span className="sr-only">{messages.forecast.high} </span>
                      {high}°
                    </span>
                  </p>
                </div>
              )
            })}
          </div>
          <div className="mt-3 hidden gap-3 md:grid md:grid-cols-7">
            {days.map((day) => {
              const rain = Math.round(day.precipitation_probability)
              return (
                <article
                  key={day.date}
                  className="forecast-day flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-100 bg-white p-3 text-slate-950"
                >
                  <p className="truncate text-sm font-medium text-slate-800">
                    {messages.forecast.weekdays[weekdayKey(day.date)]}
                  </p>
                  <WeatherGlyph code={day.weather_code} />
                  <p className="text-xs font-medium text-blue-600">{messages.forecast.rainChance(rain)}</p>
                  <p className="text-sm font-semibold text-slate-700">
                    <span className="sr-only">{messages.forecast.low} </span>
                    {Math.round(day.temperature_min)}°
                    <span aria-hidden="true"> / </span>
                    <span className="sr-only">{messages.forecast.high} </span>
                    {Math.round(day.temperature_max)}°
                  </p>
                </article>
              )
            })}
          </div>
        </>
      ) : null}
    </section>
  )
}
