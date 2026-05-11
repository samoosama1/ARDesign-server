import { useState, useEffect, useRef, useMemo } from 'react'

/**
 * Searchable single-select combobox. Used by the design-registration wizard
 * because SINIF 8 alone has 413 Locarno subclasses — a native <select> is
 * usable but not pleasant at that length.
 *
 * Props:
 *   options: [{ value, label }]
 *   value: string | ''
 *   onChange: (value) => void
 *   placeholder, disabled
 */
export default function Combobox({ options, value, onChange, placeholder, disabled }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const rootRef = useRef(null)
  const listRef = useRef(null)

  const selected = useMemo(
    () => options.find((o) => o.value === value) || null,
    [options, value],
  )

  // When closed: show the selected label. When open: show user's query.
  const display = open ? query : selected?.label ?? ''

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((o) => o.label.toLowerCase().includes(q))
  }, [options, query])

  useEffect(() => {
    if (!open) return
    function onMouseDown(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [open])

  // Keep highlighted option scrolled into view.
  useEffect(() => {
    if (!open || !listRef.current) return
    const el = listRef.current.querySelector(`[data-idx="${highlight}"]`)
    if (el) el.scrollIntoView({ block: 'nearest' })
  }, [highlight, open])

  function select(opt) {
    onChange(opt.value)
    setOpen(false)
    setQuery('')
  }

  function onKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) {
        setOpen(true)
        setHighlight(0)
        return
      }
      setHighlight((h) => Math.min(h + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      if (open && filtered[highlight]) {
        e.preventDefault()
        select(filtered[highlight])
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
      setQuery('')
    }
  }

  return (
    <div className={`combobox ${disabled ? 'disabled' : ''}`} ref={rootRef}>
      <input
        type="text"
        className="combobox-input"
        value={display}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
          setHighlight(0)
        }}
        onFocus={() => !disabled && setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
      />
      {open && (
        <ul className="combobox-list" ref={listRef}>
          {filtered.length === 0 && <li className="combobox-empty">No matches</li>}
          {filtered.map((opt, i) => (
            <li
              key={opt.value}
              data-idx={i}
              className={`combobox-option ${i === highlight ? 'highlight' : ''} ${
                opt.value === value ? 'selected' : ''
              }`}
              onMouseDown={(e) => {
                e.preventDefault()
                select(opt)
              }}
              onMouseEnter={() => setHighlight(i)}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}