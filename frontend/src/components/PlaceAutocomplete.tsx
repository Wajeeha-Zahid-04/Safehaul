import { useQuery } from '@tanstack/react-query'
import { useId, useState, type KeyboardEvent } from 'react'
import { geocode } from '../api/client'
import type { Place } from '../api/types'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

const DEBOUNCE_MS = 300
const MIN_QUERY_LENGTH = 2

interface Props {
  label: string
  placeholder: string
  value: Place | null
  onChange: (place: Place | null) => void
}

export function PlaceAutocomplete({ label, placeholder, value, onChange }: Props) {
  const id = useId()
  const listId = `${id}-list`
  const [text, setText] = useState(value?.label ?? '')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)

  const query = useDebouncedValue(text.trim(), DEBOUNCE_MS)
  const searching = open && query.length >= MIN_QUERY_LENGTH && query !== value?.label
  const { data: results = [], isFetching, isError } = useQuery({
    queryKey: ['geocode', query],
    queryFn: ({ signal }) => geocode(query, signal),
    enabled: searching,
    staleTime: 5 * 60_000,
  })
  const showList = searching && (results.length > 0 || isError || !isFetching)

  function select(place: Place) {
    onChange(place)
    setText(place.label)
    setOpen(false)
    setActive(-1)
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!showList || results.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => (i + 1) % results.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      select(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        maxLength={200}
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
          setActive(-1)
          if (value) onChange(null) // typing invalidates the previous pick
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:ring-2 focus:ring-sky-200 focus:outline-none"
      />
      {searching && isFetching && (
        <span className="absolute top-9 right-3 text-xs text-slate-400">Searching…</span>
      )}
      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-slate-200 bg-white py-1 text-sm shadow-lg"
        >
          {isError && <li className="px-3 py-2 text-red-600">Search failed. Keep typing to retry.</li>}
          {!isError && results.length === 0 && (
            <li className="px-3 py-2 text-slate-500">No places found.</li>
          )}
          {results.map((place, i) => (
            <li
              key={`${place.lat},${place.lon},${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              // mousedown (not click) fires before the input's blur closes the list
              onMouseDown={(e) => {
                e.preventDefault()
                select(place)
              }}
              className={`cursor-pointer px-3 py-2 ${i === active ? 'bg-sky-50 text-sky-900' : 'hover:bg-slate-50'}`}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
