import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/useI18n'
import { garmentLabel } from '../i18n'
import type { ClothingLayers, Garment, Gender } from '../types/api'
import { FALLBACK_GARMENT_IMAGE, getGarmentVisual, type GarmentBadge } from '../utils/garmentVisuals'

interface ClothingLayersViewProps {
  layers: ClothingLayers
  isSeniorMode: boolean
}

/** Spoken UTCI bands, shown as the outfit's achieved thermal state. */
const THERMAL_STATUS_LABELS: Record<string, string> = {
  COMFORT: 'Thermal Comfort',
  SLIGHT_COLD: 'Slight Cold',
  MODERATE_COLD: 'Moderate Cold',
  EXTREME_COLD: 'Extreme Cold',
  MODERATE_HEAT: 'Moderate Heat',
  EXTREME_HEAT: 'Extreme Heat',
}

function thermalStatusLabel(category: string): string {
  const key = category.trim().toUpperCase()
  const known = THERMAL_STATUS_LABELS[key]
  if (known !== undefined) {
    return known
  }
  return key
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(' ')
}

interface LayerCardProps {
  garment: Garment
  gender: Gender
  isSeniorMode: boolean
}

function LayerCard({ garment, gender, isSeniorMode }: LayerCardProps) {
  const { language, messages } = useI18n()
  const visual = getGarmentVisual(garment.id, gender, garment.category)
  const badgeLabel: Record<GarmentBadge, string> = {
    Base: messages.layers.base,
    Mid: messages.layers.mid,
    Outer: messages.layers.outer,
    Accessory: messages.layers.accessories,
  }
  const [imageUrl, setImageUrl] = useState(visual.imageUrl)
  const tags = garment.removable ? [...visual.protectionTags, 'Removable'] : visual.protectionTags

  const isAccessory = visual.badge === 'Accessory'
  return (
    <article className="flex h-full items-center gap-3 rounded-xl bg-white p-3 shadow-sm ring-1 ring-slate-200/80">
      <div className={`relative h-[132px] w-[108px] shrink-0 overflow-hidden rounded-xl ${visual.washClass}`}>
        <img
          src={imageUrl}
          alt={garmentLabel(language, garment.id, garment.label)}
          className={`h-full w-full ${isAccessory ? 'object-contain p-1' : 'object-cover'}`}
          onError={() => {
            if (imageUrl !== FALLBACK_GARMENT_IMAGE) {
              setImageUrl(FALLBACK_GARMENT_IMAGE)
            }
          }}
        />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span className={`outfit-chip w-fit rounded-full px-2.5 py-1 text-xs font-semibold ${visual.accentClass}`}>
          {badgeLabel[visual.badge]}
        </span>
        <h3 className={`outfit-label text-slate-950 ${isSeniorMode ? 'text-xl font-bold' : 'text-base font-semibold'}`}>
          {garmentLabel(language, garment.id, garment.label)}
        </h3>
        <ul className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <li key={tag} className="outfit-chip rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
              {tag}
            </li>
          ))}
        </ul>
      </div>
    </article>
  )
}

function EmptyLayer({ title, status }: { title: string; status: string }) {
  return (
    <article className="flex h-full min-h-[132px] items-center gap-3 rounded-xl bg-white/80 p-3 ring-1 ring-slate-200/70">
      <span className="outfit-chip rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">{title}</span>
      <p className="outfit-label text-slate-600">{status}</p>
    </article>
  )
}

export function ClothingLayersView({ layers, isSeniorMode }: ClothingLayersViewProps) {
  const { gender } = useAuth()
  const { messages } = useI18n()
  const thermalStatus = thermalStatusLabel(layers.utci_category)
  return (
    <section aria-label="Clothing layers" className="space-y-4 rounded-3xl bg-white/70 p-4 ring-1 ring-slate-200/70 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold text-slate-950">{messages.layers.todaysOutfit}</h2>
        <span className="thermal-status cursor-default select-none rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
          {thermalStatus}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <LayerCard
          key={`${layers.base_layer.id}-${gender}`}
          garment={layers.base_layer}
          gender={gender}
          isSeniorMode={isSeniorMode}
        />
        {layers.mid_layer ? (
          <LayerCard
            key={`${layers.mid_layer.id}-${gender}`}
            garment={layers.mid_layer}
            gender={gender}
            isSeniorMode={isSeniorMode}
          />
        ) : (
          <EmptyLayer title={messages.layers.mid} status={messages.layers.notNeeded} />
        )}
        {layers.outer_layer ? (
          <LayerCard
            key={`${layers.outer_layer.id}-${gender}`}
            garment={layers.outer_layer}
            gender={gender}
            isSeniorMode={isSeniorMode}
          />
        ) : (
          <EmptyLayer title={messages.layers.outer} status={messages.layers.notNeeded} />
        )}
        {layers.accessories.length === 0 ? (
          <EmptyLayer title={messages.layers.accessories} status={messages.layers.notNeeded} />
        ) : null}
        {layers.accessories.map((item) => (
          <LayerCard
            key={`${item.id}-${gender}`}
            garment={item}
            gender={gender}
            isSeniorMode={isSeniorMode}
          />
        ))}
      </div>
    </section>
  )
}
