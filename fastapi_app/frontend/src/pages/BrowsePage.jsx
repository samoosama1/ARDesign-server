import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import { useLocarnoTree } from '../hooks/useLocarnoTree'
import Combobox from '../components/Combobox'
import DesignCard from '../components/DesignCard'

const PAGE_SIZE = 50
const SEARCH_DEBOUNCE_MS = 250

export default function BrowsePage() {
  const { tree, loading: treeLoading } = useLocarnoTree(true)

  // Filter inputs (immediate)
  const [searchInput, setSearchInput] = useState('')
  const [mainClass, setMainClass] = useState('')
  const [subclass, setSubclass] = useState('')

  // Debounced search term (what gets sent to the API)
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchInput.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [searchInput])

  // Results
  const [results, setResults] = useState([])
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const mainOptions = useMemo(() => {
    if (!tree) return []
    return tree.main_classes.map((m) => ({
      value: m.value,
      label: `Class ${m.number}: ${m.label}`,
    }))
  }, [tree])
  const subOptions = useMemo(() => {
    if (!tree || !mainClass) return []
    return tree.subclasses_by_main[mainClass] || []
  }, [tree, mainClass])

  const fetchPage = useCallback(async (startOffset, append) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (debouncedSearch) params.set('q', debouncedSearch)
      if (mainClass) params.set('locarno_main', mainClass)
      if (subclass) params.set('locarno_subclass', subclass)
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(startOffset))

      const res = await apiFetch(`/api/patents/?${params.toString()}`)
      if (!res.ok) throw new Error(`Search failed (${res.status})`)
      const data = await res.json()
      setResults((prev) => (append ? [...prev, ...data] : data))
      setOffset(startOffset + data.length)
      setHasMore(data.length === PAGE_SIZE)
    } catch (err) {
      setError(err.message)
      if (!append) setResults([])
    } finally {
      setLoading(false)
    }
  }, [debouncedSearch, mainClass, subclass])

  // Re-fetch from the top whenever filters change
  useEffect(() => {
    fetchPage(0, false)
  }, [fetchPage])

  function handleMainChange(v) {
    setMainClass(v)
    setSubclass('')
  }

  function clearFilters() {
    setSearchInput('')
    setMainClass('')
    setSubclass('')
  }

  const hasFilters = Boolean(searchInput || mainClass || subclass)

  return (
    <div className="page">
      <div className="browse-layout">
        <aside className="browse-filters">
          <h2>
            Filters
            {hasFilters && (
              <button type="button" className="clear-btn" onClick={clearFilters}>
                Clear all
              </button>
            )}
          </h2>

          <label>
            <span>Search by name</span>
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Start typing..."
            />
          </label>

          <label>
            <span>Locarno main class</span>
            <Combobox
              options={mainOptions}
              value={mainClass}
              onChange={handleMainChange}
              placeholder={treeLoading ? 'Loading…' : 'Any class'}
              disabled={treeLoading || !tree}
            />
          </label>

          <label>
            <span>Locarno subclass</span>
            <Combobox
              options={subOptions}
              value={subclass}
              onChange={setSubclass}
              placeholder={mainClass ? 'Any subclass' : 'Pick a main class first'}
              disabled={treeLoading || !mainClass}
            />
          </label>
        </aside>

        <main className="browse-results">
          <h1>Browse designs</h1>
          <p className="browse-subtitle">
            {loading && results.length === 0
              ? 'Searching…'
              : `${results.length} design${results.length === 1 ? '' : 's'}${
                  hasMore ? '+' : ''
                } shown${debouncedSearch ? ` for "${debouncedSearch}"` : ''}`}
          </p>

          {error && <p className="error">{error}</p>}

          {!loading && results.length === 0 ? (
            <div className="browse-empty">
              <div className="browse-empty-icon">◌</div>
              <h3>No designs match your filters</h3>
              <p>Try removing a filter or loosening the search term.</p>
            </div>
          ) : (
            <section className="patents-grid">
              {results.map((p) => (
                <DesignCard key={p.id} patent={p} locarnoTree={tree} />
              ))}
            </section>
          )}

          {hasMore && (
            <div className="browse-loadmore">
              <button
                type="button"
                disabled={loading}
                onClick={() => fetchPage(offset, true)}
              >
                {loading ? 'Loading…' : 'Load more'}
              </button>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}