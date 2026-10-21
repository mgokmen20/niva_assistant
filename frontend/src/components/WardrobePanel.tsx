import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import { useI18n } from '../i18n/useI18n'
import {
  ApiError,
  createWardrobeItem,
  deleteWardrobeItem,
  fetchWardrobe,
  toggleWardrobeItem,
  updateWardrobeItem,
} from '../services/api'
import type { WardrobeCategory, WardrobeColor, WardrobeItem, WardrobeStyle, WardrobeThickness } from '../types/api'
import { categoryIcon } from '../utils/garmentVisuals'

const CATEGORIES: readonly WardrobeCategory[] = ['T-Shirt', 'Sweater', 'Pants', 'Outerwear', 'Shorts', 'Accessory']
const THICKNESSES: readonly WardrobeThickness[] = ['Thin', 'Normal', 'Thick', 'Thermal']
const STYLES: readonly WardrobeStyle[] = ['Casual', 'Sport', 'Formal', 'Outdoor']
const COLORS: readonly WardrobeColor[] = ['Black', 'Blue', 'Red', 'White', 'Green', 'Navy', 'Grey']

const fieldClass =
  'mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600'

const labelClass = 'block text-sm font-medium text-slate-700'

function messageFrom(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message.trim() !== '') {
    return error.message
  }
  return fallback
}

function isWardrobeColor(value: string): value is WardrobeColor {
  return (COLORS as readonly string[]).includes(value)
}

function WardrobeThumb({ item }: { item: WardrobeItem }) {
  const icon = categoryIcon(item.category)
  const direct = item.image_url?.trim() ?? ''
  const [source, setSource] = useState(direct !== '' ? direct : icon)
  return (
    <img
      src={source}
      alt=""
      className="h-10 w-10 shrink-0 rounded-md bg-slate-50 object-contain"
      onError={() => {
        if (source !== icon) {
          setSource(icon)
        }
      }}
    />
  )
}

const emptyForm = {
  itemName: '',
  category: 'T-Shirt' as WardrobeCategory,
  thickness: 'Normal' as WardrobeThickness,
  style: 'Casual' as WardrobeStyle,
  colorName: 'Black' as WardrobeColor,
  waterproof: false,
  imageUrl: '',
}

