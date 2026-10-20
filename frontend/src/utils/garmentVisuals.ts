/** Apparel photos and accessory illustrations. Accessories use unique drawings, not model photos. */

import type { Gender } from '../types/api'

export type GarmentBadge = 'Base' | 'Mid' | 'Outer' | 'Accessory'

export interface GarmentVisual {
  imageUrl: string
  accentClass: string
  washClass: string
  badge: GarmentBadge
  protectionTags: readonly string[]
}

const IMAGE_SIZE = 'auto=format&fit=crop&w=800&h=1000&q=80'

function apparelPhoto(photoId: string): string {
  return `https://images.unsplash.com/photo-${photoId}?${IMAGE_SIZE}`
}

/** Clean apparel photo used when a garment id is not in the catalog. */
export const FALLBACK_GARMENT_IMAGE = apparelPhoto('1523381210434-271e8be1f52b')

interface Tone {
  accentClass: string
  washClass: string
  badge: GarmentBadge
}

interface CatalogEntry {
  tone: Tone
  photos: Record<Gender, string>
  protectionTags: readonly string[]
}

const BASE: Tone = {
  accentClass: 'bg-sky-100 text-sky-950',
  washClass: 'bg-sky-50',
  badge: 'Base',
}

const MID: Tone = {
  accentClass: 'bg-violet-100 text-violet-950',
  washClass: 'bg-violet-50',
  badge: 'Mid',
}

const OUTER: Tone = {
  accentClass: 'bg-indigo-100 text-indigo-950',
  washClass: 'bg-indigo-50',
  badge: 'Outer',
}

const ACCESSORY: Tone = {
  accentClass: 'bg-amber-100 text-amber-950',
  washClass: 'bg-amber-50',
  badge: 'Accessory',
}

function photos(neutral: string, women: string, men: string): Record<Gender, string> {
  return {
    neutral: apparelPhoto(neutral),
    women: apparelPhoto(women),
    men: apparelPhoto(men),
  }
}

/** One illustration for every gender so an accessory never borrows a clothing model photo. */
function sameArt(imageUrl: string): Record<Gender, string> {
  return { neutral: imageUrl, women: imageUrl, men: imageUrl }
}

function accessoryArt(background: string, drawing: string): string {
  const markup =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 200">` +
    `<rect width="160" height="200" rx="28" fill="${background}"/>${drawing}</svg>`
  return `data:image/svg+xml,${encodeURIComponent(markup)}`
}

const SUNGLASSES_ART = accessoryArt(
  '#fff7ed',
  '<g fill="none" stroke="#0f172a" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M28 92h18c10 0 16 8 22 8s12-8 22-8h18" stroke-width="5"/>' +
    '<path d="M22 96c2 18 12 30 26 30s24-12 26-30c-8 6-16 8-26 8s-18-2-26-8z" fill="#0f172a" stroke="none"/>' +
    '<path d="M86 96c2 18 12 30 26 30s24-12 26-30c-8 6-16 8-26 8s-18-2-26-8z" fill="#0f172a" stroke="none"/>' +
    '<path d="M34 104c6-8 14-8 18 0" stroke="#cbd5e1" stroke-width="3"/>' +
    '<path d="M98 104c6-8 14-8 18 0" stroke="#cbd5e1" stroke-width="3"/>' +
    '<path d="M18 94H10M150 94h-8" stroke-width="4"/>' +
    '</g>',
)

const UMBRELLA_ART = accessoryArt(
  '#eff6ff',
  '<path d="M80 42c-34 10-50 36-50 54h100c0-18-16-44-50-54z" fill="#0284c7"/>' +
    '<path d="M46 96c8-14 16-14 22 0M80 96c6-16 14-16 20 0M114 96c-6-14-14-14-20 0" fill="none" stroke="#e0f2fe" stroke-width="3"/>' +
    '<path d="M80 42v112" stroke="#0f172a" stroke-width="4" stroke-linecap="round"/>' +
    '<path d="M80 154c14 0 18 12 8 16" fill="none" stroke="#0f172a" stroke-width="4" stroke-linecap="round"/>',
)

