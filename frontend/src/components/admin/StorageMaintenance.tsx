import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from '../../i18n/useI18n'
import { utcIsoDate } from '../../utils/utcDate'
import { ApiError, downloadPurgeArchive, previewPurge, purgeLogs } from '../../services/api'
import type { PurgeInterval, PurgePreview } from '../../types/api'
import { dangerButton, fieldClass, primaryButton, quietButton } from './workspaceStyles'

/** Named retention choices. Matches PURGE_AGE_DAY_CHOICES in the backend. */
const PURGE_AGE_DAYS = [30, 60, 90] as const

type PurgeChoice = (typeof PURGE_AGE_DAYS)[number] | 'custom'

function messageFrom(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return fallback
}

function intervalFor(choice: PurgeChoice, startDate: string, endDate: string): PurgeInterval {
  if (choice === 'custom') {
    return { startDate, endDate }
  }
  return { beforeDate: utcIsoDate(-choice) }
}

/** Admin-only archive and purge for historical recommendation logs. */
export function StorageMaintenance() {
  const { t } = useTranslation()
  const [choice, setChoice] = useState<PurgeChoice>(90)
  const [startDate, setStartDate] = useState(() => utcIsoDate(-90))
  const [endDate, setEndDate] = useState(() => utcIsoDate(-1))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pending, setPending] = useState<{ interval: PurgeInterval; preview: PurgePreview } | null>(null)

  const rangeReady = choice !== 'custom' || (startDate !== '' && endDate !== '' && startDate <= endDate)

  async function begin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!rangeReady) {
      setError(t('workspace.storage.rangeInvalid'))
      return
    }
    const interval = intervalFor(choice, startDate, endDate)
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await downloadPurgeArchive(interval)
      const preview = await previewPurge(interval)
      setPending({ interval, preview })
    } catch (caught) {
      setError(messageFrom(caught, t('workspace.storage.loadError')))
    } finally {
      setBusy(false)
    }
  }

  async function confirmPurge() {
    if (pending === null) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await purgeLogs(pending.interval, true)
      setPending(null)
      setNotice(t('workspace.storage.purged'))
    } catch (caught) {
      setError(messageFrom(caught, t('workspace.storage.loadError')))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <h2 className="text-lg font-semibold text-slate-950">{t('workspace.storage.title')}</h2>
      <p className="mt-1 max-w-2xl text-sm text-slate-600">{t('workspace.storage.intro')}</p>
      <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={(event) => void begin(event)}>
        <label className="text-sm font-semibold text-slate-700" htmlFor="purge-boundary">
          {t('workspace.storage.boundary')}
          <select
            id="purge-boundary"
            value={String(choice)}
            onChange={(event) => {
              const next = event.target.value
              setChoice(next === 'custom' ? 'custom' : (Number(next) as (typeof PURGE_AGE_DAYS)[number]))
            }}
            className={`mt-1 block ${fieldClass}`}
          >
            {PURGE_AGE_DAYS.map((days) => (
              <option key={days} value={days}>
                {days === 30
                  ? t('workspace.storage.older30')
                  : days === 60
                    ? t('workspace.storage.older60')
                    : t('workspace.storage.older90')}
              </option>
            ))}
            <option value="custom">{t('workspace.storage.custom')}</option>
          </select>
        </label>
        {choice === 'custom' ? (
          <>
            <label className="text-sm font-semibold text-slate-700" htmlFor="purge-start">
              {t('workspace.storage.start')}
              <input
                id="purge-start"
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                className={`mt-1 block ${fieldClass}`}
              />
            </label>
            <label className="text-sm font-semibold text-slate-700" htmlFor="purge-end">
              {t('workspace.storage.end')}
              <input
                id="purge-end"
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
                className={`mt-1 block ${fieldClass}`}
              />
            </label>
          </>
        ) : null}
        <button type="submit" className={primaryButton} disabled={busy || !rangeReady}>
          {t('workspace.storage.exportPurge')}
        </button>
      </form>
      {!rangeReady ? (
        <p className="mt-3 text-sm font-semibold text-rose-800" role="alert">
          {t('workspace.storage.rangeInvalid')}
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 rounded-2xl bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-950" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mt-3 rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-950" role="status">
          {notice}
        </p>
      ) : null}
      {pending ? (
        <PurgeDialog
          preview={pending.preview}
          busy={busy}
          onCancel={() => {
            setPending(null)
            setNotice(t('workspace.storage.cancelled'))
          }}
          onConfirm={() => void confirmPurge()}
        />
      ) : null}
    </section>
  )
}

function PurgeDialog({
  preview,
  busy,
  onCancel,
  onConfirm,
}: {
  preview: PurgePreview
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { t } = useTranslation()
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) {
        onCancel()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [busy, onCancel])

  const empty = preview.matching_count === 0

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="purge-title"
        className="w-full max-w-md rounded-3xl bg-white p-5 text-slate-950 shadow-2xl"
      >
        <h2 id="purge-title" className="text-lg font-semibold">
          {t('workspace.storage.confirmTitle')}
        </h2>
        <p className="mt-2 text-sm text-slate-700">
          {empty
            ? t('workspace.storage.confirmEmpty')
            : t(
                'workspace.storage.confirmBody',
                preview.matching_count,
                preview.matching_recommendations,
                preview.matching_feedback,
              )}
        </p>
        <p className="mt-2 text-sm font-medium text-slate-600">{t('workspace.storage.backupReady')}</p>
        <div className="mt-4 flex gap-2">
          <button type="button" className={`flex-1 ${quietButton}`} onClick={onCancel} disabled={busy}>
            {empty ? t('workspace.storage.close') : t('workspace.storage.cancel')}
          </button>
          {empty ? null : (
            <button type="button" className={`flex-1 ${dangerButton}`} onClick={onConfirm} disabled={busy}>
              {t('workspace.storage.purge')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
