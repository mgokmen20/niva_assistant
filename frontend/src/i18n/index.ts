import { german } from './de'
import { english } from './en'
import { translate } from './translate'
import { turkish } from './tr'
import { APP_LANGUAGES, type AppLanguage, type Dictionary } from './types'

export const LANGUAGE_STORAGE_KEY = 'niva_lang'

const DICTIONARIES: Record<AppLanguage, Dictionary> = {
  en: english,
  de: german,
  tr: turkish,
}

const DOCUMENT_LANG: Record<AppLanguage, string> = {
  en: 'en',
  de: 'de-CH',
  tr: 'tr',
}

export function isAppLanguage(value: unknown): value is AppLanguage {
  return typeof value === 'string' && APP_LANGUAGES.includes(value as AppLanguage)
}

export function messagesFor(language: AppLanguage): Dictionary {
  return DICTIONARIES[language]
}

export function documentLanguage(language: AppLanguage): string {
  return DOCUMENT_LANG[language]
}

export function languageFromTag(tag: string): AppLanguage {
  const base = tag.toLowerCase().split('-')[0]
  if (base === 'de') {
    return 'de'
  }
  if (base === 'tr') {
    return 'tr'
  }
  return 'en'
}

export function readStoredLanguage(): AppLanguage | null {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
    return isAppLanguage(stored) ? stored : null
  } catch {
    return null
  }
}

export function writeStoredLanguage(language: AppLanguage): void {
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language)
}

/** Guest order: saved choice, then the browser language, then English. */
export function detectGuestLanguage(): AppLanguage {
  const stored = readStoredLanguage()
  if (stored !== null) {
    return stored
  }
  if (typeof navigator === 'undefined') {
    return 'en'
  }
  return languageFromTag(navigator.language || 'en')
}

export function garmentLabel(language: AppLanguage, garmentId: string, fallback: string): string {
  return DICTIONARIES[language].garments[garmentId] ?? fallback
}

const CATEGORY_PATH = {
  base: 'workspace.retail.base',
  mid: 'workspace.retail.mid',
  outer: 'workspace.retail.outer',
  accessory: 'workspace.retail.accessory',
} as const

const BAND_PATH = {
  '<5°C': 'workspace.retail.below5',
  '5-10°C': 'workspace.retail.cool',
  '11-15°C': 'workspace.retail.mild',
  '>15°C': 'workspace.retail.warm',
} as const

/** Localized clothing category for a stored layer id such as base, mid, or outer. */
export function categoryLabel(language: AppLanguage, category: string): string {
  const path = CATEGORY_PATH[category as keyof typeof CATEGORY_PATH]
  return path === undefined ? category : translate(messagesFor(language), path)
}

/** Localized temperature-band caption for a stored analytics bucket. */
export function bandLabel(language: AppLanguage, bucket: string): string {
  const path = BAND_PATH[bucket as keyof typeof BAND_PATH]
  return path === undefined ? bucket : translate(messagesFor(language), path)
}

export type { AppLanguage, Dictionary }