const WARM_HAT_ART = accessoryArt(
  '#f5f3ff',
  '<path d="M42 118c0-42 14-64 38-64s38 22 38 64v8H42z" fill="#6d28d9"/>' +
    '<rect x="38" y="112" width="84" height="26" rx="8" fill="#4c1d95"/>' +
    '<circle cx="80" cy="58" r="7" fill="#ddd6fe"/>',
)

const GLOVES_ART = accessoryArt(
  '#fff7ed',
  '<path d="M48 78c0-10 8-16 14-12 4-12 16-14 20-2 6-10 18-8 20 4 8-4 16 2 14 12l-6 46c-2 10-10 16-20 16H62c-12 0-20-8-20-18z" fill="#ea580c"/>' +
    '<path d="M58 70v28M72 62v36M88 66v32" stroke="#fed7aa" stroke-width="3" stroke-linecap="round"/>' +
    '<path d="M96 86c8-2 16 6 14 16" fill="none" stroke="#9a3412" stroke-width="3" stroke-linecap="round"/>',
)

const SCARF_ART = accessoryArt(
  '#fdf2f8',
  '<path d="M46 58h68c8 0 14 6 14 14v18H46c-8 0-14-6-14-14V72c0-8 6-14 14-14z" fill="#db2777"/>' +
    '<path d="M48 90h78v18c0 16-14 28-32 28H70c-14 0-22-8-22-20z" fill="#be185d"/>' +
    '<path d="M58 108h48M58 120h36" stroke="#fbcfe8" stroke-width="3" stroke-linecap="round"/>',
)

const SUN_HAT_ART = accessoryArt(
  '#fefce8',
  '<ellipse cx="80" cy="118" rx="58" ry="16" fill="#eab308"/>' +
    '<path d="M52 112c2-32 14-52 28-52s26 20 28 52z" fill="#facc15"/>' +
    '<path d="M56 96h48" stroke="#ca8a04" stroke-width="4" stroke-linecap="round"/>',
)

function entry(tone: Tone, images: Record<Gender, string>, protectionTags: readonly string[]): CatalogEntry {
  return { tone, photos: images, protectionTags }
}

