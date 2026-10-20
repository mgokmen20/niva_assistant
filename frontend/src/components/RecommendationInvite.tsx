import { useEffect } from 'react'

/** Asks a guest to sign in before a clothing or voice request. */
export function RecommendationInvite({
  onClose,
  onSignIn,
  onRegister,
  title = 'Sign in to get your personalized thermal clothing recommendation',
  body = 'Weather stays available for everyone. Outfit suggestions and voice replies are saved to your account.',
  signInLabel = 'Login',
  registerLabel = 'Register',
  dismissLabel = 'Not now',
}: {
  onClose: () => void
  onSignIn: () => void
  onRegister: () => void
  title?: string
  body?: string
  signInLabel?: string
  registerLabel?: string
  dismissLabel?: string
}) {
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

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="recommendation-invite-title"
        className="w-full max-w-md rounded-3xl bg-white p-5 text-slate-950 shadow-2xl"
      >
        <h2 id="recommendation-invite-title" className="text-lg font-semibold">
          {title}
        </h2>
        <p className="mt-2 text-sm text-slate-600">{body}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onSignIn}
            className="min-h-12 flex-1 rounded-md border border-blue-600 bg-blue-600 px-4 text-sm font-semibold text-white shadow-sm transition duration-150 hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
          >
            {signInLabel}
          </button>
          <button
            type="button"
            onClick={onRegister}
            className="min-h-12 flex-1 rounded-md border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm transition duration-150 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
          >
            {registerLabel}
          </button>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="mt-3 min-h-12 w-full rounded-md px-4 text-sm font-semibold text-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
        >
          {dismissLabel}
        </button>
      </div>
    </div>
  )
}
