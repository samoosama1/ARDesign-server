import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../../api/client'
import { clearLocarnoTreeCache } from '../../hooks/useLocarnoTree'
import ConfirmDialog from './ConfirmDialog'

async function readError(res, fallback) {
  try {
    const body = await res.json()
    return body.detail || fallback
  } catch {
    return fallback
  }
}

// ---- shape helpers -----------------------------------------------------------

// Normalize the /api/locarno payload into a flat, editable working tree where
// list order *is* the sort order (the save endpoint reads sort_index from it).
function fromApi(tree) {
  return {
    mains: (tree?.main_classes || []).map((m) => ({
      value: m.value,
      number: m.number,
      label: m.label,
      subclasses: (tree?.subclasses_by_main?.[m.value] || []).map((s) => ({
        value: s.value,
        label: s.label,
      })),
    })),
  }
}

const clone = (x) => JSON.parse(JSON.stringify(x))
const byValue = (arr) => Object.fromEntries((arr || []).map((x) => [x.value, x]))

function toPayload(draft) {
  return {
    main_classes: draft.mains.map((m) => ({
      value: m.value,
      number: m.number,
      label: m.label,
      subclasses: m.subclasses.map((s) => ({ value: s.value, label: s.label })),
    })),
  }
}

// Compute the human-readable change list between the loaded tree and the draft.
function diffTree(orig, draft) {
  if (!orig || !draft) return []
  const out = []
  const oM = byValue(orig.mains)
  const dM = byValue(draft.mains)

  draft.mains.forEach((m) => {
    const o = oM[m.value]
    if (!o) {
      out.push({ type: 'add', text: `Add class ${m.number} — ${m.label}` })
      m.subclasses.forEach((s) =>
        out.push({ type: 'add', text: `Add subclass “${s.label}”`, parent: m.label }))
      return
    }
    if (o.label !== m.label || o.number !== m.number) {
      const bits = []
      if (o.label !== m.label) bits.push(`“${o.label}” → “${m.label}”`)
      if (o.number !== m.number) bits.push(`no. ${o.number} → ${m.number}`)
      out.push({ type: 'edit', text: `Edit class ${bits.join(', ')}` })
    }
    const oS = byValue(o.subclasses)
    const dS = byValue(m.subclasses)
    m.subclasses.forEach((s) => {
      const os = oS[s.value]
      if (!os) out.push({ type: 'add', text: `Add subclass “${s.label}”`, parent: m.label })
      else if (os.label !== s.label)
        out.push({ type: 'edit', text: `Rename subclass “${os.label}” → “${s.label}”`, parent: m.label })
    })
    o.subclasses.forEach((s) => {
      if (!dS[s.value]) out.push({ type: 'remove', text: `Remove subclass “${s.label}”`, parent: m.label })
    })
    const cO = o.subclasses.map((s) => s.value).filter((v) => dS[v])
    const cD = m.subclasses.map((s) => s.value).filter((v) => oS[v])
    if (cO.join('|') !== cD.join('|'))
      out.push({ type: 'reorder', text: `Reorder subclasses in ${m.label}` })
  })

  orig.mains.forEach((m) => {
    if (!dM[m.value])
      out.push({ type: 'remove', text: `Remove class ${m.number} — ${m.label} (and its subclasses)` })
  })

  const cO = orig.mains.map((m) => m.value).filter((v) => dM[v])
  const cD = draft.mains.map((m) => m.value).filter((v) => oM[v])
  if (cO.join('|') !== cD.join('|')) out.push({ type: 'reorder', text: 'Reorder main classes' })

  return out
}

const TYPE_LABEL = { add: 'add', edit: 'edit', remove: 'remove', reorder: 'reorder' }

