import { LayoutDashboard, User } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/useI18n'
import type { AppView } from '../navigation/useAppView'
import { canOpenWorkspace } from '../utils/accountRole'

const ghostLink =
  'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-100 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600'

const ghostCurrent =
  'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-2 rounded-md text-sm font-medium text-gray-900 bg-gray-100 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600'

const signInButton =
  'shrink-0 whitespace-nowrap rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700'

const signOutButton =
  'shrink-0 whitespace-nowrap text-sm font-medium text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-md px-3 py-2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600'

/** Header control that opens the dedicated profile page. */
function ProfileButton({
  label,
  current,
  openLabel,
  onOpenProfile,
  showIcon,
}: {
  label: string
  current: boolean
  openLabel: string
  onOpenProfile: () => void
  showIcon: boolean
}) {
  return (
    <button
      type="button"
      onClick={onOpenProfile}
      aria-current={current ? 'page' : undefined}
      aria-label={current ? label : `${openLabel} ${label}`}
      className={current ? ghostCurrent : ghostLink}
    >
      {showIcon ? <User className="hidden lg:block" size={16} aria-hidden="true" /> : null}
      <span className="max-w-32 truncate whitespace-nowrap">{label}</span>
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
  const onProfile = view === 'profile'
  const showWorkspace = user !== null && canOpenWorkspace(role)

  if (density === 'session') {
    if (user === null) {
      return (
        <button type="button" onClick={() => openAuthModal()} className={signInButton}>
          {messages.header.signIn}
        </button>
      )
    }
    return (
      <button type="button" onClick={signOut} className={signOutButton}>
        {messages.header.signOut}
      </button>
    )
  }

  if (user === null) {
    return (
      <div className="flex flex-nowrap items-center gap-2">
        <button
          type="button"
          onClick={onOpenTravel}
          aria-current={view === 'travel' ? 'page' : undefined}
          className={view === 'travel' ? ghostCurrent : ghostLink}
        >
          {messages.header.travel}
        </button>
        <ProfileButton
          label={messages.header.profile}
          current={onProfile}
          openLabel={messages.header.openProfile}
          onOpenProfile={onOpenProfile}
          showIcon={false}
        />
        <button type="button" onClick={() => openAuthModal()} className={signInButton}>
          {messages.header.signIn}
        </button>
      </div>
    )
  }

  const name = `${user.first_name} ${user.last_name}`.trim()

  return (
    <div className="flex flex-nowrap items-center justify-end gap-2">
      <button
        type="button"
        onClick={onOpenTravel}
        aria-current={view === 'travel' ? 'page' : undefined}
        className={view === 'travel' ? ghostCurrent : ghostLink}
      >
        {messages.header.travel}
      </button>
      {showWorkspace ? (
        <button
          type="button"
          onClick={onOpenWorkspace}
          aria-current={view === 'workspace' ? 'page' : undefined}
          className={view === 'workspace' ? ghostCurrent : ghostLink}
        >
          <LayoutDashboard size={16} aria-hidden="true" />
          {messages.header.workspace}
        </button>
      ) : null}
      <ProfileButton
        label={name || messages.header.profile}
        current={onProfile}
        openLabel={messages.header.openProfile}
        onOpenProfile={onOpenProfile}
        showIcon
      />
      <button type="button" onClick={signOut} className={signOutButton}>
        {messages.header.signOut}
      </button>
    </div>
  )
}
