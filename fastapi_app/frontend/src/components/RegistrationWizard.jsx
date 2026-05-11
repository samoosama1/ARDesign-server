import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api/client'
import Combobox from './Combobox'

/**
 * 2-phase design registration form.
 *   Phase 1: design name + Locarno main class + Locarno subclass.
 *   Phase 2: ZIP upload + submit.
 * Phase 1 is held in browser state — nothing is persisted until Phase 2 fires
 * the single multipart POST to /api/patents/upload.
 *
 * Locarno tree is fetched lazily from /api/locarno when the wizard first
 * opens, cached on the module instance for the rest of the session.
 */
let locarnoCache = null
let locarnoPromise = null

function loadLocarno() {
  if (locarnoCache) return Promise.resolve(locarnoCache)
  if (locarnoPromise) return locarnoPromise
  locarnoPromise = apiFetch('/api/locarno')
    .then(async (res) => {
      if (!res.ok) throw new Error(`Failed to load Locarno tree (${res.status})`)
      const data = await res.json()
      locarnoCache = data
      return data
    })
    .finally(() => { locarnoPromise = null })
  return locarnoPromise
}

export default function RegistrationWizard({ open, onClose, onComplete }) {
  const [phase, setPhase] = useState(1)
  const [designName, setDesignName] = useState('')
  const [mainClass, setMainClass] = useState('')
  const [subclass, setSubclass] = useState('')
  const [file, setFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const [tree, setTree] = useState(locarnoCache)
  const [treeLoading, setTreeLoading] = useState(false)

  useEffect(() => {
    if (!open || tree) return
    setTreeLoading(true)
    loadLocarno()
      .then(setTree)
      .catch((e) => setError(e.message))
      .finally(() => setTreeLoading(false))
  }, [open, tree])

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

  const mainSummary = useMemo(
    () => tree?.main_classes.find((m) => m.value === mainClass) || null,
    [tree, mainClass],
  )
  const subSummary = useMemo(
    () => subOptions.find((s) => s.value === subclass) || null,
    [subOptions, subclass],
  )

  function resetAndClose() {
    setPhase(1)
    setDesignName('')
    setMainClass('')
    setSubclass('')
    setFile(null)
    setError(null)
    onClose()
  }

  function handleMainChange(v) {
    setMainClass(v)
    setSubclass('')
  }

  function goNext() {
    if (!designName.trim()) { setError('Enter a design name.'); return }
    if (!mainClass || !subclass) { setError('Choose a Locarno main class and subclass.'); return }
    setError(null)
    setPhase(2)
  }

  async function handleSubmit() {
    if (!file) { setError('Pick a ZIP file.'); return }
    setSubmitting(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('design_name', designName.trim())
      form.append('locarno_main_class', mainClass)
      form.append('locarno_subclass', subclass)
      const res = await apiFetch('/api/patents/upload', { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Upload failed')
      }
      resetAndClose()
      onComplete?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  return (
    <div className="modal-overlay" onClick={resetAndClose}>
      <div className="modal wizard-modal" onClick={(e) => e.stopPropagation()}>
        <header className="wizard-header">
          <h2>Register a design</h2>
          <div className="wizard-steps">
            <span className={phase === 1 ? 'active' : 'done'}>1 · Details</span>
            <span className={phase === 2 ? 'active' : ''}>2 · Upload</span>
          </div>
        </header>

        {phase === 1 && (
          <div className="wizard-body">
            <label className="wizard-field">
              <span>Design name</span>
              <input
                type="text"
                value={designName}
                onChange={(e) => setDesignName(e.target.value)}
                placeholder="e.g. Curved-back office chair"
                maxLength={255}
              />
            </label>
            <label className="wizard-field">
              <span>Locarno main class</span>
              <Combobox
                options={mainOptions}
                value={mainClass}
                onChange={handleMainChange}
                placeholder={treeLoading ? 'Loading…' : 'Type to filter — e.g. furniture, foodstuffs'}
                disabled={treeLoading || !tree}
              />
            </label>
            <label className="wizard-field">
              <span>Locarno subclass</span>
              <Combobox
                options={subOptions}
                value={subclass}
                onChange={setSubclass}
                placeholder={
                  treeLoading
                    ? 'Loading…'
                    : mainClass
                    ? 'Type to filter subclasses'
                    : 'Pick a main class first'
                }
                disabled={treeLoading || !mainClass}
              />
            </label>
          </div>
        )}

        {phase === 2 && (
          <div className="wizard-body">
            <div className="wizard-summary">
              <p><strong>{designName}</strong></p>
              <p className="meta">
                {mainSummary && `Class ${mainSummary.number} — ${mainSummary.label}`}
              </p>
              <p className="meta">{subSummary?.label}</p>
            </div>
            <label className="wizard-field">
              <span>Design ZIP (3D model files)</span>
              <input
                type="file"
                accept=".zip"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            {file && (
              <p className="meta">
                {file.name} ({Math.round(file.size / 1024)} KB)
              </p>
            )}
          </div>
        )}

        {error && <p className="error">{error}</p>}

        <footer className="wizard-footer">
          <button type="button" onClick={resetAndClose} disabled={submitting}>Cancel</button>
          {phase === 2 && (
            <button type="button" onClick={() => setPhase(1)} disabled={submitting}>
              ← Back
            </button>
          )}
          {phase === 1 && (
            <button type="button" className="btn-primary" onClick={goNext} disabled={treeLoading}>
              Next →
            </button>
          )}
          {phase === 2 && (
            <button
              type="button"
              className="btn-primary"
              onClick={handleSubmit}
              disabled={!file || submitting}
            >
              {submitting ? 'Submitting…' : 'Submit registration'}
            </button>
          )}
        </footer>
      </div>
    </div>
  )
}