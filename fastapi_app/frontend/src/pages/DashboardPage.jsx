import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import QRCode from 'qrcode'
import { useAuth } from '../hooks/useAuth'
import { apiFetch } from '../api/client'
import ActionButton from '../components/ActionButton'

const VIEWS = ['front', 'left', 'right', 'back']

// Polling windows (2s tick).
// ZIP conversion: ~2 min. Image generation: ~15 min (GPU-bound, queued behind other jobs).
const POLL_TICKS_CONVERT = 60
const POLL_TICKS_GENERATE = 450

export default function DashboardPage() {
  const { user, logout } = useAuth()
  const [patents, setPatents] = useState([])
  const [activeTab, setActiveTab] = useState('zip')
  const [uploading, setUploading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)

  // ZIP upload
  const fileRef = useRef()

  // Image generate
  const [views, setViews] = useState({}) // { front: File, left: File, ... }
  const [genTitle, setGenTitle] = useState('')

  // One object URL per selected File; revoked when the file is replaced/cleared.
  const previews = useMemo(() => {
    const out = {}
    for (const v of VIEWS) {
      if (views[v]) out[v] = URL.createObjectURL(views[v])
    }
    return out
  }, [views])

  useEffect(() => {
    return () => {
      Object.values(previews).forEach((url) => URL.revokeObjectURL(url))
    }
  }, [previews])

  // QR + viewer modals
  const [qrDataUrl, setQrDataUrl] = useState(null)
  const [qrPatentName, setQrPatentName] = useState('')
  const [viewerPatent, setViewerPatent] = useState(null)

  const pollRefs = useRef({})

  const fetchPatents = useCallback(async () => {
    try {
      const res = await apiFetch('/api/patents/')
      if (res.ok) setPatents(await res.json())
    } catch {
      /* silent */
    }
  }, [])

  useEffect(() => {
    fetchPatents()
    return () => {
      Object.values(pollRefs.current).forEach(clearInterval)
    }
  }, [fetchPatents])

  function pollStatus(patentId, maxTicks = POLL_TICKS_CONVERT) {
    if (pollRefs.current[patentId]) return // already polling
    let count = 0
    const id = setInterval(async () => {
      count++
      if (count > maxTicks) {
        clearInterval(id)
        delete pollRefs.current[patentId]
        fetchPatents()
        return
      }
      try {
        const res = await apiFetch(`/api/patents/${patentId}/status`)
        if (!res.ok) return
        const data = await res.json()
        if (data.status === 'CONVERTED' || data.status === 'FAILED') {
          clearInterval(id)
          delete pollRefs.current[patentId]
          fetchPatents()
        }
      } catch {
        /* retry next tick */
      }
    }, 2000)
    pollRefs.current[patentId] = id
  }

  async function handleUpload(e) {
    e.preventDefault()
    setError(null)
    const file = fileRef.current?.files[0]
    if (!file) return

    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)

      const uploadRes = await apiFetch('/api/patents/upload', { method: 'POST', body: form })
      if (!uploadRes.ok) {
        const err = await uploadRes.json()
        throw new Error(err.detail || 'Upload failed')
      }

      fileRef.current.value = ''
      await fetchPatents()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  function setViewFile(view, file) {
    setViews((prev) => {
      const next = { ...prev }
      if (file) next[view] = file
      else delete next[view]
      return next
    })
  }

  async function handleGenerate(e) {
    e.preventDefault()
    setError(null)
    if (!views.front) {
      setError('Front view is required.')
      return
    }

    setGenerating(true)
    try {
      const form = new FormData()
      VIEWS.forEach((v) => {
        if (views[v]) form.append(v, views[v])
      })
      if (genTitle.trim()) form.append('title', genTitle.trim())

      const res = await apiFetch('/api/patents/generate', { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Generation request failed')
      }
      const data = await res.json()

      setViews({})
      setGenTitle('')
      await fetchPatents()
      pollStatus(data.patent_id, POLL_TICKS_GENERATE)
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  async function handleConvert(patentId) {
    setError(null)
    try {
      const res = await apiFetch(`/api/patents/${patentId}/convert`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to start conversion')
      }
      await fetchPatents()
      pollStatus(patentId, POLL_TICKS_CONVERT)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this patent?')) return
    try {
      const res = await apiFetch(`/api/patents/${id}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) fetchPatents()
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

  function statusClass(status) {
    return 'status status-' + status.toLowerCase()
  }

  return (
    <div className="app">
      <header>
        <h1>ARPatent</h1>
        <div className="header-right">
          <span className="username">{user?.username}</span>
          <button className="btn-logout" onClick={logout}>Sign Out</button>
        </div>
      </header>

      <section className="upload-section">
        <div className="tabs">
          <button
            className={activeTab === 'zip' ? 'active' : ''}
            onClick={() => { setActiveTab('zip'); setError(null) }}
          >
            Upload ZIP
          </button>
          <button
            className={activeTab === 'image' ? 'active' : ''}
            onClick={() => { setActiveTab('image'); setError(null) }}
          >
            Generate from Image
          </button>
        </div>

        {activeTab === 'zip' && (
          <form onSubmit={handleUpload}>
            <input type="file" accept=".zip" ref={fileRef} required />
            <button type="submit" disabled={uploading}>
              {uploading ? 'Uploading...' : 'Upload ZIP'}
            </button>
          </form>
        )}

        {activeTab === 'image' && (
          <form onSubmit={handleGenerate}>
            <p className="mv-hint">
              Front view is required. Left / back views improve quality.
              Right view is accepted but may be ignored by the model.
            </p>
            <div className="mv-grid">
              {VIEWS.map((view) => {
                const file = views[view]
                const preview = previews[view]
                return (
                  <label
                    key={view}
                    className={`mv-slot ${file ? 'filled' : ''} ${view === 'front' ? 'required' : ''}`}
                  >
                    <span className="mv-slot-label">{view}</span>
                    {preview ? (
                      <>
                        <img src={preview} alt={view} />
                        <button
                          type="button"
                          className="mv-clear"
                          onClick={(e) => { e.preventDefault(); setViewFile(view, null) }}
                          aria-label={`Clear ${view}`}
                        >
                          ×
                        </button>
                      </>
                    ) : (
                      <span className="mv-slot-empty">
                        <span>+</span>
                        <span>add {view}</span>
                      </span>
                    )}
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={(e) => setViewFile(view, e.target.files?.[0] || null)}
                    />
                  </label>
                )
              })}
            </div>
            <div className="mv-title-row">
              <input
                type="text"
                placeholder="Name for this model (optional)"
                value={genTitle}
                onChange={(e) => setGenTitle(e.target.value)}
              />
              <button type="submit" disabled={generating || !views.front}>
                {generating ? 'Starting...' : 'Generate 3D Model'}
              </button>
            </div>
          </form>
        )}

        {error && <p className="error">{error}</p>}
      </section>

      {patents.length === 0 ? (
        <p className="empty">No patents uploaded yet.</p>
      ) : (
        <section className="patents-grid">
          {patents.map((p) => (
            <div key={p.id} className="patent-card">
              <h3>{p.model_filename}</h3>
              <span className={statusClass(p.status)}>{p.status}</span>
              <p className="meta">Type: {p.file_type}</p>
              <p className="meta">Uploaded by: {p.uploaded_by}</p>
              <p className="meta">{new Date(p.uploaded_at).toLocaleDateString()}</p>
              {p.user_id === user?.id && p.status === 'UPLOADED' && (
                <div className="card-actions">
                  <ActionButton variant="primary" onClick={() => handleConvert(p.id)}>
                    Convert
                  </ActionButton>
                </div>
              )}
              {p.status === 'CONVERTED' && (
                <div className="card-actions">
                  <ActionButton variant="primary" onClick={() => setViewerPatent(p)}>
                    View
                  </ActionButton>
                  <ActionButton onClick={() => handleDownload(p.id, p.model_filename)}>
                    Download
                  </ActionButton>
                  <ActionButton onClick={() => handleQR(p.id, p.model_filename)}>
                    QR Code
                  </ActionButton>
                </div>
              )}
              {p.user_id === user?.id && p.status === 'FAILED' && p.file_type !== 'IMAGE' && (
                <div className="card-actions">
                  <ActionButton variant="primary" onClick={() => handleConvert(p.id)}>
                    Retry
                  </ActionButton>
                </div>
              )}
              {p.user_id === user?.id && (
                <div className="card-actions">
                  <ActionButton variant="danger" onClick={() => handleDelete(p.id)}>
                    Delete
                  </ActionButton>
                </div>
              )}
            </div>
          ))}
        </section>
      )}

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
