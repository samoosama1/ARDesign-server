import { useState, useEffect, useRef, useCallback } from 'react'
import QRCode from 'qrcode'
import { useAuth } from '../hooks/useAuth'
import { apiFetch } from '../api/client'
import ActionButton from '../components/ActionButton'

export default function DashboardPage() {
  const { user, logout } = useAuth()
  const [patents, setPatents] = useState([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [qrDataUrl, setQrDataUrl] = useState(null)
  const [qrPatentName, setQrPatentName] = useState('')
  const fileRef = useRef()
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

  function pollStatus(patentId) {
    let count = 0
    const id = setInterval(async () => {
      count++
      if (count > 60) {
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

  async function handleConvert(patentId) {
    setError(null)
    try {
      const res = await apiFetch(`/api/patents/${patentId}/convert`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to start conversion')
      }
      await fetchPatents()
      pollStatus(patentId)
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
        <form onSubmit={handleUpload}>
          <input type="file" accept=".zip" ref={fileRef} required />
          <button type="submit" disabled={uploading}>
            {uploading ? 'Uploading...' : 'Upload ZIP'}
          </button>
        </form>
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
                  <ActionButton onClick={() => handleDownload(p.id, p.model_filename)}>
                    Download GLB
                  </ActionButton>
                  <ActionButton onClick={() => handleQR(p.id, p.model_filename)}>
                    QR Code
                  </ActionButton>
                </div>
              )}
              {p.user_id === user?.id && p.status === 'FAILED' && (
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
    </div>
  )
}
