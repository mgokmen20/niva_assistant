import { LayoutDashboard, User } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/useI18n'
import type { AppView } from '../navigation/useAppView'
import type { Gender } from '../types/api'
import { canOpenWorkspace } from '../utils/accountRole'

/** Header control that opens the dedicated profile page. */
function ProfileButton({
  label,
  current,
  profileLabel,
  openLabel,
  onOpenProfile,
}: {
  label: string
  current: boolean
  profileLabel: string
  openLabel: string
  onOpenProfile: () => void
}) {
  return (
    <button
      type="button"
      onClick={onOpenProfile}
      aria-current={current ? 'page' : undefined}
      aria-label={current ? `${profileLabel}, ${label}` : `${openLabel} ${label}`}
      className={`inline-flex min-h-12 max-w-full items-center gap-2 rounded-full px-3 text-sm font-semibold ring-1 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800 ${
        current
          ? 'bg-indigo-800 text-white ring-indigo-800'
          : 'bg-white text-slate-950 ring-slate-300 hover:bg-indigo-50 hover:ring-indigo-400'
      }`}
    >
      <User size={20} aria-hidden="true" />
      <span className="max-w-36 truncate">{label}</span>
      <span
        className={`rounded-full px-2 py-1 text-xs font-semibold ${
          current ? 'bg-white/20 text-white' : 'bg-indigo-100 text-indigo-950'
        }`}
      >
        {profileLabel}
      </span>
    </button>
  )
}

export function UserNav({
  view,
  onOpenProfile,
  onOpenWorkspace,
  onOpenTravel,
  density = 'full',
}: {
  view: AppView
  onOpenProfile: () => void
  onOpenWorkspace: () => void
  onOpenTravel: () => void
  density?: 'full' | 'session'
}) {
  const { user, role, signOut, openAuthModal } = useAuth()
  const { messages } = useI18n()
  const genderLabel: Record<Gender, string> = {
    men: messages.profile.men,
    women: messages.profile.women,
    neutral: messages.profile.other,
  }
  const onProfile = view === 'profile'
  const showWorkspace = user !== null && canOpenWorkspace(role)

  if (density === 'session') {
    if (user === null) {
      return (
        <button
          type="button"
          onClick={() => openAuthModal()}
          className="min-h-12 shrink-0 rounded-full bg-indigo-800 px-4 text-sm font-semibold text-white transition hover:bg-indigo-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
        >
          {messages.header.signIn}
        </button>
      )
    }
    return (
      <button
        type="button"
        onClick={signOut}
        className="min-h-12 shrink-0 rounded-full px-3 text-sm font-semibold text-slate-800 ring-1 ring-slate-300 transition hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
      >
        {messages.header.signOut}
      </button>
    )
  }

  if (user === null) {
    return (
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onOpenTravel}
          aria-current={view === 'travel' ? 'page' : undefined}
          className="inline-flex min-h-12 items-center rounded-full bg-white px-3 text-sm font-semibold text-slate-950 ring-1 ring-slate-300 hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
        >
          {messages.header.travel}
        </button>
        <ProfileButton
          label={messages.header.profile}
          current={onProfile}
          profileLabel={messages.header.profile}
          openLabel={messages.header.openProfile}
          onOpenProfile={onOpenProfile}
        />
        <button
          type="button"
          onClick={() => openAuthModal()}
          className="min-h-12 rounded-full bg-indigo-800 px-4 text-sm font-semibold text-white transition hover:bg-indigo-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
        >
          {messages.header.signIn}
        </button>
      </div>
    )
  }

  const name = `${user.first_name} ${user.last_name}`.trim()

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <button
        type="button"
        onClick={onOpenTravel}
        aria-current={view === 'travel' ? 'page' : undefined}
        className={`inline-flex min-h-12 items-center rounded-full px-3 text-sm font-semibold ring-1 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800 ${
          view === 'travel'
            ? 'bg-indigo-800 text-white ring-indigo-800'
            : 'bg-white text-slate-950 ring-slate-300 hover:bg-indigo-50 hover:ring-indigo-400'
        }`}
      >
        {messages.header.travel}
      </button>
      {showWorkspace ? (
        <button
          type="button"
          onClick={onOpenWorkspace}
          aria-current={view === 'workspace' ? 'page' : undefined}
          className={`inline-flex min-h-12 items-center gap-2 rounded-full px-3 text-sm font-semibold ring-1 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800 ${
            view === 'workspace'
              ? 'bg-slate-950 text-white ring-slate-950'
              : 'bg-white text-slate-950 ring-slate-300 hover:bg-slate-100 hover:ring-slate-400'
          }`}
        >
          <LayoutDashboard size={20} aria-hidden="true" />
          {messages.header.workspace}
        </button>
      ) : null}
      <ProfileButton
        label={name || messages.header.profile}
        current={onProfile}
        profileLabel={messages.header.profile}
        openLabel={messages.header.openProfile}
        onOpenProfile={onOpenProfile}
      />
      <span className="outfit-chip inline-flex min-h-8 items-center rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-800">
        {genderLabel[user.gender]}
      </span>
      <button
        type="button"
        onClick={signOut}
        className="min-h-12 rounded-full px-3 text-sm font-semibold text-slate-800 ring-1 ring-transparent transition hover:bg-slate-100 hover:ring-slate-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-800"
      >
        {messages.header.signOut}
      </button>
    </div>
  )
}