/** Signed-in wardrobe: add, edit, and list clothing the wearer owns. */
export function WardrobePanel({ token }: { token: string }) {
  const { messages } = useI18n()
  const copy = messages.profile
  const [items, setItems] = useState<WardrobeItem[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [itemName, setItemName] = useState(emptyForm.itemName)
  const [category, setCategory] = useState<WardrobeCategory>(emptyForm.category)
  const [thickness, setThickness] = useState<WardrobeThickness>(emptyForm.thickness)
  const [style, setStyle] = useState<WardrobeStyle>(emptyForm.style)
  const [colorName, setColorName] = useState<WardrobeColor>(emptyForm.colorName)
  const [waterproof, setWaterproof] = useState(emptyForm.waterproof)
  const [imageUrl, setImageUrl] = useState(emptyForm.imageUrl)

  const loadItems = useCallback(async () => {
    const next = await fetchWardrobe(token)
    setItems(next)
  }, [token])

  useEffect(() => {
    let active = true
    void fetchWardrobe(token)
      .then((next) => {
        if (active) {
          setItems(next)
        }
      })
      .catch((caught: unknown) => {
        if (active) {
          setError(messageFrom(caught, messages.common.tryAgain))
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [messages.common.tryAgain, token])

  function resetForm() {
    setEditingId(null)
    setItemName(emptyForm.itemName)
    setCategory(emptyForm.category)
    setThickness(emptyForm.thickness)
    setStyle(emptyForm.style)
    setColorName(emptyForm.colorName)
    setWaterproof(emptyForm.waterproof)
    setImageUrl(emptyForm.imageUrl)
  }

  function beginEdit(item: WardrobeItem) {
    setEditingId(item.id)
    setItemName(item.item_name)
    setCategory(item.category)
    setThickness(item.thickness)
    setStyle(item.style)
    setColorName(isWardrobeColor(item.color_name) ? item.color_name : 'Black')
    setWaterproof(item.is_waterproof)
    setImageUrl(item.image_url ?? '')
    setError(null)
    setNotice(null)
    document.getElementById('wardrobe-item-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  async function saveItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = itemName.trim()
    if (name === '') {
      return
    }
    const input = {
      item_name: name,
      category,
      thickness,
      style,
      color_name: colorName,
      is_waterproof: waterproof,
      image_url: imageUrl.trim() === '' ? null : imageUrl.trim(),
    }
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      if (editingId !== null) {
        await updateWardrobeItem(token, editingId, input)
        setNotice(copy.itemUpdated)
      } else {
        await createWardrobeItem(token, input)
        setNotice(copy.itemAdded)
      }
      await loadItems()
      resetForm()
    } catch (caught) {
      setError(messageFrom(caught, messages.common.tryAgain))
    } finally {
      setSubmitting(false)
    }
  }

  async function toggleActive(itemId: string) {
    setError(null)
    setNotice(null)
    try {
      const next = await toggleWardrobeItem(token, itemId)
      setItems((current) => current.map((item) => (item.id === next.id ? next : item)))
    } catch (caught) {
      setError(messageFrom(caught, messages.common.tryAgain))
    }
  }

  async function removeItem(itemId: string) {
    setDeletingId(itemId)
    setError(null)
    setNotice(null)
    try {
      await deleteWardrobeItem(token, itemId)
      if (editingId === itemId) {
        resetForm()
      }
      await loadItems()
      setNotice(copy.itemDeleted)
    } catch (caught) {
      setError(messageFrom(caught, messages.common.tryAgain))
    } finally {
      setDeletingId(null)
    }
  }

  const editing = editingId !== null

  return (
    <div className="space-y-4">
      {error ? (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-900" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-950" role="status">
          {notice}
        </p>
      ) : null}

      <section id="wardrobe-item-form" className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm md:p-5">
        <h2 className="text-base font-semibold text-slate-950">{editing ? copy.wardrobeEdit : copy.wardrobeAdd}</h2>
        <form className="mt-4 space-y-4" onSubmit={(event) => void saveItem(event)}>
          <label className={labelClass} htmlFor="wardrobe-item-name">
            {copy.itemName}
            <input
              id="wardrobe-item-name"
              value={itemName}
              onChange={(event) => setItemName(event.target.value)}
              className={fieldClass}
              placeholder={copy.itemNamePlaceholder}
              maxLength={120}
              required
            />
          </label>
          <label className={labelClass} htmlFor="wardrobe-image-url">
            {copy.imageUrl}
            <input
              id="wardrobe-image-url"
              value={imageUrl}
              onChange={(event) => setImageUrl(event.target.value)}
              className={fieldClass}
              placeholder={copy.imageUrlPlaceholder}
              inputMode="url"
              maxLength={500}
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-3">
            <label className={labelClass} htmlFor="wardrobe-category">
              {copy.category}
              <select
                id="wardrobe-category"
                value={category}
                onChange={(event) => setCategory(event.target.value as WardrobeCategory)}
                className={fieldClass}
              >
                {CATEGORIES.map((option) => (
                  <option key={option} value={option}>
                    {copy.categoryLabels[option]}
                  </option>
                ))}
              </select>
            </label>
            <label className={labelClass} htmlFor="wardrobe-style">
              {copy.style}
              <select
                id="wardrobe-style"
                value={style}
                onChange={(event) => setStyle(event.target.value as WardrobeStyle)}
                className={fieldClass}
              >
                {STYLES.map((option) => (
                  <option key={option} value={option}>
                    {copy.styleLabels[option]}
                  </option>
                ))}
              </select>
            </label>
            <label className={labelClass} htmlFor="wardrobe-color">
              {copy.color}
              <select
                id="wardrobe-color"
                value={colorName}
                onChange={(event) => setColorName(event.target.value as WardrobeColor)}
                className={fieldClass}
              >
                {COLORS.map((option) => (
                  <option key={option} value={option}>
                    {copy.colorLabels[option]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <fieldset>
            <legend className="text-sm font-medium text-slate-700">{copy.thickness}</legend>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
              {THICKNESSES.map((option) => (
                <label key={option} className="inline-flex items-center gap-2 text-sm text-slate-800">
                  <input
                    type="radio"
                    name="wardrobe-thickness"
                    value={option}
                    checked={thickness === option}
                    onChange={() => setThickness(option)}
                    className="h-4 w-4 accent-blue-600"
                  />
                  {copy.thicknessLabels[option]}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-800">
            <input
              type="checkbox"
              checked={waterproof}
              onChange={(event) => setWaterproof(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300 accent-blue-600"
            />
            {copy.waterproof}
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex min-h-10 items-center rounded-md bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:opacity-60"
            >
              {submitting ? (editing ? copy.updatingItem : copy.addingItem) : editing ? copy.updateItem : copy.addItem}
            </button>
            {editing ? (
              <button
                type="button"
                onClick={resetForm}
                className="inline-flex min-h-10 items-center rounded-md border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
              >
                {copy.cancelEdit}
              </button>
            ) : null}
          </div>
        </form>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-4 py-3 md:px-5">
          <h2 className="text-base font-semibold text-slate-950">{copy.tabWardrobe}</h2>
        </div>
        {loading ? (
          <p className="px-4 py-3 text-sm text-slate-600 md:px-5" role="status">
            {copy.wardrobeLoading}
          </p>
        ) : null}
        {!loading && items.length === 0 ? (
          <p className="px-4 py-3 text-sm text-slate-600 md:px-5">{copy.wardrobeEmpty}</p>
        ) : null}
        {items.length > 0 ? (
          <div className="max-h-80 overflow-auto">
            <table className="min-w-full border-collapse text-left text-sm">
              <thead className="sticky top-0 z-10 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-2 font-semibold md:px-5">
                    {copy.columnName}
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {copy.columnCategory}
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {copy.columnDetails}
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    {copy.columnStatus}
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-semibold md:px-5">
                    {copy.columnActions}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => {
                  const colorLabel =
                    copy.colorLabels[item.color_name as keyof typeof copy.colorLabels] ?? item.color_name
                  return (
                    <tr key={item.id} className={editingId === item.id ? 'bg-blue-50' : 'bg-white'}>
                      <th scope="row" className="px-4 py-2.5 text-left text-sm font-medium text-slate-950 md:px-5">
                        <span className="flex items-center gap-3">
                          <WardrobeThumb key={`${item.id}-${item.image_url ?? ''}`} item={item} />
                          {item.item_name}
                        </span>
                      </th>
                      <td className="whitespace-nowrap px-3 py-2.5 text-slate-700">
                        {copy.categoryLabels[item.category]}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-slate-600">
                        <span>
                          {copy.thicknessLabels[item.thickness]} · {copy.styleLabels[item.style]} · {colorLabel}
                        </span>
                        {item.is_waterproof ? <span className="mt-0.5 block text-slate-500">{copy.waterproof}</span> : null}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2.5">
                        <button
                          type="button"
                          role="switch"
                          aria-checked={item.is_active}
                          aria-label={`${item.item_name}: ${item.is_active ? copy.activeItem : copy.laundryItem}`}
                          onClick={() => void toggleActive(item.id)}
                          className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                        >
                          <span
                            aria-hidden="true"
                            className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                              item.is_active ? 'bg-blue-600' : 'bg-slate-300'
                            }`}
                          >
                            <span
                              className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                                item.is_active ? 'translate-x-4' : 'translate-x-0'
                              }`}
                            />
                          </span>
                          {item.is_active ? copy.activeItem : copy.laundryItem}
                        </button>
                      </td>
                      <td className="px-4 py-2.5 text-right md:px-5">
                        <div className="inline-flex items-center justify-end gap-1">
                          <button
                            type="button"
                            aria-label={`${copy.editItem} ${item.item_name}`}
                            onClick={() => beginEdit(item)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
                          >
                            <Pencil aria-hidden="true" size={16} />
                          </button>
                          <button
                            type="button"
                            aria-label={`${copy.deleteItem} ${item.item_name}`}
                            disabled={deletingId === item.id}
                            onClick={() => void removeItem(item.id)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-rose-50 hover:text-rose-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-700 disabled:opacity-60"
                          >
                            <Trash2 aria-hidden="true" size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  )
}
