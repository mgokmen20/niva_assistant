/** Mirrors the FastAPI recommendation and feedback DTOs. */

export interface DailyForecastDay {
  date: string
  temperature_max: number
  temperature_min: number
  precipitation_probability: number
  weather_code: number
}

export interface PackingItem {
  item_id: string
  category: string
  quantity: number
}

export interface TripOutlookDay {
  date: string
  temperature_max: number
  temperature_min: number
  precipitation_probability: number
  weather_code: number
  wind_speed: number
}

export interface TravelPlan {
  city_name: string
  start_date: string
  end_date: string
  summary: string
  items: PackingItem[]
  days: TripOutlookDay[]
}

export interface SavedPackingItem {
  id: string
  name: string
  category: string
  quantity: number
  checked: boolean
}

export interface SavedTrip {
  id: string
  destination_city: string
  start_date: string
  end_date: string
  summary_text: string
  packing_items: SavedPackingItem[]
  created_at: string
}

export interface DiurnalPeriod {
  period: 'morning' | 'afternoon' | 'evening' | string
  temperature: number
  weather_code: number
}

export interface Meteorology {
  air_temperature: number
  apparent_temperature: number
  wind_speed: number
  rain_probability: number
  uv_index: number
  diurnal?: DiurnalPeriod[]
}

export interface Garment {
  id: string
  label: string
  category: string
  removable?: boolean | null
}

export interface ClothingLayers {
  base_layer: Garment
  mid_layer: Garment | null
  outer_layer: Garment | null
  accessories: Garment[]
  risk_level: string
  utci_category: string
}

export interface VoiceAnswer {
  answer_text: string
  language: string
  audio_base64: string
}

export interface RecommendationResponse {
  recommendation_id: string | null
  effective_temperature: number
  meteorology: Meteorology
  clothing_layers: ClothingLayers
  voice_summary: string
  personal_offset?: number | null
}

export interface FeedbackResponse {
  previous_offset: number
  new_offset: number
  delta_applied: number
}

export type ThermalRating = 'TOO_COLD' | 'PERFECT' | 'TOO_WARM'

/** Apparel imagery audience stored on the wearer profile. */
export type Gender = 'neutral' | 'women' | 'men'

/** Account role used for workspace access. Unknown values stay a standard user. */
export type AccountRole = 'user' | 'partner' | 'admin'

export interface LocationMatch {
  id: number
  name: string
  latitude: number
  longitude: number
  admin1: string | null
  country: string | null
}

export interface ActiveLocation {
  name: string
  lat: number
  lon: number
}

export interface ReverseLocation {
  name: string
  region: string
  country: string
  display_name: string
}

export interface UserProfile {
  id: string
  email: string
  first_name: string
  last_name: string
  birth_date: string
  role: string
  gender: Gender
}

export type ThermalPreference = 'cold_sensitive' | 'balanced' | 'warm_sensitive'
export type EnvironmentRoutine = 'mostly_indoor' | 'mostly_outdoor'

export type PreferredLanguage = 'en' | 'de' | 'tr'

export interface WearerProfile extends UserProfile {
  phone_number: string | null
  thermal_preference: ThermalPreference
  environment_routine: EnvironmentRoutine
  baseline_offset: number
  active_offset: number
  preferred_language: PreferredLanguage
}

export interface TimelinePoint {
  day: string
  recommendations: number
  feedback: number
  recommendations_count?: number
  feedback_count?: number
}

export interface SentimentSlice {
  rating: string
  count: number
  percentage: number
}

export interface TemperatureLayerBand {
  bucket: string
  recommendation_count: number
  layers: GarmentStat[]
}

export interface GenderShare {
  gender: string
  count: number
  percentage: number
}

export interface AnalyticsOverview {
  total_registered_users: number
  active_wearers: number
  total_recommendations: number
  thermal_satisfaction_rate: number
  most_frequent_garment: string | null
  most_frequent_garment_category: string | null
  most_frequent_garment_count: number
  timeline: TimelinePoint[]
  sentiment_breakdown: SentimentSlice[]
  temperature_layer_breakdown: TemperatureLayerBand[]
  accessories_distribution: GarmentStat[]
  user_demographics_gender: GenderShare[]
}

export interface GarmentStat {
  garment: string
  category: string
  count: number
  percentage: number
}

export interface TemperatureBucket {
  city: string
  bucket: string
  recommendation_count: number
  garments: GarmentStat[]
}

export interface ClothingTrendBucket {
  city: string
  bucket: string
  gender: string
  recommendation_count: number
  garments: GarmentStat[]
}

/** Wearer segment accepted by the analytics filters. */
export type AnalyticsGender = 'all' | 'male' | 'female' | 'other'

export interface AdminUserRecord {
  id: string
  first_name: string
  last_name: string
  email: string
  phone_number: string | null
  role: string
  is_active: boolean
  baseline_offset: number
  last_login_at: string | null
  last_login_ip: string | null
  created_at: string
}

export interface AdminUserList {
  items: AdminUserRecord[]
  total: number
  page: number
  page_size: number
}

/** Fields an admin may change on PUT /admin/users/{id}. */
export interface AdminUserUpdate {
  role?: AccountRole
  is_active?: boolean
  phone_number?: string | null
}

/** Calendar bounds for an analytics query. Dates are YYYY-MM-DD. */
export interface AnalyticsQuery {
  days?: number
  city?: string
  startDate?: string
  endDate?: string
  gender?: AnalyticsGender
}

/** Interval whose recommendation history an admin may archive and remove. */
export interface PurgeInterval {
  beforeDate?: string
  startDate?: string
  endDate?: string
}

export interface PurgePreview {
  matching_count: number
  matching_recommendations: number
  matching_feedback: number
}

export interface PurgeResult {
  purged_count: number
  purged_recommendations: number
  purged_feedback: number
}
