import type { AccountRole } from '../types/api'

/** Map a stored role onto the three accounts the workspace understands. */
export function accountRole(value: string | null | undefined): AccountRole {
  if (value === 'admin' || value === 'partner') {
    return value
  }
  return 'user'
}

/** Partners and admins may open the management workspace. */
export function canOpenWorkspace(role: AccountRole): boolean {
  return role === 'admin' || role === 'partner'
}
