import type {
  DailyForecastDay,
  AdminUserList,
  AdminUserRecord,
  AdminUserUpdate,
  AnalyticsOverview,
  AnalyticsQuery,
  ClothingTrendBucket,
  EnvironmentRoutine,
  FeedbackResponse,
  GarmentStat,
  Gender,
  LocationMatch,
  Meteorology,
  PurgeInterval,
  PurgePreview,
  PurgeResult,
  PreferredLanguage,
  RecommendationResponse,
  ReverseLocation,
  SavedPackingItem,
  SavedTrip,
  TemperatureBucket,
  TravelPlan,
  ThermalPreference,
  UserProfile,
  VoiceAnswer,
  WardrobeItem,
  WardrobeItemInput,
  WearerProfile,
} from '../types/api'

const RECOMMENDATIONS_URL = '/api/v1/recommendations'
const TRAVEL_URL = '/api/v1/travel'
const VOICE_URL = '/api/v1/voice'
const LOCATIONS_URL = '/api/v1/locations'
const REVERSE_LOOKUP_TIMEOUT_MS = 5000
const CURRENT_USER_URL = '/api/v1/auth/me'
const PROFILE_URL = '/api/v1/profile'
const WARDROBE_URL = '/api/v1/wardrobe'
const ANALYTICS_URL = '/api/v1/analytics'
const ADMIN_USERS_URL = '/api/v1/admin/users'
const PURGE_URL = '/api/v1/admin/maintenance'
const CSV_FILENAME = 'niva-clothing-trends.csv'
const ARCHIVE_FILENAME = 'niva-log-archive.csv'

export const ACCESS_TOKEN_STORAGE_KEY = 'niva.accessToken'
export const ACCESS_TOKEN_EXPIRES_KEY = 'niva.accessTokenExpiresAt'
export const USER_PROFILE_STORAGE_KEY = 'niva.user'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface ValidationIssue {
  msg?: unknown
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string' && body.detail.trim() !== '') {
      return body.detail
    }
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((issue) => {
          const record = issue as ValidationIssue
          return typeof record.msg === 'string' ? record.msg : ''
        })
        .filter((message) => message !== '')
      if (messages.length > 0) {
        return messages.join(' ')
      }
    }
  } catch {
    // A non-JSON error body still becomes a status message below.
  }
  return `Request failed (${response.status}).`
}

export async function askAssistant(
  question: string,
  city: string,
  lang: string,
  token?: string | null,
  signal?: AbortSignal,
): Promise<VoiceAnswer> {
  const response = await fetch('/api/v1/assistant/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question, city, lang }),
    signal,
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as VoiceAnswer
}

export async function askNiva(
  question: string,
  latitude: number,
  longitude: number,
  cityName: string,
  token?: string | null,
  signal?: AbortSignal,
): Promise<VoiceAnswer> {
  const response = await fetch(`${VOICE_URL}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question,
      latitude,
      longitude,
      city_name: cityName,
    }),
    signal,
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as VoiceAnswer
}

export async function synthesizeSpeech(
  text: string,
  token: string,
  language: PreferredLanguage = 'en',
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await fetch(`${VOICE_URL}/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ text, language }),
    signal,
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return response.blob()
}

export async function fetchDailyForecast(lat: number, lon: number): Promise<DailyForecastDay[]> {
  const response = await fetch(withQuery('/api/v1/weather/forecast', { latitude: lat, longitude: lon }))
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const body = (await response.json()) as unknown
  if (!Array.isArray(body)) {
    throw new ApiError('The weekly forecast returned an unexpected response.', response.status)
  }
  return body.filter(isDailyForecastDay)
}

function isDailyForecastDay(value: unknown): value is DailyForecastDay {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const row = value as Partial<DailyForecastDay>
  return (
    typeof row.date === 'string' &&
    typeof row.temperature_max === 'number' &&
    typeof row.temperature_min === 'number' &&
    typeof row.precipitation_probability === 'number' &&
    typeof row.weather_code === 'number'
  )
}

