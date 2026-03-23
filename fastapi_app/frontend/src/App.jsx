import { useState, useEffect, useRef, useCallback } from 'react'
import QRCode from 'qrcode'

export default function App() {
  const [patents, setPatents] = useState([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [qrDataUrl, setQrDataUrl] = useState(null)
  const [qrPatentName, setQrPatentName] = useState('')
  const fileRef = useRef()
  const pollRefs = useRef({})

  const fetchPatents = useCallback(async () => {
    try {
      const res = await fetch('/api/patents/')
      if (res.ok) setPatents(await res.json())
    } catch {
      /* silent — list will just be stale */
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
        const res = await fetch(`/api/patents/${patentId}/status`)
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

      const uploadRes = await fetch('/api/patents/upload', { method: 'POST', body: form })
      if (!uploadRes.ok) {
        const err = await uploadRes.json()
        throw new Error(err.detail || 'Upload failed')
      }
      const { patent_id } = await uploadRes.json()

      const convertRes = await fetch(`/api/patents/${patent_id}/convert`, { method: 'POST' })
      if (!convertRes.ok) {
        const err = await convertRes.json()
        throw new Error(err.detail || 'Failed to start conversion')
      }

      fileRef.current.value = ''
      await fetchPatents()
      pollStatus(patent_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  function handleDownload(id, filename) {
    const a = document.createElement('a')
    a.href = `/api/patents/${id}/model`
    a.download = `${filename}.glb`
    a.click()
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
              <p className="meta">{new Date(p.uploaded_at).toLocaleDateString()}</p>
              {p.status === 'CONVERTED' && (
                <div className="card-actions">
                  <button onClick={() => handleDownload(p.id, p.model_filename)}>
                    Download GLB
                  </button>
                  <button onClick={() => handleQR(p.id, p.model_filename)}>
                    QR Code
                  </button>
                </div>
              )}
              {p.status === 'FAILED' && (
                <p className="error">Conversion failed</p>
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
