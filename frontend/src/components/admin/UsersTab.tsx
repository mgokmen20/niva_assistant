import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../../context/AuthContext'
import { useWorkspace } from '../../context/WorkspaceContext'
import { useTranslation } from '../../i18n/useI18n'
import {
  ApiError,
  deactivateUser,
  fetchAdminUsers,
  resetUserPassword,
  updateAdminUser,
} from '../../services/api'
import type { AccountRole, AdminUserRecord } from '../../types/api'
import { accountRole } from '../../utils/accountRole'
import { WorkspaceError, WorkspaceLoading } from './WorkspaceMessage'
import { fieldClass, primaryButton, quietButton } from './workspaceStyles'

const ROLES: AccountRole[] = ['user', 'partner', 'admin']

const ROLE_CLASS: Record<AccountRole, string> = {
  admin: 'bg-purple-100 text-purple-950',
  partner: 'bg-blue-100 text-blue-950',
  user: 'bg-slate-100 text-slate-800',
}

function messageFrom(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return fallback
}

function roleLabel(role: AccountRole, t: ReturnType<typeof useTranslation>['t']): string {
  if (role === 'admin') {
    return t('workspace.accounts.roleAdmin')
  }
  if (role === 'partner') {
    return t('workspace.accounts.rolePartner')
  }
  return t('workspace.accounts.roleUser')
}

