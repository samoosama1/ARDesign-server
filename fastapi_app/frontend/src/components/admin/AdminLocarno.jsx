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

// True iff the two lists share at least one value but in a different relative order.
function orderChanged(aArr, bArr) {
  const aSet = new Set(aArr)
  const bSet = new Set(bArr)
  const aCommon = aArr.filter((v) => bSet.has(v))
  const bCommon = bArr.filter((v) => aSet.has(v))
  return aCommon.join('|') !== bCommon.join('|')
}

// Compute the human-readable change list shown inside the save dialog.
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
    if (orderChanged(o.subclasses.map((s) => s.value), m.subclasses.map((s) => s.value)))
      out.push({ type: 'reorder', text: `Reorder subclasses in ${m.label}` })
  })

  orig.mains.forEach((m) => {
    if (!dM[m.value])
      out.push({ type: 'remove', text: `Remove class ${m.number} — ${m.label} (and its subclasses)` })
  })

  if (orderChanged(orig.mains.map((m) => m.value), draft.mains.map((m) => m.value)))
    out.push({ type: 'reorder', text: 'Reorder main classes' })

  return out
}

const TYPE_LABEL = { add: 'add', edit: 'edit', remove: 'remove', reorder: 'reorder' }

function DiffList({ changes }) {
  if (!changes.length) return <p className="confirm-lead">No changes.</p>
  return (
    <ul className="locarno-diff-list">
      {changes.map((c, i) => (
        <li key={i} className="locarno-diff-item">
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
  const draftMains = useMemo(() => byValue(draft?.mains), [draft])

  const mainsReordered = useMemo(() => {
    if (!original || !draft) return false
    return orderChanged(original.mains.map((m) => m.value), draft.mains.map((m) => m.value))
  }, [original, draft])

  // Per-main subclass reorder lookup: { mainValue: true }.
  const subsReordered = useMemo(() => {
    const out = {}
    if (!original || !draft) return out
    original.mains.forEach((om) => {
      const dm = draftMains[om.value]
      if (!dm) return
      if (orderChanged(om.subclasses.map((s) => s.value), dm.subclasses.map((s) => s.value)))
        out[om.value] = true
    })
    return out
  }, [original, draft, draftMains])

  // Apply a local edit to the draft (no network).
  const edit = useCallback((mutator) => {
    setDraft((prev) => {
      const next = clone(prev)
      mutator(next)
      return next
    })
  }, [])

  const findMain = (t, v) => t.mains.find((m) => m.value === v)

  function reorderMains(index, dir) {
    edit((t) => {
      const j = index + dir
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
    const ds = newSub[mainValue] || {}
    const value = (ds.value || '').trim()
    const label = (ds.label || '').trim()
    if (!value || !label) {
      setError('Subclass needs a value and a label.')
      return
    }
    if (draft.mains.some((m) => m.subclasses.some((s) => s.value === value))) {
      setError(`Subclass value “${value}” already exists.`)
      return
    }
    edit((t) => {
      const m = findMain(t, mainValue)
      if (m) m.subclasses.push({ value, label })
    })
    setNewSub((p) => ({ ...p, [mainValue]: { value: '', label: '' } }))
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
  const toggle = (v) => setExpanded((p) => ({ ...p, [v]: !p[v] }))

  // ---- row renderers ---------------------------------------------------------

  // Read-only row in the "Saved" panel. Highlight by comparison to draft.
  function SavedMain({ m }) {
    const d = draftMains[m.value]
    const removed = !d
    const labelChanged = d && d.label !== m.label
    const numberChanged = d && d.number !== m.number
    const isOpen = !!expanded[m.value]
    const rowMod = removed ? 'is-removed' : (labelChanged || numberChanged) ? 'is-edited' : ''
    return (
      <li className={`locarno-main ${rowMod}`}>
        <div className="locarno-row">
          <button className="locarno-toggle" onClick={() => toggle(m.value)} aria-label="toggle">
            {isOpen ? '▾' : '▸'}
          </button>
          <span className={`locarno-num ${numberChanged ? 'is-changed' : ''}`}>{m.number}</span>
          <span className={`locarno-label ${labelChanged ? 'is-changed' : ''} ${removed ? 'is-struck' : ''}`}>
            {m.label}
          </span>
          <code className="locarno-value">{m.value}</code>
        </div>
        {isOpen && (
          <ul className="locarno-subs">
            {subsReordered[m.value] && (
              <li className="locarno-row locarno-sub locarno-reorder-note">
                <span className="diff-badge diff-reorder">order changed</span>
              </li>
            )}
            {m.subclasses.map((s) => {
              const ds = d?.subclasses.find((x) => x.value === s.value)
              const subRemoved = !ds
              const subChanged = ds && ds.label !== s.label
              return (
                <li key={s.value} className={`locarno-row locarno-sub ${subRemoved ? 'is-removed' : subChanged ? 'is-edited' : ''}`}>
                  <span className={`locarno-label ${subChanged ? 'is-changed' : ''} ${subRemoved ? 'is-struck' : ''}`}>
                    {s.label}
                  </span>
                  <code className="locarno-value">{s.value}</code>
                </li>
              )
            })}
          </ul>
        )}
      </li>
    )
  }

  // Interactive row in the "Draft" panel.
  function DraftMain({ m, i }) {
    const o = origMains[m.value]
    const isNew = !o
    const labelChanged = o && o.label !== m.label
    const numberChanged = o && o.number !== m.number
    const isOpen = !!expanded[m.value]
    const rowMod = isNew ? 'is-added' : (labelChanged || numberChanged) ? 'is-edited' : ''
    const subDraft = newSub[m.value] || { value: '', label: '' }
    return (
      <li className={`locarno-main ${rowMod}`}>
        <div className="locarno-row">
          <button className="locarno-toggle" onClick={() => toggle(m.value)} aria-label="toggle">
            {isOpen ? '▾' : '▸'}
          </button>
          <span className={`locarno-num ${numberChanged ? 'is-changed' : ''}`}>{m.number}</span>
          {editing?.kind === 'main' && editing.value === m.value ? (
            <>
              <input className="locarno-edit" value={editLabel} autoFocus
                onChange={(e) => setEditLabel(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && saveEdit()} />
              <button className="btn-secondary" onClick={() => saveEdit()}>Done</button>
              <button className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
            </>
          ) : (
            <>
              <span className={`locarno-label ${labelChanged ? 'is-changed' : ''}`}>{m.label}</span>
              <code className="locarno-value">{m.value}</code>
              <span className="locarno-actions">
                <button onClick={() => reorderMains(i, -1)} disabled={i === 0} title="Move up">↑</button>
                <button onClick={() => reorderMains(i, 1)} disabled={i === (draft.mains.length - 1)} title="Move down">↓</button>
                <button onClick={() => startEdit('main', m.value, m.label)}>Rename</button>
                <button className="btn-delete" onClick={() => removeMain(m.value)}>Remove</button>
              </span>
            </>
          )}
        </div>
        {isOpen && (
          <ul className="locarno-subs">
            {subsReordered[m.value] && (
              <li className="locarno-row locarno-sub locarno-reorder-note">
                <span className="diff-badge diff-reorder">order changed</span>
              </li>
            )}
            {m.subclasses.map((s, j) => {
              const os = o?.subclasses.find((x) => x.value === s.value)
              const subNew = !os
              const subEdited = os && os.label !== s.label
              const subMod = subNew ? 'is-added' : subEdited ? 'is-edited' : ''
              return (
                <li key={s.value} className={`locarno-row locarno-sub ${subMod}`}>
                  {editing?.kind === 'sub' && editing.value === s.value ? (
                    <>
                      <input className="locarno-edit" value={editLabel} autoFocus
                        onChange={(e) => setEditLabel(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && saveEdit(m.value)} />
                      <button className="btn-secondary" onClick={() => saveEdit(m.value)}>Done</button>
                      <button className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <span className={`locarno-label ${subEdited ? 'is-changed' : ''}`}>{s.label}</span>
                      <code className="locarno-value">{s.value}</code>
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
            <li className="locarno-row locarno-sub locarno-add-row-li">
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
  }

  if (loading && !draft) return <div className="loading">Loading…</div>

  const removalCount = diff.filter((c) => c.type === 'remove').length

  return (
    <section className="admin-section admin-locarno">
      <div className={`locarno-savebar${dirty ? ' is-dirty' : ''}`}>
        <span className="locarno-savebar-status">
          {dirty
            ? `${diff.length} pending change${diff.length === 1 ? '' : 's'} — not saved yet`
            : 'No pending changes'}
        </span>
        <div className="locarno-savebar-actions">
          <button className="btn-secondary" onClick={discard} disabled={!dirty || saving}>Discard</button>
          <button className="btn-primary" onClick={() => { setSaveError(null); setShowSave(true) }} disabled={!dirty || saving}>
            Save changes
          </button>
        </div>
      </div>

      {error && <div className="admin-error">{error}</div>}

      <div className="locarno-panels">
        {/* SAVED — read-only snapshot of what's currently in the DB */}
        <article className="locarno-panel locarno-panel--saved">
          <header className="locarno-panel-header">
            <h3>Saved</h3>
            <span className="locarno-panel-count">{original?.mains.length ?? 0} classes</span>
            {mainsReordered && <span className="diff-badge diff-reorder">order changed</span>}
          </header>
          <ul className="locarno-tree">
            {(original?.mains || []).map((m) => <SavedMain key={m.value} m={m} />)}
            {(original?.mains || []).length === 0 && <li className="admin-empty">No Locarno classes.</li>}
          </ul>
        </article>

        {/* DRAFT — your working copy. Edits stay here until Save. */}
        <article className="locarno-panel locarno-panel--draft">
          <header className="locarno-panel-header">
            <h3>Draft</h3>
            <span className="locarno-panel-count">{draft?.mains.length ?? 0} classes</span>
            {mainsReordered && <span className="diff-badge diff-reorder">order changed</span>}
          </header>
          <form className="admin-add-row locarno-add-main" onSubmit={addMain}>
            <input placeholder="value (e.g. SINIF_1)" value={newMain.value}
              onChange={(e) => setNewMain({ ...newMain, value: e.target.value })} />
            <input placeholder="number" type="number" value={newMain.number}
              onChange={(e) => setNewMain({ ...newMain, number: e.target.value })} />
            <input placeholder="label" value={newMain.label}
              onChange={(e) => setNewMain({ ...newMain, label: e.target.value })} />
            <button type="submit" className="btn-primary">Add main class</button>
          </form>
          <ul className="locarno-tree">
            {(draft?.mains || []).map((m, i) => <DraftMain key={m.value} m={m} i={i} />)}
            {(draft?.mains || []).length === 0 && <li className="admin-empty">No Locarno classes. Add one above.</li>}
          </ul>
        </article>
      </div>

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
