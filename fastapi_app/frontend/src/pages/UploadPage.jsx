import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../api/client'
import { useLocarnoTree } from '../hooks/useLocarnoTree'
import Combobox from '../components/Combobox'
import RegistrationWizard from '../components/RegistrationWizard'

const VIEWS = ['front', 'left', 'right', 'back']

const QUALITY_OPTIONS = [
  { value: 'turbo', label: 'Turbo', hint: 'fastest, lower quality' },
  { value: 'fast', label: 'Fast', hint: 'balanced' },
  { value: 'standard', label: 'Standard', hint: 'best quality, slowest' },
]
const DETAIL_OPTIONS = [
  { value: 'low', label: 'Low', hint: 'coarse mesh' },
  { value: 'standard', label: 'Standard', hint: 'default' },
  { value: 'high', label: 'High', hint: 'finer detail' },
]

export default function UploadPage() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('zip')
  const [error, setError] = useState(null)
  const [wizardOpen, setWizardOpen] = useState(false)

  const [views, setViews] = useState({})
  const [genTitle, setGenTitle] = useState('')
  const [mainClass, setMainClass] = useState('')
  const [subclass, setSubclass] = useState('')
  const [quality, setQuality] = useState('standard')
  const [detail, setDetail] = useState('high')
  const [generating, setGenerating] = useState(false)

  // Same Locarno classification the ZIP-upload wizard uses. Loaded only while
  // the image tab is the one in view.
  const { tree, loading: treeLoading } = useLocarnoTree(activeTab === 'image')
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

  function handleMainChange(v) {
    setMainClass(v)
    setSubclass('')
  }

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
    if (!mainClass || !subclass) {
      setError('Choose a Locarno main class and subclass.')
      return
    }

    setGenerating(true)
    try {
      const form = new FormData()
      VIEWS.forEach((v) => {
        if (views[v]) form.append(v, views[v])
      })
      if (genTitle.trim()) form.append('title', genTitle.trim())
      form.append('locarno_main_class', mainClass)
      form.append('locarno_subclass', subclass)
      form.append('quality', quality)
      form.append('detail', detail)

      const res = await apiFetch('/api/patents/generate', { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Generation request failed')
      }

      setViews({})
      setGenTitle('')
      setMainClass('')
      setSubclass('')
      navigate('/browse')
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  function onWizardComplete() {
    navigate('/browse')
  }

  return (
    <div className="page">
      <div className="upload-page-header">
        <h1>Register a new design</h1>
        <p>
          Upload a 3D-model ZIP under the Locarno classification, or generate
          a model from 1–4 reference photos.
        </p>
      </div>

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
          <div className="zip-launcher">
            <p className="zip-launcher-hint">
              Submit a design for registration: enter the design name and Locarno
              classification, then upload its 3D-model ZIP.
            </p>
            <button
              type="button"
              className="btn-primary"
              onClick={() => { setError(null); setWizardOpen(true) }}
            >
              Register a design
            </button>
          </div>
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

            <div className="mv-locarno">
              <label className="wizard-field">
                <span>Locarno main class</span>
                <Combobox
                  options={mainOptions}
                  value={mainClass}
                  onChange={handleMainChange}
                  placeholder={treeLoading ? 'Loading…' : 'Type to filter, e.g. furniture, foodstuffs'}
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

            <div className="mv-presets">
              <div className="mv-preset-group">
                <span className="mv-preset-label">Quality</span>
                <div className="mv-preset-options">
                  {QUALITY_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={`mv-preset-chip ${quality === opt.value ? 'active' : ''}`}
                      title={opt.hint}
                    >
                      <input
                        type="radio"
                        name="quality"
                        value={opt.value}
                        checked={quality === opt.value}
                        onChange={() => setQuality(opt.value)}
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
              </div>
              <div className="mv-preset-group">
                <span className="mv-preset-label">Detail</span>
                <div className="mv-preset-options">
                  {DETAIL_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={`mv-preset-chip ${detail === opt.value ? 'active' : ''}`}
                      title={opt.hint}
                    >
                      <input
                        type="radio"
                        name="detail"
                        value={opt.value}
                        checked={detail === opt.value}
                        onChange={() => setDetail(opt.value)}
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="mv-title-row">
              <input
                type="text"
                placeholder="Name for this model (optional)"
                value={genTitle}
                onChange={(e) => setGenTitle(e.target.value)}
              />
              <button
                type="submit"
                disabled={generating || !views.front || !mainClass || !subclass}
              >
                {generating ? 'Starting...' : 'Generate 3D Model'}
              </button>
            </div>
          </form>
        )}

        {error && <p className="error">{error}</p>}
      </section>

      <RegistrationWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onComplete={onWizardComplete}
      />
    </div>
  )
}
