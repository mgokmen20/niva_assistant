import { useI18n } from '../../i18n/useI18n'
import type { TripOutlookDay } from '../../types/api'
import { WeatherGlyph } from '../WeatherGlyph'

const WEEKDAY_KEYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'] as const
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

function tripDateLabel(
  isoDate: string,
  months: Record<(typeof MONTH_KEYS)[number], string>,
  weekdays: Record<(typeof WEEKDAY_KEYS)[number], string>,
): string {
  const parsed = new Date(`${isoDate}T12:00:00Z`)
  if (Number.isNaN(parsed.getTime())) {
    return isoDate
  }
  const day = String(parsed.getUTCDate()).padStart(2, '0')
  const month = months[MONTH_KEYS[parsed.getUTCMonth()] ?? 'january']
  const weekday = weekdays[WEEKDAY_KEYS[parsed.getUTCDay()] ?? 'sunday']
  return `${day} ${month} ${weekday}`
}

/** Daily conditions for the dates that produced the packing list. */
export function TripOutlook({ days }: { days: TripOutlookDay[] }) {
  const { messages } = useI18n()
  if (days.length === 0) {
    return null
  }

  return (
    <section aria-label={messages.travel.outlook} className="rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200/80">
      <h2 className="text-lg font-semibold text-slate-950">{messages.travel.outlook}</h2>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {days.map((day) => {
          const label = tripDateLabel(day.date, messages.travel.months, messages.travel.weekdaysShort)
          const rain = Math.round(day.precipitation_probability)
          const wind = messages.travel.wind(day.wind_speed.toFixed(1))
          return (
            <article
              key={day.date}
              className="forecast-day flex min-w-0 flex-col gap-2 rounded-2xl border-2 border-slate-900 bg-white p-3 text-slate-950"
            >
              <p className="text-base font-bold">{label}</p>
              <WeatherGlyph code={day.weather_code} windSpeed={day.wind_speed} />
              <p className="text-sm font-semibold">
                <span className="sr-only">{messages.forecast.low} </span>
                {Math.round(day.temperature_min)}°
                <span aria-hidden="true"> / </span>
                <span className="sr-only">{messages.forecast.high} </span>
                {Math.round(day.temperature_max)}°
              </p>
              <p className="text-sm font-bold">
                {messages.forecast.rainChance(rain)}
                <span aria-hidden="true"> · </span>
                {wind}
              </p>
            </article>
          )
        })}
      </div>
    </section>
  )
}