/** Admin account table with role, password, and status actions. */
export function UsersTab() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const { refreshKey } = useWorkspace()
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<AdminUserRecord[]>([])
  const [total, setTotal] = useState(0)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [resetTarget, setResetTarget] = useState<AdminUserRecord | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    void fetchAdminUsers(page, appliedSearch)
      .then((payload) => {
        if (!active) {
          return
        }
        setError(null)
        setRows(payload.items)
        setTotal(payload.total)
        setPageSize(payload.page_size)
      })
      .catch((caught: unknown) => {
        if (active) {
          setRows([])
          setError(messageFrom(caught, t('workspace.accounts.loadError')))
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
  }, [appliedSearch, attempt, page, refreshKey, t])

  function applySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPage(1)
    setAppliedSearch(search.trim())
  }

  async function changeRole(row: AdminUserRecord, role: AccountRole) {
    setBusyId(row.id)
    setError(null)
    setNotice(null)
    try {
      const updated = await updateAdminUser(row.id, { role })
      setRows((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setNotice(t('workspace.accounts.roleUpdated', `${updated.first_name} ${updated.last_name}`))
    } catch (caught) {
      setError(messageFrom(caught, t('workspace.accounts.loadError')))
    } finally {
      setBusyId(null)
    }
  }

  async function toggleActive(row: AdminUserRecord) {
    setBusyId(row.id)
    setError(null)
    setNotice(null)
    try {
      if (row.is_active) {
        await deactivateUser(row.id)
        setRows((current) => current.map((item) => (item.id === row.id ? { ...item, is_active: false } : item)))
        setNotice(t('workspace.accounts.nowInactive', `${row.first_name} ${row.last_name}`))
      } else {
        const updated = await updateAdminUser(row.id, { is_active: true })
        setRows((current) => current.map((item) => (item.id === updated.id ? updated : item)))
        setNotice(t('workspace.accounts.activeAgain', `${updated.first_name} ${updated.last_name}`))
      }
    } catch (caught) {
      setError(messageFrom(caught, t('workspace.accounts.loadError')))
    } finally {
      setBusyId(null)
    }
  }

  const lastPage = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <form className="flex flex-wrap items-end gap-2" onSubmit={applySearch}>
        <label className="text-sm font-semibold text-slate-800" htmlFor="user-search">
          {t('workspace.accounts.searchLabel')}
          <input
            id="user-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className={`mt-1 w-72 max-w-full ${fieldClass}`}
          />
        </label>
        <button
          type="submit"
          className={primaryButton}
        >
          {t('workspace.accounts.search')}
        </button>
      </form>
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
      {notice ? (
        <p className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-950" role="status">
          {notice}
        </p>
      ) : null}
      {loading && rows.length === 0 ? <WorkspaceLoading label={t('workspace.accounts.loading')} /> : null}
      <div className="overflow-x-auto rounded-3xl bg-white shadow-sm ring-1 ring-slate-200">
        <table className="workspace-table min-w-full text-left text-sm">
          <caption className="sr-only">{t('workspace.accounts.caption')}</caption>
          <thead className="bg-slate-50 text-slate-700">
            <tr>
              <th className="px-4 py-3 font-semibold">{t('workspace.accounts.name')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.accounts.email')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.accounts.phone')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.accounts.role')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.accounts.lastIp')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.accounts.status')}</th>
              <th className="px-4 py-3 font-semibold">{t('workspace.accounts.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const role = accountRole(row.role)
              const isSelf = user?.id === row.id
              return (
                <tr key={row.id} className="border-t border-slate-200">
                  <td className="px-4 py-3 font-semibold">
                    {row.first_name} {row.last_name}
                  </td>
                  <td className="px-4 py-3">{row.email}</td>
                  <td className="px-4 py-3">{row.phone_number ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`role-badge inline-flex rounded-full px-2 py-1 text-xs font-semibold ${ROLE_CLASS[role]}`}>
                      {roleLabel(role, t)}
                    </span>
                  </td>
                  <td className="px-4 py-3">{row.last_login_ip ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span className={row.is_active ? 'font-semibold text-emerald-800' : 'font-semibold text-rose-800'}>
                      {row.is_active ? t('workspace.accounts.active') : t('workspace.accounts.inactive')}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <label className="text-xs font-semibold" htmlFor={`role-${row.id}`}>
                        {t('workspace.accounts.editRole')}
                        <select
                          id={`role-${row.id}`}
                          value={role}
                          disabled={busyId === row.id || isSelf}
                          onChange={(event) => {
                            const next = accountRole(event.target.value)
                            if (next !== role) {
                              void changeRole(row, next)
                            }
                          }}
                          className={`ml-2 ${fieldClass}`}
                        >
                          {ROLES.map((option) => (
                            <option key={option} value={option}>
                              {roleLabel(option, t)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        onClick={() => setResetTarget(row)}
                        className={quietButton}
                      >
                        {t('workspace.accounts.resetPassword')}
                      </button>
                      <button
                        type="button"
                        disabled={busyId === row.id || isSelf}
                        onClick={() => void toggleActive(row)}
                        className={quietButton}
                      >
                        {row.is_active ? t('workspace.accounts.deactivate') : t('workspace.accounts.activate')}
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {rows.length === 0 && !loading ? (
          <p className="px-4 py-6 text-sm font-medium text-slate-600">{t('workspace.accounts.empty')}</p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => setPage((current) => Math.max(1, current - 1))}
          className={quietButton}
        >
          {t('workspace.accounts.previous')}
        </button>
        <p className="text-sm font-semibold">
          {t('workspace.accounts.page', page, lastPage)}
        </p>
        <button
          type="button"
          disabled={page >= lastPage}
          onClick={() => setPage((current) => current + 1)}
          className={quietButton}
        >
          {t('workspace.accounts.next')}
        </button>
      </div>
      {resetTarget ? (
        <PasswordDialog
          account={resetTarget}
          onClose={() => setResetTarget(null)}
          onSaved={(text) => {
            setResetTarget(null)
            setNotice(text)
          }}
        />
      ) : null}
    </div>
  )
}

function PasswordDialog({
  account,
  onClose,
  onSaved,
}: {
  account: AdminUserRecord
  onClose: () => void
  onSaved: (notice: string) => void
}) {
  const { t } = useTranslation()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (password.length < 8) {
      setError(t('workspace.accounts.passwordShort'))
      return
    }
    if (password !== confirm) {
      setError(t('workspace.accounts.passwordMismatch'))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await resetUserPassword(account.id, password)
      onSaved(t('workspace.accounts.passwordSaved', `${account.first_name} ${account.last_name}`))
    } catch (caught) {
      setError(messageFrom(caught, t('workspace.accounts.loadError')))
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-4 sm:items-center">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="reset-password-title"
        className="w-full max-w-md rounded-3xl bg-white p-5 text-slate-950 shadow-2xl"
        onSubmit={(event) => void submit(event)}
      >
        <h2 id="reset-password-title" className="text-lg font-semibold">
          {t('workspace.accounts.resetTitle')}
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          {t('workspace.accounts.resetBody', `${account.first_name} ${account.last_name}`)}
        </p>
        <label className="mt-4 block text-sm font-semibold" htmlFor="reset-new-password">
          {t('workspace.accounts.newPassword')}
          <input
            id="reset-new-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
            required
            minLength={8}
          />
        </label>
        <label className="mt-3 block text-sm font-semibold" htmlFor="reset-confirm-password">
          {t('workspace.accounts.confirmPassword')}
          <input
            id="reset-confirm-password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            className="mt-1 min-h-12 w-full rounded-2xl border border-slate-300 px-3"
            required
            minLength={8}
          />
        </label>
        {error ? (
          <p className="mt-3 rounded-2xl bg-rose-50 px-3 py-3 text-sm font-semibold text-rose-950" role="alert">
            {error}
          </p>
        ) : null}
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className={`flex-1 ${quietButton}`}
          >
            {t('workspace.accounts.cancel')}
          </button>
          <button
            type="submit"
            disabled={saving}
            className={`flex-1 ${primaryButton}`}
          >
            {t('workspace.accounts.savePassword')}
          </button>
        </div>
      </form>
    </div>
  )
}