function DiffList({ changes }) {
  return (
    <ul className="locarno-diff-list">
      {changes.map((c, i) => (
        <li key={i} className={`locarno-diff-item diff-${c.type}`}>
          <span className={`diff-badge diff-${c.type}`}>{TYPE_LABEL[c.type]}</span>
          <span className="diff-text">
            {c.text}
            {c.parent && <span className="diff-parent"> · in {c.parent}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}

// ---- component ---------------------------------------------------------------

export default function AdminLocarno() {
  const [original, setOriginal] = useState(null)
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState({})

  const [editing, setEditing] = useState(null) // { kind: 'main'|'sub', value }
  const [editLabel, setEditLabel] = useState('')
  const [newMain, setNewMain] = useState({ value: '', number: '', label: '' })
  const [newSub, setNewSub] = useState({}) // mainValue -> { value, label }

  const [showSave, setShowSave] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch('/api/locarno')
      if (!res.ok) throw new Error(await readError(res, 'Failed to load Locarno tree'))
      const normalized = fromApi(await res.json())
      setOriginal(normalized)
      setDraft(clone(normalized))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const diff = useMemo(() => diffTree(original, draft), [original, draft])
  const dirty = diff.length > 0
  const origMains = useMemo(() => byValue(original?.mains), [original])

  // Apply a local edit to the draft (no network).
  const edit = useCallback((mutator) => {
    setDraft((prev) => {
      const next = clone(prev)
      mutator(next)
      return next
    })
  }, [])

  function findMain(tree, value) {
    return tree.mains.find((m) => m.value === value)
  }

  function reorderMains(index, dir) {
    const j = index + dir
    edit((t) => {
      if (j < 0 || j >= t.mains.length) return
      ;[t.mains[index], t.mains[j]] = [t.mains[j], t.mains[index]]
    })
  }

  function reorderSubs(mainValue, index, dir) {
    edit((t) => {
      const m = findMain(t, mainValue)
      const j = index + dir
      if (!m || j < 0 || j >= m.subclasses.length) return
      ;[m.subclasses[index], m.subclasses[j]] = [m.subclasses[j], m.subclasses[index]]
    })
  }

  function startEdit(kind, value, label) {
    setEditing({ kind, value })
    setEditLabel(label)
  }

  function saveEdit(mainValue) {
    const label = editLabel.trim()
    if (!label) return
    edit((t) => {
      if (editing.kind === 'main') {
        const m = findMain(t, editing.value)
        if (m) m.label = label
      } else {
        const m = findMain(t, mainValue)
        const s = m?.subclasses.find((x) => x.value === editing.value)
        if (s) s.label = label
      }
    })
    setEditing(null)
  }

  function removeMain(value) {
    edit((t) => { t.mains = t.mains.filter((m) => m.value !== value) })
  }

  function removeSub(mainValue, value) {
    edit((t) => {
      const m = findMain(t, mainValue)
      if (m) m.subclasses = m.subclasses.filter((s) => s.value !== value)
    })
  }

  function addMain(e) {
    e.preventDefault()
    setError(null)
    const value = newMain.value.trim()
    const label = newMain.label.trim()
    const number = parseInt(newMain.number, 10)
    if (!value || !label || Number.isNaN(number)) {
      setError('Main class needs a value, a numeric number, and a label.')
      return
    }
    if (draft.mains.some((m) => m.value === value)) {
      setError(`Main class value “${value}” already exists.`)
      return
    }
    if (draft.mains.some((m) => m.number === number)) {
      setError(`Main class number ${number} is already used.`)
      return
    }
    edit((t) => { t.mains.push({ value, number, label, subclasses: [] }) })
    setExpanded((p) => ({ ...p, [value]: true }))
    setNewMain({ value: '', number: '', label: '' })
  }

  function addSub(e, mainValue) {
    e.preventDefault()
    setError(null)
    const draftSub = newSub[mainValue] || {}
    const value = (draftSub.value || '').trim()
    const label = (draftSub.label || '').trim()
    if (!value || !label) {
      setError('Subclass needs a value and a label.')
      return
    }
    const exists = draft.mains.some((m) => m.subclasses.some((s) => s.value === value))
    if (exists) {
      setError(`Subclass value “${value}” already exists.`)
      return
    }
    edit((t) => {
      const m = findMain(t, mainValue)
      if (m) m.subclasses.push({ value, label })
    })
    setNewSub((prev) => ({ ...prev, [mainValue]: { value: '', label: '' } }))
  }

  function discard() {
    setDraft(clone(original))
    setEditing(null)
    setNewMain({ value: '', number: '', label: '' })
    setNewSub({})
    setError(null)
  }

  async function commit() {
    setSaving(true)
    setSaveError(null)
    try {
      const res = await apiFetch('/api/admin/locarno/tree', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(toPayload(draft)),
      })
      if (!res.ok) throw new Error(await readError(res, 'Save failed'))
      clearLocarnoTreeCache()
      setShowSave(false)
      await load() // reload canonical state from server
    } catch (e) {
      setSaveError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const removalCount = diff.filter((c) => c.type === 'remove').length

  if (loading && !draft) return <div className="loading">Loading…</div>

  const mains = draft?.mains || []

  return (
    <section className="admin-section admin-locarno">
      {/* Sticky action bar: nothing reaches the DB until Save is pressed. */}
      <div className={`locarno-savebar${dirty ? ' is-dirty' : ''}`}>
        <span className="locarno-savebar-status">
          {dirty
            ? `${diff.length} pending change${diff.length === 1 ? '' : 's'} — not saved yet`
            : 'No pending changes'}
        </span>
        <div className="locarno-savebar-actions">
          <button className="btn-secondary" onClick={discard} disabled={!dirty || saving}>
            Discard
          </button>
          <button className="btn-primary" onClick={() => { setSaveError(null); setShowSave(true) }} disabled={!dirty || saving}>
            Save changes
          </button>
        </div>
      </div>

      {error && <div className="admin-error">{error}</div>}

      {dirty && (
        <div className="locarno-diff">
          <h4 className="locarno-diff-title">Pending changes</h4>
          <DiffList changes={diff} />
        </div>
      )}

      <form className="admin-add-row" onSubmit={addMain}>
        <input placeholder="value (e.g. SINIF_1)" value={newMain.value}
          onChange={(e) => setNewMain({ ...newMain, value: e.target.value })} />
        <input placeholder="number" type="number" value={newMain.number}
          onChange={(e) => setNewMain({ ...newMain, number: e.target.value })} />
        <input placeholder="label" value={newMain.label}
          onChange={(e) => setNewMain({ ...newMain, label: e.target.value })} />
        <button type="submit" className="btn-primary">Add main class</button>
      </form>

      <ul className="locarno-tree">
        {mains.map((m, i) => {
          const isOpen = !!expanded[m.value]
          const subDraft = newSub[m.value] || { value: '', label: '' }
          const o = origMains[m.value]
          const isNew = !o
          const isEdited = o && (o.label !== m.label || o.number !== m.number)
          const subsByOrig = byValue(o?.subclasses)
          return (
            <li key={m.value} className={`locarno-main${isNew ? ' is-new' : ''}`}>
              <div className="locarno-row">
                <button className="locarno-toggle"
                  onClick={() => setExpanded((p) => ({ ...p, [m.value]: !p[m.value] }))}>
                  {isOpen ? '▾' : '▸'}
                </button>
                <span className="locarno-num">{m.number}</span>
                {editing?.kind === 'main' && editing.value === m.value ? (
                  <>
                    <input className="locarno-edit" value={editLabel}
                      onChange={(e) => setEditLabel(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && saveEdit()} autoFocus />
                    <button className="btn-secondary" onClick={() => saveEdit()}>Done</button>
                    <button className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <span className="locarno-label">{m.label}</span>
                    <code className="locarno-value">{m.value}</code>
                    {isNew && <span className="diff-badge diff-add">new</span>}
                    {isEdited && <span className="diff-badge diff-edit">edited</span>}
                    <span className="locarno-actions">
                      <button onClick={() => reorderMains(i, -1)} disabled={i === 0} title="Move up">↑</button>
                      <button onClick={() => reorderMains(i, 1)} disabled={i === mains.length - 1} title="Move down">↓</button>
                      <button onClick={() => startEdit('main', m.value, m.label)}>Rename</button>
                      <button className="btn-delete" onClick={() => removeMain(m.value)}>Remove</button>
                    </span>
                  </>
                )}
              </div>

              {isOpen && (
                <ul className="locarno-subs">
                  {m.subclasses.map((s, j) => {
                    const os = subsByOrig[s.value]
                    const subNew = !os
                    const subEdited = os && os.label !== s.label
                    return (
                      <li key={s.value} className={`locarno-row locarno-sub${subNew ? ' is-new' : ''}`}>
                        {editing?.kind === 'sub' && editing.value === s.value ? (
                          <>
                            <input className="locarno-edit" value={editLabel}
                              onChange={(e) => setEditLabel(e.target.value)}
                              onKeyDown={(e) => e.key === 'Enter' && saveEdit(m.value)} autoFocus />
                            <button className="btn-secondary" onClick={() => saveEdit(m.value)}>Done</button>
                            <button className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
                          </>
                        ) : (
                          <>
                            <span className="locarno-label">{s.label}</span>
                            <code className="locarno-value">{s.value}</code>
                            {subNew && <span className="diff-badge diff-add">new</span>}
                            {subEdited && <span className="diff-badge diff-edit">edited</span>}
                            <span className="locarno-actions">
                              <button onClick={() => reorderSubs(m.value, j, -1)} disabled={j === 0} title="Move up">↑</button>
                              <button onClick={() => reorderSubs(m.value, j, 1)} disabled={j === m.subclasses.length - 1} title="Move down">↓</button>
                              <button onClick={() => startEdit('sub', s.value, s.label)}>Rename</button>
                              <button className="btn-delete" onClick={() => removeSub(m.value, s.value)}>Remove</button>
                            </span>
                          </>
                        )}
                      </li>
                    )
                  })}
                  <li className="locarno-row locarno-sub">
                    <form className="admin-add-row" onSubmit={(e) => addSub(e, m.value)}>
                      <input placeholder="subclass value" value={subDraft.value}
                        onChange={(e) => setNewSub((p) => ({ ...p, [m.value]: { ...subDraft, value: e.target.value } }))} />
                      <input placeholder="subclass label" value={subDraft.label}
                        onChange={(e) => setNewSub((p) => ({ ...p, [m.value]: { ...subDraft, label: e.target.value } }))} />
                      <button type="submit">Add subclass</button>
                    </form>
                  </li>
                </ul>
              )}
            </li>
          )
        })}
        {mains.length === 0 && <li className="admin-empty">No Locarno classes.</li>}
      </ul>

      <ConfirmDialog
        open={showSave}
        title="Save Locarno changes?"
        confirmLabel={`Save ${diff.length} change${diff.length === 1 ? '' : 's'}`}
        danger={removalCount > 0}
        busy={saving}
        onConfirm={commit}
        onCancel={() => !saving && setShowSave(false)}
      >
        <p className="confirm-lead">
          These changes are applied together in one transaction. Review before saving:
        </p>
        <DiffList changes={diff} />
        {removalCount > 0 && (
          <p className="confirm-warn">
            {removalCount} removal{removalCount === 1 ? '' : 's'} included. A removal is
            refused if any design still uses that class or subclass.
          </p>
        )}
        {saveError && <div className="admin-error">{saveError}</div>}
      </ConfirmDialog>
    </section>
  )
}
