/** Light SaaS controls shared by the management workspace. */

export const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700'

export const pillActive = `min-h-12 rounded-full border border-blue-600 bg-blue-600 px-4 text-sm font-semibold text-white shadow-sm transition duration-150 hover:bg-blue-700 ${focusRing}`

export const pillIdle = `min-h-12 rounded-full border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm transition duration-150 hover:bg-slate-50 ${focusRing}`

export const primaryButton = `inline-flex min-h-12 items-center justify-center rounded-md border border-blue-600 bg-blue-600 px-4 text-sm font-semibold text-white shadow-sm transition duration-150 hover:bg-blue-700 disabled:opacity-60 ${focusRing}`

export const quietButton = `inline-flex min-h-12 items-center justify-center rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm transition duration-150 hover:bg-slate-50 disabled:opacity-50 ${focusRing}`

export const dangerButton = `inline-flex min-h-12 items-center justify-center rounded-md border border-rose-600 bg-rose-600 px-4 text-sm font-semibold text-white shadow-sm transition duration-150 hover:bg-rose-700 disabled:opacity-60 ${focusRing}`

export const fieldClass = `min-h-12 rounded-md border border-slate-200 bg-white px-3 font-semibold text-slate-800 shadow-sm ${focusRing}`
