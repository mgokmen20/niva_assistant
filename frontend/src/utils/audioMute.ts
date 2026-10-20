export const AUDIO_MUTED_STORAGE_KEY = 'niva_audio_muted'

export function readAudioMuted(): boolean {
  try {
    return window.localStorage.getItem(AUDIO_MUTED_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

export function writeAudioMuted(muted: boolean): void {
  window.localStorage.setItem(AUDIO_MUTED_STORAGE_KEY, muted ? 'true' : 'false')
}
