import { useTranslation } from '../../i18n/useI18n'
import { primaryButton } from './workspaceStyles'

/** Shared loading and error states for the workspace tabs. */

export function WorkspaceLoading({ label }: { label: string }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <p className="text-sm font-semibold text-slate-600">{label}</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {['one', 'two', 'three', 'four'].map((key) => (
          <div key={key} className="h-24 animate-pulse rounded-3xl bg-slate-200" />
        ))}
      </div>
    </div>
  )
}

export function WorkspaceError({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-3xl bg-rose-50 p-4 ring-1 ring-rose-200" role="alert">
      <p className="font-semibold text-rose-950">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className={`mt-3 ${primaryButton}`}
      >
        {t('workspace.retry')}
      </button>
    </div>
  )
}
