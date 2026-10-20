import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useAuth } from './AuthContext'
import {
  detectGuestLanguage,
  documentLanguage,
  isAppLanguage,
  messagesFor,
  writeStoredLanguage,
  type AppLanguage,
} from '../i18n'
import { LanguageContext } from '../i18n/languageState'
import { fetchProfile, updateProfile } from '../services/api'

export function LanguageProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  const [language, setLanguageState] = useState<AppLanguage>(detectGuestLanguage)

  useEffect(() => {
    document.documentElement.lang = documentLanguage(language)
  }, [language])

  useEffect(() => {
    if (token === null) {
      return
    }
    let active = true
    void fetchProfile(token)
      .then((profile) => {
        if (!active) {
          return
        }
        const preferred = isAppLanguage(profile.preferred_language) ? profile.preferred_language : 'en'
        setLanguageState(preferred)
        writeStoredLanguage(preferred)
      })
      .catch(() => {
        if (active) {
          setLanguageState(detectGuestLanguage())
        }
      })
    return () => {
      active = false
    }
  }, [token])

  const setLanguage = useCallback(
    async (next: AppLanguage) => {
      const previous = language
      setLanguageState(next)
      writeStoredLanguage(next)
      if (token === null) {
        return
      }
      try {
        const current = await fetchProfile(token)
        await updateProfile(token, {
          firstName: current.first_name,
          lastName: current.last_name,
          email: current.email,
          phoneNumber: current.phone_number ?? '',
          thermalPreference: current.thermal_preference,
          environmentRoutine: current.environment_routine,
          gender: current.gender,
          birthDate: current.birth_date,
          preferredLanguage: next,
        })
      } catch (error) {
        setLanguageState(previous)
        writeStoredLanguage(previous)
        throw error
      }
    },
    [language, token],
  )

  const value = useMemo(
    () => ({
      language,
      messages: messagesFor(language),
      setLanguage,
    }),
    [language, setLanguage],
  )

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}
