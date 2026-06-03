import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useLocation, useNavigate, Link } from 'react-router-dom'
import QRCode from 'qrcode'
import { useAuth } from '../hooks/useAuth'
import { apiFetch } from '../api/client'
import { useLocarnoTree } from '../hooks/useLocarnoTree'
import ActionButton from '../components/ActionButton'
import { statusLabel } from '../statusLabels'

const POLL_TICKS = 60

function statusClass(status) {
  return 'status status-' + status.toLowerCase()
}

/**
 * Dedicated page for a single design. Carries the actions that used to live on
 * the catalog card (Convert/Retry, Download, Delete) plus an always-visible 3D
 * viewer and QR code. The patent is handed in via router state for an instant
 * first paint, then revalidated against GET /api/patents/:id (which also covers
 * deep links and refreshes where there is no router state).
 */
export default function DesignDetailPage() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { tree } = useLocarnoTree(true)

  const [patent, setPatent] = useState(location.state?.patent ?? null)
  const [loading, setLoading] = useState(!location.state?.patent)
  const [error, setError] = useState(null)
  const [qrDataUrl, setQrDataUrl] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [show3d, setShow3d] = useState(false)
  const pollRef = useRef(null)

  const fetchPatent = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/patents/${id}`)
      if (res.status === 404) throw new Error('This design no longer exists.')
      if (!res.ok) throw new Error(`Failed to load design (${res.status})`)
      setPatent(await res.json())
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    fetchPatent()
  }, [fetchPatent])

  // Render the QR (it points at the public /model URL) as soon as the model is
  // ready; clear it back to a hint while the design is still being processed.
  useEffect(() => {
    if (!patent || patent.status !== 'CONVERTED') {
      setQrDataUrl(null)
      return
    }
    const url = `${window.location.origin}/api/patents/${patent.id}/model`
    QRCode.toDataURL(url, { width: 256 })
      .then(setQrDataUrl)
      .catch(() => setQrDataUrl(null))
  }, [patent])

  // Collapse the 3D viewer if the model stops being available (e.g. a re-convert
  // flips status back to QUEUED) so we never point model-viewer at a stale URL.
  useEffect(() => {
    if (patent?.status !== 'CONVERTED') setShow3d(false)
  }, [patent?.status])

  // Stop polling if the user navigates away mid-conversion.
  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current)
  }, [])

  function pollStatus() {
    if (pollRef.current) return
    let count = 0
    pollRef.current = setInterval(async () => {
      count++
      if (count > POLL_TICKS) {
        clearInterval(pollRef.current)
        pollRef.current = null
        fetchPatent()
        return
      }
      try {
        const res = await apiFetch(`/api/patents/${id}/status`)
        if (!res.ok) return
        const data = await res.json()
        if (data.status === 'CONVERTED' || data.status === 'FAILED') {
          clearInterval(pollRef.current)
          pollRef.current = null
          fetchPatent()
        }
      } catch { /* retry */ }
    }, 2000)
  }

  async function handleConvert() {
    setActionError(null)
    try {
      const res = await apiFetch(`/api/patents/${id}/convert`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Failed to start conversion')
      }
      await fetchPatent()
      pollStatus()
    } catch (err) {
      setActionError(err.message)
    }
  }

  async function handleDownload() {
    setActionError(null)
    try {
      const res = await apiFetch(`/api/patents/${id}/model`)
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${patent.model_filename}.glb`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setActionError('Download failed.')
    }
  }

  async function handleDelete() {
    if (!confirm('Delete this design?')) return
    try {
      const res = await apiFetch(`/api/patents/${id}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) navigate('/browse')
    } catch { /* silent */ }
  }

  if (loading) {
    return (
      <div className="page">
        <p className="browse-subtitle">Loading…</p>
      </div>
    )
  }

  if (error || !patent) {
    return (
      <div className="page detail-page">
        <Link to="/browse" className="back-link">← Back to browse</Link>
        <p className="error">{error || 'Design not found.'}</p>
      </div>
    )
  }

  const isOwner = patent.user_id === user?.id
  const isConverted = patent.status === 'CONVERTED'
  const warnings = patent.warnings ?? []

  let mainLabel = null
  let subLabel = null
  if (tree) {
    if (patent.locarno_main_class) {
      mainLabel = tree.main_classes.find(
        (m) => m.value === patent.locarno_main_class,
      )?.label || null
    }
    if (patent.locarno_subclass && patent.locarno_main_class) {
      subLabel = (tree.subclasses_by_main[patent.locarno_main_class] || [])
        .find((s) => s.value === patent.locarno_subclass)?.label || null
    }
  }
  const locarnoLine = [mainLabel, subLabel].filter(Boolean).join(' › ')

  return (
    <div className="page detail-page">
      <Link to="/browse" className="back-link">← Back to browse</Link>

      <div className="detail-header">
        <h1>{patent.model_filename}</h1>
        <span className={statusClass(patent.status)}>{statusLabel(patent.status)}</span>
      </div>

      <div className="detail-grid">
        <div className="detail-media">
          {isConverted && show3d ? (
            <model-viewer
              src={`/api/patents/${patent.id}/model`}
              camera-controls
              auto-rotate
              shadow-intensity="1"
              exposure="1"
            />
          ) : patent.has_thumbnail ? (
            <div className="card-thumb">
              <img
                src={`/api/patents/${patent.id}/thumbnail`}
                alt={patent.model_filename}
              />
            </div>
          ) : (
            <div className="card-thumb card-thumb-empty">
              <span aria-hidden="true">🖼</span>
              <span>No preview</span>
            </div>
          )}
          {isConverted && !show3d && (
            <button
              type="button"
              className="view-3d-btn"
              onClick={() => setShow3d(true)}
            >
              ▶ View in 3D
            </button>
          )}
        </div>

        <aside className="detail-side">
          <div className="detail-qr">
            <h3>QR Code</h3>
            {qrDataUrl ? (
              <>
                <img src={qrDataUrl} alt="QR code linking to the 3D model" />
                <p className="qr-hint">Scan to open the 3D model</p>
              </>
            ) : (
              <p className="meta">Available once the design is converted.</p>
            )}
          </div>

          <dl className="detail-meta">
            <div>
              <dt>Type</dt>
              <dd>{patent.file_type}</dd>
            </div>
            {locarnoLine && (
              <div>
                <dt>Locarno</dt>
                <dd>{locarnoLine}</dd>
              </div>
            )}
            <div>
              <dt>Uploaded by</dt>
              <dd>{patent.uploaded_by}</dd>
            </div>
            <div>
              <dt>Uploaded</dt>
              <dd>{new Date(patent.uploaded_at).toLocaleDateString()}</dd>
            </div>
          </dl>

          <div className="card-actions detail-actions">
            {isOwner && patent.status === 'UPLOADED' && (
              <ActionButton variant="primary" onClick={handleConvert}>
                Convert
              </ActionButton>
            )}
            {isOwner && patent.status === 'FAILED' && patent.file_type !== 'IMAGE' && (
              <ActionButton variant="primary" onClick={handleConvert}>
                Retry
              </ActionButton>
            )}
            {isConverted && (
              <ActionButton onClick={handleDownload}>Download</ActionButton>
            )}
            {isOwner && (
              <ActionButton variant="danger" onClick={handleDelete}>
                Delete
              </ActionButton>
            )}
          </div>
          {actionError && <p className="error">{actionError}</p>}
        </aside>
      </div>

      {warnings.length > 0 && (
        <section className="detail-warnings">
          <h3>Dönüşüm uyarıları</h3>
          <p className="meta">
            Model başarıyla dönüştürüldü, ancak dönüştürücü aşağıdaki konular
            hakkında uyardı. Modeli kontrol etmenizi öneririz.
          </p>
          <ul className="warnings-list">
            {warnings.map((w, i) => (
              <li key={i} className={`warning-item warning-${w.phase}`}>
                <span className="warning-phase">
                  {w.phase === 'import' ? 'İçe aktarma' : 'Dışa aktarma'}
                </span>
                <p className="warning-message">{w.message}</p>
                {w.details && <code className="warning-details">{w.details}</code>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}