export async function fetchTravelPlan(
  latitude: number,
  longitude: number,
  cityName: string,
  startDate: string,
  endDate: string,
  token: string,
  language: PreferredLanguage = 'en',
): Promise<TravelPlan> {
  const response = await fetch(`${TRAVEL_URL}/plan?lang=${encodeURIComponent(language)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      latitude,
      longitude,
      city_name: cityName,
      start_date: startDate,
      end_date: endDate,
    }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as TravelPlan
}

export async function fetchSavedTrips(token: string): Promise<SavedTrip[]> {
  const response = await fetch(`${TRAVEL_URL}/trips`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as SavedTrip[]
}

export async function saveTrip(
  body: {
    destination_city: string
    start_date: string
    end_date: string
    summary_text: string
    packing_items: SavedPackingItem[]
  },
  token: string,
): Promise<SavedTrip> {
  const response = await fetch(`${TRAVEL_URL}/trips`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as SavedTrip
}

export async function updateTripChecks(
  tripId: string,
  items: { id: string; checked: boolean }[],
  token: string,
): Promise<SavedTrip> {
  const response = await fetch(`${TRAVEL_URL}/trips/${tripId}/items`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ items }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as SavedTrip
}

export async function deleteSavedTrip(tripId: string, token: string): Promise<void> {
  const response = await fetch(`${TRAVEL_URL}/trips/${tripId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
}

export async function fetchCurrentWeather(lat: number, lon: number): Promise<Meteorology> {
  const response = await fetch(withQuery('/api/v1/weather/current', { latitude: lat, longitude: lon }))
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as Meteorology
}

export async function fetchCurrentRecommendation(
  lat: number,
  lon: number,
  cityName: string,
  firstName?: string | null,
  token?: string | null,
  language: PreferredLanguage = 'en',
): Promise<RecommendationResponse> {
  const givenName = firstName?.trim() ?? ''
  const response = await fetch(`${RECOMMENDATIONS_URL}/current?lang=${encodeURIComponent(language)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      latitude: lat,
      longitude: lon,
      city_name: cityName,
      mode: 'auto',
      ...(givenName !== '' ? { first_name: givenName } : {}),
    }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as RecommendationResponse
}

function isLocationMatch(value: unknown): value is LocationMatch {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const row = value as Partial<LocationMatch>
  return (
    typeof row.id === 'number' &&
    typeof row.name === 'string' &&
    typeof row.latitude === 'number' &&
    typeof row.longitude === 'number'
  )
}

export async function searchLocations(query: string, signal?: AbortSignal): Promise<LocationMatch[]> {
  const params = new URLSearchParams({ query })
  const response = await fetch(`${LOCATIONS_URL}/search?${params.toString()}`, { signal })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const body = (await response.json()) as unknown
  if (!Array.isArray(body)) {
    throw new ApiError('Location search returned an unexpected response.', response.status)
  }
  return body.filter(isLocationMatch).map((place) => ({
    id: place.id,
    name: place.name,
    latitude: place.latitude,
    longitude: place.longitude,
    admin1: typeof place.admin1 === 'string' ? place.admin1 : null,
    country: typeof place.country === 'string' ? place.country : null,
  }))
}

function textField(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export async function reverseLocation(lat: number, lon: number): Promise<ReverseLocation> {
  const params = new URLSearchParams({
    lat: String(lat),
    lon: String(lon),
  })
  const response = await fetch(`${LOCATIONS_URL}/reverse?${params.toString()}`, {
    signal: AbortSignal.timeout(REVERSE_LOOKUP_TIMEOUT_MS),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const body = (await response.json()) as Partial<ReverseLocation>
  const name = textField(body.name)
  if (name === '') {
    throw new ApiError('Location lookup did not return a place name.', response.status)
  }
  return {
    name,
    region: textField(body.region),
    country: textField(body.country),
    display_name: textField(body.display_name),
  }
}

export async function submitFeedback(
  recommendationId: string,
  rating: string,
  followed: boolean,
  token: string,
): Promise<FeedbackResponse> {
  const response = await fetch(`${RECOMMENDATIONS_URL}/feedback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      recommendation_id: recommendationId,
      rating,
      followed_recommendation: followed,
    }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as FeedbackResponse
}

function isGender(value: unknown): value is Gender {
  return value === 'men' || value === 'women' || value === 'neutral'
}

interface TokenPayload {
  access_token?: unknown
}

export interface RegisterAccountInput {
  firstName: string
  lastName: string
  email: string
  password: string
  birthDate: string
  gender: Gender
  phoneNumber?: string
  thermalPreference: ThermalPreference
  environmentRoutine: EnvironmentRoutine
}

const LOGIN_URL = '/api/v1/auth/login'
const REGISTER_URL = '/api/v1/auth/register'

export async function loginAccount(email: string, password: string, rememberMe = false): Promise<string> {
  const form = new URLSearchParams()
  form.set('username', email)
  form.set('password', password)
  form.set('remember_me', rememberMe ? 'true' : 'false')
  const response = await fetch(LOGIN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const payload = (await response.json()) as TokenPayload
  if (typeof payload.access_token !== 'string' || payload.access_token.trim() === '') {
    throw new ApiError('Sign in did not return an access token.', response.status)
  }
  return payload.access_token
}

export async function registerAccount(input: RegisterAccountInput): Promise<void> {
  const response = await fetch(REGISTER_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: input.email,
      password: input.password,
      first_name: input.firstName,
      last_name: input.lastName,
      birth_date: input.birthDate,
      gender: input.gender,
      phone_number: input.phoneNumber ?? null,
      thermal_preference: input.thermalPreference,
      environment_routine: input.environmentRoutine,
    }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
}

export async function fetchCurrentUser(token: string): Promise<UserProfile> {
  const response = await fetch(CURRENT_USER_URL, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const body = (await response.json()) as UserProfile
  return {
    ...body,
    gender: isGender(body.gender) ? body.gender : 'neutral',
  }
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

/** Prefer the tab session, then the remembered token. */
function readAccessToken(): string {
  const sessionToken = window.sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  if (sessionToken !== null && sessionToken.trim() !== '') {
    return sessionToken
  }
  const localToken = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  const expiresAt = window.localStorage.getItem(ACCESS_TOKEN_EXPIRES_KEY)
  const expires = expiresAt === null ? Number.NaN : Date.parse(expiresAt)
  if (localToken !== null && localToken.trim() !== '' && !Number.isNaN(expires) && expires > Date.now()) {
    return localToken
  }
  throw new ApiError('Authentication is required.', 401)
}

function withQuery(path: string, params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') {
      continue
    }
    search.set(key, String(value))
  }
  const query = search.toString()
  return query === '' ? path : `${path}?${query}`
}

function analyticsSearch(path: string, query: AnalyticsQuery): string {
  const hasRange = query.startDate !== undefined && query.startDate !== '' && query.endDate !== undefined && query.endDate !== ''
  const shared = {
    city: query.city,
    gender: query.gender !== undefined && query.gender !== 'all' ? query.gender : undefined,
  }
  return withQuery(
    path,
    hasRange
      ? { start_date: query.startDate, end_date: query.endDate, ...shared }
      : { days: query.days, ...shared },
  )
}

function purgeSearch(interval: PurgeInterval): Record<string, string | undefined> {
  return {
    before_date: interval.beforeDate,
    start_date: interval.startDate,
    end_date: interval.endDate,
  }
}

function saveDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export async function fetchAnalyticsOverview(query: AnalyticsQuery): Promise<AnalyticsOverview> {
  const response = await fetch(analyticsSearch(`${ANALYTICS_URL}/overview`, query), {
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as AnalyticsOverview
}

export async function fetchGarmentDistribution(query: AnalyticsQuery & { city: string }): Promise<GarmentStat[]> {
  const response = await fetch(analyticsSearch(`${ANALYTICS_URL}/clothing-distribution`, query), {
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as GarmentStat[]
}

export async function fetchAnalyticsTrends(query: AnalyticsQuery = {}): Promise<ClothingTrendBucket[]> {
  const response = await fetch(analyticsSearch(`${ANALYTICS_URL}/trends`, query), {
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as ClothingTrendBucket[]
}

export async function fetchTemperatureCorrelations(query: AnalyticsQuery = {}): Promise<TemperatureBucket[]> {
  const response = await fetch(analyticsSearch(`${ANALYTICS_URL}/temperature-correlations`, query), {
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as TemperatureBucket[]
}

export async function downloadAnalyticsCsv(query: AnalyticsQuery = {}): Promise<void> {
  const response = await fetch(analyticsSearch(`${ANALYTICS_URL}/export-csv`, query), {
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  saveDownload(await response.blob(), CSV_FILENAME)
}

export async function previewPurge(interval: PurgeInterval): Promise<PurgePreview> {
  const response = await fetch(withQuery(`${PURGE_URL}/purge-preview`, purgeSearch(interval)), {
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as PurgePreview
}

export async function downloadPurgeArchive(interval: PurgeInterval): Promise<void> {
  const response = await fetch(withQuery(`${PURGE_URL}/purge-archive`, purgeSearch(interval)), {
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  saveDownload(await response.blob(), ARCHIVE_FILENAME)
}

export async function purgeLogs(interval: PurgeInterval, exportFirst: boolean): Promise<PurgeResult> {
  const response = await fetch(`${PURGE_URL}/purge-logs`, {
    method: 'POST',
    headers: { ...authHeaders(readAccessToken()), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      before_date: interval.beforeDate ?? null,
      start_date: interval.startDate ?? null,
      end_date: interval.endDate ?? null,
      export_first: exportFirst,
    }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as PurgeResult
}

export async function fetchAdminUsers(page?: number, search?: string, role?: string): Promise<AdminUserList> {
  const response = await fetch(withQuery(ADMIN_USERS_URL, { page, search, role }), {
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as AdminUserList
}

export async function updateAdminUser(userId: string, data: AdminUserUpdate): Promise<AdminUserRecord> {
  const response = await fetch(`${ADMIN_USERS_URL}/${userId}`, {
    method: 'PUT',
    headers: { ...authHeaders(readAccessToken()), 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return (await response.json()) as AdminUserRecord
}

export async function resetUserPassword(userId: string, newPassword: string): Promise<void> {
  const response = await fetch(`${ADMIN_USERS_URL}/${userId}/reset-password`, {
    method: 'POST',
    headers: { ...authHeaders(readAccessToken()), 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password: newPassword }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
}

export async function deactivateUser(userId: string): Promise<void> {
  const response = await fetch(`${ADMIN_USERS_URL}/${userId}`, {
    method: 'DELETE',
    headers: authHeaders(readAccessToken()),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
}

export async function fetchProfile(token: string): Promise<WearerProfile> {
  const response = await fetch(`${PROFILE_URL}/me`, { headers: authHeaders(token) })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return asWearerProfile((await response.json()) as WearerProfile)
}

function asPreferredLanguage(value: string | undefined): WearerProfile['preferred_language'] {
  if (value === 'de' || value === 'tr' || value === 'en') {
    return value
  }
  return 'en'
}

function asWearerProfile(body: WearerProfile): WearerProfile {
  return {
    ...body,
    gender: isGender(body.gender) ? body.gender : 'neutral',
    phone_number: body.phone_number ?? null,
    preferred_language: asPreferredLanguage(body.preferred_language),
  }
}

export async function updateProfile(
  token: string,
  input: {
    firstName: string
    lastName: string
    email: string
    phoneNumber: string
    thermalPreference: ThermalPreference
    environmentRoutine: EnvironmentRoutine
    gender?: Gender
    birthDate?: string
    preferredLanguage?: WearerProfile['preferred_language']
  },
): Promise<WearerProfile> {
  const response = await fetch(`${PROFILE_URL}/me`, {
    method: 'PUT',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      first_name: input.firstName,
      last_name: input.lastName,
      email: input.email,
      phone_number: input.phoneNumber,
      thermal_preference: input.thermalPreference,
      environment_routine: input.environmentRoutine,
      ...(input.gender ? { gender: input.gender } : {}),
      ...(input.birthDate ? { birth_date: input.birthDate } : {}),
      ...(input.preferredLanguage ? { preferred_language: input.preferredLanguage } : {}),
    }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return asWearerProfile((await response.json()) as WearerProfile)
}

export async function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const response = await fetch(`${PROFILE_URL}/change-password`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
}

export async function resetCalibration(token: string): Promise<WearerProfile> {
  const response = await fetch(`${PROFILE_URL}/reset-calibration`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return asWearerProfile((await response.json()) as WearerProfile)
}

function isWardrobeItem(value: unknown): value is WardrobeItem {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const row = value as Partial<WardrobeItem>
  return (
    typeof row.id === 'string' &&
    typeof row.user_id === 'string' &&
    typeof row.category === 'string' &&
    typeof row.thickness === 'string' &&
    typeof row.color_name === 'string' &&
    typeof row.style === 'string' &&
    typeof row.is_waterproof === 'boolean' &&
    typeof row.is_active === 'boolean' &&
    typeof row.item_name === 'string'
  )
}

export async function fetchWardrobe(token: string): Promise<WardrobeItem[]> {
  const response = await fetch(`${WARDROBE_URL}/`, { headers: authHeaders(token) })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const body = (await response.json()) as unknown
  if (!Array.isArray(body) || !body.every(isWardrobeItem)) {
    throw new ApiError('Wardrobe response was not a list of clothing items.', response.status)
  }
  return body
}

export async function createWardrobeItem(token: string, input: WardrobeItemInput): Promise<WardrobeItem> {
  const response = await fetch(`${WARDROBE_URL}/`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const body = (await response.json()) as unknown
  if (!isWardrobeItem(body)) {
    throw new ApiError('Wardrobe response was not a clothing item.', response.status)
  }
  return body
}

export async function updateWardrobeItem(
  token: string,
  itemId: string,
  input: WardrobeItemInput,
): Promise<WardrobeItem> {
  const response = await fetch(`${WARDROBE_URL}/${itemId}`, {
    method: 'PUT',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const body = (await response.json()) as unknown
  if (!isWardrobeItem(body)) {
    throw new ApiError('Wardrobe response was not a clothing item.', response.status)
  }
  return body
}

export async function toggleWardrobeItem(token: string, itemId: string): Promise<WardrobeItem> {
  const response = await fetch(`${WARDROBE_URL}/${itemId}/toggle-active`, {
    method: 'PATCH',
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  const body = (await response.json()) as unknown
  if (!isWardrobeItem(body)) {
    throw new ApiError('Wardrobe response was not a clothing item.', response.status)
  }
  return body
}

export async function deleteWardrobeItem(token: string, itemId: string): Promise<void> {
  const response = await fetch(`${WARDROBE_URL}/${itemId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
}
