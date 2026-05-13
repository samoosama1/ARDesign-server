import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import QRCode from 'qrcode'
import { useAuth } from '../hooks/useAuth'
import { apiFetch } from '../api/client'
import { useLocarnoTree } from '../hooks/useLocarnoTree'
import Combobox from '../components/Combobox'
import DesignCard from '../components/DesignCard'

const PAGE_SIZE = 50
const SEARCH_DEBOUNCE_MS = 250
const POLL_TICKS = 60

export default function BrowsePage() {
  const { user } = useAuth()
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

  // Viewer + QR modals
  const [viewerPatent, setViewerPatent] = useState(null)
  const [qrDataUrl, setQrDataUrl] = useState(null)
  const [qrPatentName, setQrPatentName] = useState('')

  const pollRefs = useRef({})

  const mainOptions = useMemo(() => {
    if (!tree) return []
    return tree.main_classes.map((m) => ({
      value: m.value,
      label: `Class ${m.number} — ${m.label}`,
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

  // Clean up any pollers on unmount
  useEffect(() => () => {
    Object.values(pollRefs.current).forEach(clearInterval)
  }, [])

  function pollStatus(patentId) {
    if (pollRefs.current[patentId]) return
    let count = 0
    const id = setInterval(async () => {
      count++
      if (count > POLL_TICKS) {
        clearInterval(id)
        delete pollRefs.current[patentId]
        fetchPage(0, false)
        return
      }
      try {
        const res = await apiFetch(`/api/patents/${patentId}/status`)
        if (!res.ok) return
        const data = await res.json()
        if (data.status === 'CONVERTED' || data.status === 'FAILED') {
          clearInterval(id)
          delete pollRefs.current[patentId]
          fetchPage(0, false)
        }
      } catch { /* retry */ }
    }, 2000)
    pollRefs.current[patentId] = id
  }

  function handleMainChange(v) {
    setMainClass(v)
    setSubclass('')
  }

  function clearFilters() {
    setSearchInput('')
    setMainClass('')
    setSubclass('')
  }

  async function handleConvert(patentId) {
    try {
      const res = await apiFetch(`/api/patents/${patentId}/convert`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Failed to start conversion')
      }
      await fetchPage(0, false)
      pollStatus(patentId)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this design?')) return
    try {
      const res = await apiFetch(`/api/patents/${id}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) fetchPage(0, false)
    } catch { /* silent */ }
  }

  async function handleDownload(id, filename) {
    try {
      const res = await apiFetch(`/api/patents/${id}/model`)
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${filename}.glb`
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* silent */ }
  }

  async function handleQR(id, filename) {
    const url = `${window.location.origin}/api/patents/${id}/model`
    const dataUrl = await QRCode.toDataURL(url, { width: 256 })
    setQrDataUrl(dataUrl)
    setQrPatentName(filename)
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
              placeholder="Typos welcome — e.g. 'chiar'"
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
                <DesignCard
                  key={p.id}
                  patent={p}
                  currentUserId={user?.id}
                  locarnoTree={tree}
                  onConvert={handleConvert}
                  onView={setViewerPatent}
                  onDownload={handleDownload}
                  onQR={handleQR}
                  onDelete={handleDelete}
                />
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

      {qrDataUrl && (
        <div className="modal-overlay" onClick={() => setQrDataUrl(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{qrPatentName}</h3>
            <img src={qrDataUrl} alt="QR Code" />
            <p className="qr-hint">Scan to open 3D model</p>
            <button onClick={() => setQrDataUrl(null)}>Close</button>
          </div>
        </div>
      )}

      {viewerPatent && (
        <div className="modal-overlay" onClick={() => setViewerPatent(null)}>
          <div className="viewer-modal" onClick={(e) => e.stopPropagation()}>
            <h3>{viewerPatent.model_filename}</h3>
            <model-viewer
              src={`/api/patents/${viewerPatent.id}/model`}
              camera-controls
              auto-rotate
              shadow-intensity="1"
              exposure="1"
            />
            <button className="viewer-close" onClick={() => setViewerPatent(null)}>
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
