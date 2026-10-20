import { useEffect, useState } from 'react'
import { bandLabel } from '../../i18n'
import { useTranslation } from '../../i18n/useI18n'
import { useWorkspace } from '../../context/WorkspaceContext'
import { ApiError, fetchAnalyticsOverview } from '../../services/api'
import type { AnalyticsOverview, GarmentStat, GenderShare, SentimentSlice, TemperatureLayerBand, TimelinePoint } from '../../types/api'
import { WorkspaceError, WorkspaceLoading } from './WorkspaceMessage'

const CARD = 'workspace-chart rounded-xl border border-slate-100 bg-white p-4 shadow-sm'

const SENTIMENT = [
  { id: 'perfect', color: '#10b981' },
  { id: 'too_cold', color: '#38bdf8' },
  { id: 'too_warm', color: '#f87171' },
] as const

const LAYERS = [
  { id: 'winter_coat', color: '#1e3a8a' },
  { id: 'light_jacket', color: '#0284c7' },
  { id: 'fleece', color: '#f59e0b' },
  { id: 't_shirt', color: '#fb7185' },
] as const

const ACCESSORIES = [
  { id: 'warm_hat', color: '#d97706' },
  { id: 'scarf', color: '#7c3aed' },
  { id: 'gloves', color: '#0284c7' },
  { id: 'sunglasses', color: '#ca8a04' },
] as const

const DEMOGRAPHICS = [
  { id: 'male', color: '#2563eb' },
  { id: 'female', color: '#7c3aed' },
  { id: 'other', color: '#64748b' },
] as const

function messageFrom(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return fallback
}

function dayLocale(language: string): string {
  if (language === 'de') {
    return 'de-CH'
  }
  if (language === 'tr') {
    return 'tr-TR'
  }
  return 'en-GB'
}

function formatDay(value: string, locale: string): string {
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' }).format(parsed)
}

function recommendationCount(point: TimelinePoint): number {
  return point.recommendations_count ?? point.recommendations
}

function feedbackCount(point: TimelinePoint): number {
  return point.feedback_count ?? point.feedback
}

function sliceFor(items: SentimentSlice[], rating: string): SentimentSlice {
  return items.find((item) => item.rating === rating) ?? { rating, count: 0, percentage: 0 }
}

function layerFor(band: TemperatureLayerBand, garment: string): GarmentStat {
  return (
    band.layers.find((item) => item.garment === garment) ?? {
      garment,
      category: '',
      count: 0,
      percentage: 0,
    }
  )
}

function sentimentTone(items: SentimentSlice[]): string {
  const ranked = [...items].sort((left, right) => right.count - left.count)
  const leader = ranked[0]
  if (leader === undefined || leader.count === 0) {
    return 'border-slate-100 bg-white text-slate-950'
  }
  if (leader.rating === 'perfect') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-950'
  }
  if (leader.rating === 'too_cold') {
    return 'border-sky-200 bg-sky-50 text-sky-950'
  }
  return 'border-rose-200 bg-rose-50 text-rose-950'
}

function sentimentSwatch(items: SentimentSlice[]): string {
  const ranked = [...items].sort((left, right) => right.count - left.count)
  const leader = ranked[0]
  if (leader === undefined || leader.count === 0) {
    return '#64748b'
  }
  return SENTIMENT.find((item) => item.id === leader.rating)?.color ?? '#64748b'
}