const CATALOG: Record<string, CatalogEntry> = {
  light_t_shirt: entry(BASE, photos('1523381210434-271e8be1f52b', '1515886657613-9f3515b0c78f', '1521572163474-6864f9cf17ab'), ['Breathable']),
  t_shirt: entry(BASE, photos('1523381210434-271e8be1f52b', '1515886657613-9f3515b0c78f', '1521572163474-6864f9cf17ab'), ['Breathable']),
  long_sleeve_base: entry(
    { ...BASE, accentClass: 'bg-cyan-100 text-cyan-950', washClass: 'bg-cyan-50' },
    photos('1596755094514-f87e34085b2c', '1515886657613-9f3515b0c78f', '1602810318383-e386cc2a3ccf'),
    ['Light warmth'],
  ),
  thermal_base_layer: entry(
    { ...BASE, accentClass: 'bg-slate-200 text-slate-950', washClass: 'bg-slate-100' },
    photos('1523381210434-271e8be1f52b', '1525507119028-ed4c629a60a3', '1603252109303-2751441dd157'),
    ['Warmth'],
  ),
  light_overshirt: entry(MID, photos('1617137968427-85924c800a22', '1487222477894-8943e31ef7b2', '1617127365659-c47fa864d8bc'), ['Layering']),
  zip_hoodie: entry(
    { ...MID, accentClass: 'bg-fuchsia-100 text-fuchsia-950', washClass: 'bg-fuchsia-50' },
    photos('1556821840-3a63f95609a7', '1578587018452-892bacefd3f2', '1516826957135-700dedea698c'),
    ['Warmth'],
  ),
  cardigan: entry(MID, photos('1434389677669-e08b4cac3105', '1469334031218-e382a71b716b', '1603252109303-2751441dd157'), ['Layering']),
  wool_sweater: entry(MID, photos('1434389677669-e08b4cac3105', '1469334031218-e382a71b716b', '1516826957135-700dedea698c'), ['Warmth']),
  fleece_mid_layer: entry(
    { ...MID, accentClass: 'bg-purple-100 text-purple-950', washClass: 'bg-purple-50' },
    photos('1578587018452-892bacefd3f2', '1434389677669-e08b4cac3105', '1556821840-3a63f95609a7'),
    ['Warmth'],
  ),
  insulated_mid_layer: entry(MID, photos('1603252109303-2751441dd157', '1509631179647-0177331693ae', '1516826957135-700dedea698c'), ['Insulation']),
  wind_shell: entry(OUTER, photos('1591047139829-d91aecb6caea', '1581044777550-4cfa60707c03', '1551028719-00167b16eac5'), ['Wind']),
  light_jacket: entry(
    { ...OUTER, accentClass: 'bg-blue-100 text-blue-950', washClass: 'bg-blue-50' },
    photos('1591047139829-d91aecb6caea', '1490481651871-ab68de25d43d', '1552374196-1ab2a1c593e8'),
    ['Light warmth'],
  ),
  waterproof_shell: entry(OUTER, photos('1548126032-079a0fb0099d', '1490481651871-ab68de25d43d', '1551028719-00167b16eac5'), ['Rain', 'Wind']),
  rain_jacket: entry(OUTER, photos('1548126032-079a0fb0099d', '1581044777550-4cfa60707c03', '1552374196-1ab2a1c593e8'), ['Rain', 'Wind']),
  winter_coat: entry(
    { ...OUTER, accentClass: 'bg-slate-200 text-slate-950', washClass: 'bg-slate-100' },
    photos('1539533018447-63fcce2678e3', '1581044777550-4cfa60707c03', '1490114538077-0a7f8cb49891'),
    ['Warmth', 'Wind'],
  ),
  umbrella: entry(ACCESSORY, sameArt(UMBRELLA_ART), ['Rain']),
  sunglasses: entry(ACCESSORY, sameArt(SUNGLASSES_ART), ['UV']),
  warm_hat: entry(ACCESSORY, sameArt(WARM_HAT_ART), ['Warmth']),
  beanie: entry(ACCESSORY, sameArt(WARM_HAT_ART), ['Warmth']),
  gloves: entry(
    { ...ACCESSORY, accentClass: 'bg-orange-100 text-orange-950', washClass: 'bg-orange-50' },
    sameArt(GLOVES_ART),
    ['Warmth'],
  ),
  scarf: entry(ACCESSORY, sameArt(SCARF_ART), ['Warmth']),
  sun_hat: entry(
    { ...ACCESSORY, accentClass: 'bg-yellow-100 text-yellow-950', washClass: 'bg-yellow-50' },
    sameArt(SUN_HAT_ART),
    ['UV'],
  ),
}

const BADGE_BY_CATEGORY: Record<string, GarmentBadge> = {
  BASE: 'Base',
  MID: 'Mid',
  OUTER: 'Outer',
  ACCESSORY: 'Accessory',
}

function fallbackVisual(category: string): GarmentVisual {
  const badge = BADGE_BY_CATEGORY[category.trim().toUpperCase()] ?? 'Accessory'
  const tone = badge === 'Base' ? BASE : badge === 'Mid' ? MID : badge === 'Outer' ? OUTER : ACCESSORY
  return {
    ...tone,
    badge,
    imageUrl: FALLBACK_GARMENT_IMAGE,
    protectionTags: ['Everyday'],
  }
}

export function getGarmentVisual(
  garmentId: string,
  gender: Gender = 'neutral',
  category = '',
): GarmentVisual {
  const match = CATALOG[garmentId]
  if (match === undefined) {
    return fallbackVisual(category)
  }
  return {
    ...match.tone,
    imageUrl: match.photos[gender],
    protectionTags: match.protectionTags,
  }
}
