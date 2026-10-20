import { useContext, useMemo } from 'react'
import { LanguageContext } from './languageState'
import { translate, type Translator } from './translate'

export function useI18n() {
  const value = useContext(LanguageContext)
  if (value === null) {
    throw new Error('useI18n must be used inside LanguageProvider.')
  }
  return value
}

/** Active language plus a typed dotted-path translator. */
export function useTranslation() {
  const { language, messages } = useI18n()
  const t = useMemo<Translator>(() => {
    return ((path: string, ...args: unknown[]) => translate(messages, path, ...args)) as Translator
  }, [messages])
  return { t, language }
}