/** KPI cards and the four overview charts for the selected filters. */
export function OverviewTab() {
  const { t } = useTranslation()
  const { city, refreshKey, rangeReady, analyticsWindow } = useWorkspace()
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!rangeReady) {
      return
    }
    let active = true
    const query = { ...analyticsWindow(), city: city ?? undefined }
    void fetchAnalyticsOverview(query)
      .then((summary) => {
        if (!active) {
          return
        }
        setError(null)
        setOverview(summary)
      })
      .catch((caught: unknown) => {
        if (active) {
          setOverview(null)
          setError(messageFrom(caught, t('workspace.overview.loadError')))
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [analyticsWindow, attempt, city, rangeReady, refreshKey, t])

  if (loading && overview === null) {
    return (
      <div className="p-4 sm:p-6">
        <WorkspaceLoading label={t('workspace.overview.loading')} />
      </div>
    )
  }

  return (
    <div className="space-y-5 p-4 sm:p-6">
      {error ? (
        <WorkspaceError
          message={error}
          onRetry={() => {
            setLoading(true)
            setError(null)
            setAttempt((current) => current + 1)
          }}
        />
      ) : null}
      {overview ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard label={t('workspace.overview.registeredUsers')} value={String(overview.total_registered_users)} />
            <KpiCard label={t('workspace.overview.activeWearers')} value={String(overview.active_wearers)} />
            <KpiCard label={t('workspace.overview.totalRecommendations')} value={String(overview.total_recommendations)} />
            <KpiCard
              label={t('workspace.overview.satisfaction')}
              value={`${overview.thermal_satisfaction_rate.toFixed(1)}%`}
              tone={sentimentTone(overview.sentiment_breakdown)}
              swatch={sentimentSwatch(overview.sentiment_breakdown)}
            />
          </div>
          <DemographicsCard slices={overview.user_demographics_gender ?? []} />
          <div className="grid gap-4 xl:grid-cols-2">
            <section className={CARD}>
              <h2 className="text-lg font-semibold text-slate-950">{t('workspace.overview.activityTitle')}</h2>
              <p className="mt-1 text-sm font-medium text-slate-600">{t('workspace.overview.activityCaption')}</p>
              <ActivityChart points={overview.timeline} />
            </section>
            <section className={CARD}>
              <h2 className="text-lg font-semibold text-slate-950">{t('workspace.overview.sentimentTitle')}</h2>
              <p className="mt-1 text-sm font-medium text-slate-600">{t('workspace.overview.sentimentCaption')}</p>
              <SentimentDonut items={overview.sentiment_breakdown} accuracy={overview.thermal_satisfaction_rate} />
            </section>
            <section className={CARD}>
              <h2 className="text-lg font-semibold text-slate-950">{t('workspace.overview.layersTitle')}</h2>
              <p className="mt-1 text-sm font-medium text-slate-600">{t('workspace.overview.layersCaption')}</p>
              <LayerChart bands={overview.temperature_layer_breakdown} />
            </section>
            <section className={CARD}>
              <h2 className="text-lg font-semibold text-slate-950">{t('workspace.overview.accessoriesTitle')}</h2>
              <p className="mt-1 text-sm font-medium text-slate-600">{t('workspace.overview.accessoriesCaption')}</p>
              <AccessoryChart items={overview.accessories_distribution} />
            </section>
          </div>
        </>
      ) : null}
    </div>
  )
}

function shareFor(items: GenderShare[], gender: string): GenderShare {
  return items.find((item) => item.gender === gender) ?? { gender, count: 0, percentage: 0 }
}

