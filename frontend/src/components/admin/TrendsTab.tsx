import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useWorkspace } from '../../context/WorkspaceContext'
import { bandLabel, categoryLabel, garmentLabel } from '../../i18n'
import { useTranslation } from '../../i18n/useI18n'
import { ApiError, downloadAnalyticsCsv, fetchAnalyticsTrends } from '../../services/api'
import type { AnalyticsGender, ClothingTrendBucket } from '../../types/api'
import { StorageMaintenance } from './StorageMaintenance'
import { WorkspaceError, WorkspaceLoading } from './WorkspaceMessage'
import { fieldClass, primaryButton } from './workspaceStyles'

interface TrendRow {
  city: string
  bucket: string
  gender: string
  garment: string
  category: string
  count: number
  percentage: number
}

const GENDERS = ['male', 'female', 'other'] as const

const CATEGORIES = ['base', 'mid', 'outer', 'accessory'] as const
const TEMPERATURE_BANDS = ['<5°C', '5-10°C', '11-15°C', '>15°C'] as const

type SortKey = 'count' | 'percentage'

function messageFrom(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return fallback
}

function flatten(buckets: ClothingTrendBucket[]): TrendRow[] {
  return buckets
    .flatMap((bucket) =>
      bucket.garments.map((garment) => ({
        city: bucket.city,
        bucket: bucket.bucket,
        gender: bucket.gender,
        garment: garment.garment,
        category: garment.category,
        count: garment.count,
        percentage: garment.percentage,
      })),
    )
    .sort((left, right) => right.count - left.count || left.garment.localeCompare(right.garment))
}

function genderName(labels: { male: string; female: string; other: string; unspecified: string }, value: string): string {
  if (value === 'male' || value === 'female' || value === 'other') {
    return labels[value]
  }
  return labels.unspecified
}

