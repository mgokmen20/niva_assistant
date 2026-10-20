import { House, LayoutDashboard, Luggage, UserRound } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/useI18n'
import type { AppView } from '../navigation/useAppView'
import { canOpenWorkspace } from '../utils/accountRole'

/** Bottom bar for screens under 768px. Desktop keeps the header links. */
export function MobileNav({
  view,
  onOpenWeather,
  onOpenTravel,
  onOpenProfile,
  onOpenWorkspace,
}: {
  view: AppView
  onOpenWeather: () => void
  onOpenTravel: () => void
  onOpenProfile: () => void
  onOpenWorkspace: () => void
}) {
  const { role, user } = useAuth()
  const { messages } = useI18n()
  const showWorkspace = user !== null && canOpenWorkspace(role)
  const items = [
    { id: 'weather' as const, label: messages.header.home, icon: House, onClick: onOpenWeather },
    { id: 'travel' as const, label: messages.header.travel, icon: Luggage, onClick: onOpenTravel },
    { id: 'profile' as const, label: messages.header.profile, icon: UserRound, onClick: onOpenProfile },
    ...(showWorkspace
      ? [{ id: 'workspace' as const, label: messages.header.workspace, icon: LayoutDashboard, onClick: onOpenWorkspace }]
      : []),
  ]

  return (
    <nav
      aria-label={messages.header.home}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className={`grid ${showWorkspace ? 'grid-cols-4' : 'grid-cols-3'}`}>
        {items.map((item) => {
          const selected = view === item.id
          const Icon = item.icon
          return (
            <li key={item.id}>
              <button
                type="button"
                onClick={item.onClick}
                aria-current={selected ? 'page' : undefined}
                className={`flex min-h-12 w-full flex-col items-center justify-center gap-0.5 px-1 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-blue-700 ${
                  selected ? 'text-blue-700' : 'text-slate-600'
                }`}
              >
                <Icon size={22} aria-hidden="true" />
                <span className="max-w-full truncate">{item.label}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