function DemographicsCard({ slices }: { slices: GenderShare[] }) {
  const { t } = useTranslation()
  const labels: Record<(typeof DEMOGRAPHICS)[number]['id'], string> = {
    male: t('workspace.men'),
    female: t('workspace.women'),
    other: t('workspace.other'),
  }
  return (
    <section className={CARD} aria-label={t('workspace.demographics')}>
      <h2 className="text-lg font-semibold text-slate-950">{t('workspace.demographics')}</h2>
      <p className="mt-1 text-sm font-medium text-slate-600">{t('workspace.demographicsCaption')}</p>
      <div className="mt-4 flex h-3 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
        {DEMOGRAPHICS.map((item) => {
          const share = shareFor(slices, item.id)
          return (
            <span
              key={item.id}
              className="h-3"
              style={{ width: `${share.percentage}%`, backgroundColor: item.color }}
            />
          )
        })}
      </div>
      <ul className="mt-3 grid gap-2 sm:grid-cols-3">
        {DEMOGRAPHICS.map((item) => {
          const share = shareFor(slices, item.id)
          return (
            <li key={item.id} className="flex items-center justify-between gap-2 text-sm font-semibold text-slate-800">
              <span className="inline-flex min-w-0 items-center gap-2">
                <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="truncate">{labels[item.id]}</span>
              </span>
              <span className="shrink-0 tabular-nums">
                {share.percentage.toFixed(1)}% ({share.count})
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function KpiCard({
  label,
  value,
  tone = 'border-slate-100 bg-white text-slate-950',
  swatch,
}: {
  label: string
  value: string
  tone?: string
  swatch?: string
}) {
  return (
    <article className={`rounded-xl border p-4 shadow-sm ${tone}`}>
      <p className="flex items-center gap-2 text-sm font-semibold">
        {swatch ? (
          <span aria-hidden="true" className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: swatch }} />
        ) : null}
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold tracking-tight">{value}</p>
    </article>
  )
}

function Legend({ items }: { items: readonly { id: string; label: string; color: string }[] }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-2">
      {items.map((item) => (
        <li
          key={item.id}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-800"
        >
          <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
          {item.label}
        </li>
      ))}
    </ul>
  )
}

function ActivityChart({ points }: { points: TimelinePoint[] }) {
  const { language, t } = useTranslation()
  const [tip, setTip] = useState<string | null>(null)
  const locale = dayLocale(language)
  const width = 640
  const height = 240
  const padLeft = 48
  const padRight = 16
  const padTop = 16
  const padBottom = 36
  const max = Math.max(1, ...points.map((point) => Math.max(recommendationCount(point), feedbackCount(point))))
  const step = points.length <= 1 ? 0 : (width - padLeft - padRight) / (points.length - 1)
  const coords = points.map((point, index) => {
    const x = padLeft + index * step
    const recommendationY = height - padBottom - (recommendationCount(point) / max) * (height - padTop - padBottom)
    const feedbackY = height - padBottom - (feedbackCount(point) / max) * (height - padTop - padBottom)
    return { ...point, x, recommendationY, feedbackY }
  })
  const recommendationLine = coords
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.recommendationY}`)
    .join(' ')
  const feedbackLine = coords.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.feedbackY}`).join(' ')
  const ticks = coords.filter((_point, index) => index === 0 || index === coords.length - 1 || coords.length <= 8)

  return (
    <div className="mt-4">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={t('workspace.overview.activityChart')}
        className="h-60 w-full"
        onMouseLeave={() => setTip(null)}
      >
        <title>{t('workspace.overview.activityChart')}</title>
        <text x="14" y={height / 2} fill="currentColor" fontSize="12" fontWeight="700" transform={`rotate(-90 14 ${height / 2})`}>
          {t('workspace.overview.count')}
        </text>
        <text x={width / 2} y={height - 8} fill="currentColor" fontSize="12" fontWeight="700" textAnchor="middle">
          {t('workspace.overview.day')}
        </text>
        <line
          x1={padLeft}
          y1={height - padBottom}
          x2={width - padRight}
          y2={height - padBottom}
          stroke="#94a3b8"
        />
        <line x1={padLeft} y1={padTop} x2={padLeft} y2={height - padBottom} stroke="#94a3b8" />
        <text x={padLeft - 8} y={padTop + 4} fill="currentColor" fontSize="11" fontWeight="700" textAnchor="end">
          {max}
        </text>
        <text x={padLeft - 8} y={height - padBottom} fill="currentColor" fontSize="11" fontWeight="700" textAnchor="end">
          0
        </text>
        {recommendationLine !== '' ? (
          <path d={recommendationLine} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        ) : null}
        {feedbackLine !== '' ? (
          <path
            d={feedbackLine}
            fill="none"
            stroke="#7c3aed"
            strokeWidth="3"
            strokeDasharray="7 5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ) : null}
        {coords.map((point) => {
          const label = t(
            'workspace.overview.dayTip',
            formatDay(point.day, locale),
            recommendationCount(point),
            feedbackCount(point),
          )
          return (
            <g key={point.day}>
              <circle
                cx={point.x}
                cy={point.recommendationY}
                r="6"
                fill="#2563eb"
                tabIndex={0}
                aria-label={label}
                className="cursor-pointer outline-none focus-visible:stroke-slate-950"
                onMouseEnter={() => setTip(label)}
                onFocus={() => setTip(label)}
              >
                <title>{label}</title>
              </circle>
              <circle
                cx={point.x}
                cy={point.feedbackY}
                r="5"
                fill="#ffffff"
                stroke="#7c3aed"
                strokeWidth="3"
                tabIndex={0}
                aria-label={label}
                className="cursor-pointer outline-none focus-visible:stroke-slate-950"
                onMouseEnter={() => setTip(label)}
                onFocus={() => setTip(label)}
              >
                <title>{label}</title>
              </circle>
            </g>
          )
        })}
        {ticks.map((point) => (
          <text key={`tick-${point.day}`} x={point.x} y={height - 18} fill="currentColor" fontSize="11" fontWeight="700" textAnchor="middle">
            {formatDay(point.day, locale)}
          </text>
        ))}
      </svg>
      <Legend
        items={[
          { id: 'recommendations', label: t('workspace.overview.recommendations'), color: '#2563eb' },
          { id: 'feedback', label: t('workspace.overview.feedback'), color: '#7c3aed' },
        ]}
      />
      {tip ? (
        <p role="tooltip" className="mt-2 rounded-md bg-slate-950 px-3 py-2 text-sm font-semibold text-white">
          {tip}
        </p>
      ) : null}
    </div>
  )
}

function SentimentDonut({ items, accuracy }: { items: SentimentSlice[]; accuracy: number }) {
  const { t } = useTranslation()
  const [tip, setTip] = useState<string | null>(null)
  const labeled = SENTIMENT.map((series) => ({
    ...series,
    label:
      series.id === 'too_cold'
        ? t('workspace.overview.tooCold')
        : series.id === 'too_warm'
          ? t('workspace.overview.tooWarm')
          : t('workspace.overview.perfect'),
  }))
  const ordered = labeled.map((series) => ({ ...series, slice: sliceFor(items, series.id) }))
  const total = ordered.reduce((sum, item) => sum + item.slice.count, 0)
  const radius = 72
  const circumference = 2 * Math.PI * radius
  const arcs = ordered.reduce<Array<(typeof ordered)[number] & { length: number; offset: number }>>(
    (built, item) => {
      const fraction = total === 0 ? 0 : item.slice.count / total
      const length = fraction * circumference
      const offset = built.reduce((sum, arc) => sum + arc.length, 0)
      built.push({ ...item, length, offset })
      return built
    },
    [],
  )

  return (
    <div className="mt-4 flex flex-col items-center gap-4 sm:flex-row sm:items-center">
      <svg viewBox="0 0 200 200" role="img" aria-label={t('workspace.overview.sentimentChart', accuracy.toFixed(1))} className="h-52 w-52">
        <title>{t('workspace.overview.sentimentTitle')}</title>
        <circle cx="100" cy="100" r={radius} fill="none" stroke="#e2e8f0" strokeWidth="22" />
        {arcs.map((arc) =>
          arc.length <= 0 ? null : (
            <circle
              key={arc.id}
              cx="100"
              cy="100"
              r={radius}
              fill="none"
              stroke={arc.color}
              strokeWidth="22"
              strokeDasharray={`${arc.length} ${circumference - arc.length}`}
              strokeDashoffset={-arc.offset}
              strokeLinecap="butt"
              transform="rotate(-90 100 100)"
              tabIndex={0}
              aria-label={t('workspace.overview.shareTip', arc.label, arc.slice.count, arc.slice.percentage.toFixed(1))}
              className="cursor-pointer outline-none transition-opacity duration-150 hover:opacity-80 focus-visible:opacity-80"
              onMouseEnter={() =>
                setTip(t('workspace.overview.shareTip', arc.label, arc.slice.count, arc.slice.percentage.toFixed(1)))
              }
              onFocus={() =>
                setTip(t('workspace.overview.shareTip', arc.label, arc.slice.count, arc.slice.percentage.toFixed(1)))
              }
            >
              <title>{t('workspace.overview.shareTip', arc.label, arc.slice.count, arc.slice.percentage.toFixed(1))}</title>
            </circle>
          ),
        )}
        <text x="100" y="96" fill="currentColor" fontSize="28" fontWeight="700" textAnchor="middle">
          {accuracy.toFixed(1)}%
        </text>
        <text x="100" y="118" fill="currentColor" fontSize="12" fontWeight="700" textAnchor="middle">
          {t('workspace.overview.perfect')}
        </text>
      </svg>
      <div className="min-w-0 flex-1">
        <Legend items={labeled} />
        <ul className="mt-3 space-y-1 text-sm font-semibold text-slate-800">
          {ordered.map((item) => (
            <li key={item.id}>
              {item.label}: {item.slice.count} · {item.slice.percentage.toFixed(1)}%
            </li>
          ))}
        </ul>
        {tip ? (
          <p role="tooltip" className="mt-2 rounded-md bg-slate-950 px-3 py-2 text-sm font-semibold text-white">
            {tip}
          </p>
        ) : null}
      </div>
    </div>
  )
}

function layerName(id: (typeof LAYERS)[number]['id'], t: ReturnType<typeof useTranslation>['t']): string {
  if (id === 'winter_coat') {
    return t('workspace.overview.winterCoat')
  }
  if (id === 'light_jacket') {
    return t('workspace.overview.lightJacket')
  }
  if (id === 'fleece') {
    return t('workspace.overview.fleece')
  }
  return t('workspace.overview.tShirt')
}

function accessoryName(id: (typeof ACCESSORIES)[number]['id'], t: ReturnType<typeof useTranslation>['t']): string {
  if (id === 'warm_hat') {
    return t('workspace.overview.warmHat')
  }
  if (id === 'scarf') {
    return t('workspace.overview.scarf')
  }
  if (id === 'gloves') {
    return t('workspace.overview.gloves')
  }
  return t('workspace.overview.sunglasses')
}

function LayerChart({ bands }: { bands: TemperatureLayerBand[] }) {
  const { language, t } = useTranslation()
  const [tip, setTip] = useState<string | null>(null)
  const series = LAYERS.map((item) => ({ ...item, label: layerName(item.id, t) }))
  const width = 640
  const height = 260
  const padLeft = 44
  const padRight = 12
  const padTop = 12
  const padBottom = 42
  const max = Math.max(
    1,
    ...bands.flatMap((band) => series.map((item) => layerFor(band, item.id).count)),
  )
  const groupWidth = bands.length === 0 ? 0 : (width - padLeft - padRight) / bands.length
  const barWidth = 14
  const barGap = 4

  return (
    <div className="mt-4">
      {bands.length === 0 ? <p className="text-sm font-medium text-slate-600">{t('workspace.overview.noBands')}</p> : null}
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t('workspace.overview.layersChart')} className="h-64 w-full">
        <title>{t('workspace.overview.layersTitle')}</title>
        <text x="12" y={height / 2} fill="currentColor" fontSize="12" fontWeight="700" transform={`rotate(-90 12 ${height / 2})`}>
          {t('workspace.overview.outfits')}
        </text>
        <line x1={padLeft} y1={height - padBottom} x2={width - padRight} y2={height - padBottom} stroke="#94a3b8" />
        <text x={padLeft - 6} y={padTop + 8} fill="currentColor" fontSize="11" fontWeight="700" textAnchor="end">
          {max}
        </text>
        <text x={padLeft - 6} y={height - padBottom} fill="currentColor" fontSize="11" fontWeight="700" textAnchor="end">
          0
        </text>
        {bands.map((band, groupIndex) => {
          const origin = padLeft + groupIndex * groupWidth
          const barsWidth = series.length * barWidth + (series.length - 1) * barGap
          const start = origin + (groupWidth - barsWidth) / 2
          return (
            <g key={band.bucket}>
              {series.map((item, seriesIndex) => {
                const stat = layerFor(band, item.id)
                const barHeight = (stat.count / max) * (height - padTop - padBottom)
                const x = start + seriesIndex * (barWidth + barGap)
                const y = height - padBottom - barHeight
                const label = t(
                  'workspace.overview.shareTip',
                  `${bandLabel(language, band.bucket)} · ${item.label}`,
                  stat.count,
                  stat.percentage.toFixed(1),
                )
                return (
                  <rect
                    key={item.id}
                    x={x}
                    y={y}
                    width={barWidth}
                    height={barHeight}
                    rx="3"
                    fill={item.color}
                    tabIndex={0}
                    aria-label={label}
                    className="cursor-pointer outline-none transition-opacity duration-150 hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-950"
                    onMouseEnter={() => setTip(label)}
                    onFocus={() => setTip(label)}
                  >
                    <title>{label}</title>
                  </rect>
                )
              })}
              <text
                x={origin + groupWidth / 2}
                y={height - 16}
                fill="currentColor"
                fontSize="12"
                fontWeight="700"
                textAnchor="middle"
              >
                {bandLabel(language, band.bucket)}
              </text>
            </g>
          )
        })}
      </svg>
      <Legend items={series} />
      {tip ? (
        <p role="tooltip" className="mt-2 rounded-md bg-slate-950 px-3 py-2 text-sm font-semibold text-white">
          {tip}
        </p>
      ) : null}
    </div>
  )
}

function AccessoryChart({ items }: { items: GarmentStat[] }) {
  const { t } = useTranslation()
  const ordered = ACCESSORIES.map((series) => ({
    ...series,
    label: accessoryName(series.id, t),
    stat: items.find((item) => item.garment === series.id) ?? {
      garment: series.id,
      category: 'accessory',
      count: 0,
      percentage: 0,
    },
  }))
  const empty = ordered.every((item) => item.stat.count === 0)

  return (
    <div className="mt-4">
      {empty ? <p className="text-sm font-medium text-slate-600">{t('workspace.overview.noAccessories')}</p> : null}
      <ul className="mt-3 space-y-3">
        {ordered.map((item) => (
          <li key={item.id}>
            <div className="flex items-baseline justify-between text-sm font-semibold text-slate-900">
              <span>{item.label}</span>
              <span>
                {item.stat.count} · {item.stat.percentage.toFixed(1)}%
              </span>
            </div>
            <div className="mt-1 h-3 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
              <div
                className="h-full rounded-full transition-all duration-150"
                style={{ width: `${item.stat.percentage}%`, backgroundColor: item.color }}
              />
            </div>
          </li>
        ))}
      </ul>
      <Legend items={ordered} />
    </div>
  )
}