/** Garments grouped by temperature band, plus the anonymized CSV download. */
export function TrendsTab() {
  const { language, t } = useTranslation()
  const { role } = useAuth()
  const { city, gender, setGender, refreshKey, rangeReady, analyticsWindow } = useWorkspace()
  const [rows, setRows] = useState<TrendRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [category, setCategory] = useState<(typeof CATEGORIES)[number] | 'all'>('all')
  const [band, setBand] = useState<(typeof TEMPERATURE_BANDS)[number] | 'all'>('all')
  const [sortKey, setSortKey] = useState<SortKey>('count')
  const [sortDescending, setSortDescending] = useState(true)

  const visibleRows = useMemo(() => {
    const filtered = rows.filter((row) => {
      if (category !== 'all' && row.category !== category) {
        return false
      }
      return band === 'all' || row.bucket === band
    })
    const direction = sortDescending ? -1 : 1
    return [...filtered].sort((left, right) => {
      const delta = left[sortKey] - right[sortKey]
      if (delta !== 0) {
        return delta * direction
      }
      return left.garment.localeCompare(right.garment)
    })
  }, [band, category, rows, sortDescending, sortKey])

  function toggleSort(next: SortKey) {
    if (sortKey === next) {
      setSortDescending((current) => !current)
      return
    }
    setSortKey(next)
    setSortDescending(true)
  }

  useEffect(() => {
    if (!rangeReady) {
      return
    }
    let active = true
    void fetchAnalyticsTrends({ ...analyticsWindow(), city: city ?? undefined })
      .then((buckets) => {
        if (active) {
          setError(null)
          setRows(flatten(buckets))
        }
      })
      .catch((caught: unknown) => {
        if (active) {
          setRows([])
          setError(messageFrom(caught, t('workspace.retail.loadError')))
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

  async function exportCsv() {
    if (!rangeReady) {
      setError(t('workspace.retail.exportRange'))
      return
    }
    setExporting(true)
    setError(null)
    setNotice(null)
    try {
      await downloadAnalyticsCsv({ ...analyticsWindow(), city: city ?? undefined })
      setNotice(t('workspace.retail.downloaded'))
    } catch (caught) {
      setError(messageFrom(caught, t('workspace.retail.loadError')))
    } finally {
      setExporting(false)
    }
  }

  const place = city ?? t('workspace.retail.everyCity')
  const genderLabels = {
    male: t('workspace.men'),
    female: t('workspace.women'),
    other: t('workspace.other'),
    unspecified: t('workspace.unspecified'),
  }

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">{t('workspace.retail.title')}</h2>
          <p className="text-sm text-slate-600">{t('workspace.retail.summary', place)}</p>
        </div>
        <button
          type="button"
          disabled={exporting || !rangeReady}
          onClick={() => void exportCsv()}
          className={primaryButton}
        >
          {t('workspace.retail.exportCsv')}
        </button>
      </div>
      {notice ? (
        <p className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-950" role="status">
          {notice}
        </p>
      ) : null}
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
      {loading && rows.length === 0 ? <WorkspaceLoading label={t('workspace.retail.loading')} /> : null}
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm font-semibold text-slate-700" htmlFor="trend-category">
          {t('workspace.retail.category')}
          <select
            id="trend-category"
            value={category}
            onChange={(event) => setCategory(event.target.value as typeof category)}
            className={`mt-1 block ${fieldClass}`}
          >
            <option value="all">{t('workspace.retail.all')}</option>
            {CATEGORIES.map((option) => (
              <option key={option} value={option}>
                {categoryLabel(language, option)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-semibold text-slate-700" htmlFor="trend-band">
          {t('workspace.retail.band')}
          <select
            id="trend-band"
            value={band}
            onChange={(event) => setBand(event.target.value as typeof band)}
            className={`mt-1 block ${fieldClass}`}
          >
            <option value="all">{t('workspace.retail.all')}</option>
            {TEMPERATURE_BANDS.map((option) => (
              <option key={option} value={option}>
                {bandLabel(language, option)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-semibold text-slate-700" htmlFor="trend-gender">
          {t('workspace.gender')}
          <select
            id="trend-gender"
            value={gender}
            onChange={(event) => setGender(event.target.value as AnalyticsGender)}
            className={`mt-1 block ${fieldClass}`}
          >
            <option value="all">{t('workspace.allGenders')}</option>
            {GENDERS.map((option) => (
              <option key={option} value={option}>
                {genderName(genderLabels, option)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="overflow-x-auto rounded-3xl bg-white shadow-sm ring-1 ring-slate-200">
        <table className="workspace-table min-w-full text-left text-sm">
          <caption className="sr-only">{t('workspace.retail.caption')}</caption>
          <thead className="bg-slate-50 text-slate-700">
            <tr>
              <th className="px-4 py-3 font-semibold">{t('workspace.retail.city')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.retail.temperature')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.gender')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.retail.garment')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.retail.category')}</th>
              <th className="px-4 py-3 font-semibold" aria-sort={sortKey === 'count' ? (sortDescending ? 'descending' : 'ascending') : 'none'}>
                <button type="button" className="font-semibold underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700" onClick={() => toggleSort('count')}>
                  {t('workspace.retail.count')}
                </button>
              </th>
              <th className="px-4 py-3 font-semibold" aria-sort={sortKey === 'percentage' ? (sortDescending ? 'descending' : 'ascending') : 'none'}>
                <button type="button" className="font-semibold underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700" onClick={() => toggleSort('percentage')}>
                  {t('workspace.retail.share')}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={`${row.city}-${row.bucket}-${row.gender}-${row.category}-${row.garment}`} className="border-t border-slate-200">
                <td className="px-4 py-3 font-semibold">{row.city}</td>
                <td className="px-4 py-3">{bandLabel(language, row.bucket)}</td>
                <td className="px-4 py-3">{genderName(genderLabels, row.gender)}</td>
                <td className="px-4 py-3">{garmentLabel(language, row.garment, row.garment)}</td>
                <td className="px-4 py-3">{categoryLabel(language, row.category)}</td>
                <td className="px-4 py-3">{row.count}</td>
                <td className="px-4 py-3">{row.percentage.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {visibleRows.length === 0 && !loading ? (
          <p className="px-4 py-6 text-sm font-medium text-slate-600">
            {rows.length === 0 ? t('workspace.retail.empty') : t('workspace.retail.noMatch')}
          </p>
        ) : null}
      </div>
      {role === 'admin' ? <StorageMaintenance /> : null}
    </div>
  )
}
