import { createContext } from 'react'
import type { AppLanguage, Dictionary } from './types'

export interface LanguageContextValue {
  language: AppLanguage
  messages: Dictionary
  setLanguage: (language: AppLanguage) => Promise<void>
}

export const LanguageContext = createContext<LanguageContextValue | null>(null)
