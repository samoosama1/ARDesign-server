import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
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

// ---- normalization ----------------------------------------------------------

// The PUT /tree endpoint reads sort by *list position*, so the working tree is
// kept as ordered arrays the whole time. Identity is `value` (primary key).
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

// Two arrays "share order" iff their common items appear in the same relative
// sequence. Used to detect reorder independently of inserts/deletes.
function sameOrderOfCommon(a, b) {
  const aSet = new Set(a)
  const bSet = new Set(b)
  const ca = a.filter((v) => bSet.has(v))
  const cb = b.filter((v) => aSet.has(v))
  return ca.join('|') === cb.join('|')
}

// ---- structured diff --------------------------------------------------------
// Built once per draft change and consumed by both the on-page Changes section
// and the save-confirm dialog. Each change has enough info for per-change undo.

function structuredDiff(orig, draft) {
  if (!orig || !draft) return { changes: [], count: 0, removalCount: 0 }
  const changes = []
  const oM = byValue(orig.mains)
  const dM = byValue(draft.mains)
  const oIndex = new Map(orig.mains.map((m, i) => [m.value, i]))

  // 1. Reordered mains (single change, affects the whole list)
  if (!sameOrderOfCommon(orig.mains.map((m) => m.value), draft.mains.map((m) => m.value))) {
    changes.push({
      kind: 'reorderMains',
      newOrder: draft.mains.filter((m) => oM[m.value]).map((m) => ({ number: m.number, label: m.label })),
    })
  }

  // 2. Per-main changes, in draft order so the list reads top-to-bottom like the tree
  draft.mains.forEach((m) => {
    const o = oM[m.value]
    if (!o) {
      // Whole new class — its subs are listed inside this block, no separate addSub events.
      changes.push({
        kind: 'addMain',
        value: m.value,
        number: m.number,
        label: m.label,
        subs: m.subclasses.map((s) => ({ value: s.value, label: s.label })),
      })
      return
    }
    if (o.label !== m.label || o.number !== m.number) {
      changes.push({
        kind: 'editMain',
        value: m.value,
        before: { number: o.number, label: o.label },
        after: { number: m.number, label: m.label },
      })
    }
    // sub-level diff for this surviving main
    const oS = byValue(o.subclasses)
    const dS = byValue(m.subclasses)
    m.subclasses.forEach((s) => {
      const os = oS[s.value]
      if (!os) changes.push({ kind: 'addSub', mainValue: m.value, mainLabel: m.label, value: s.value, label: s.label })
      else if (os.label !== s.label)
        changes.push({ kind: 'editSub', mainValue: m.value, mainLabel: m.label, value: s.value, before: os.label, after: s.label })
    })
    o.subclasses.forEach((s) => {
      if (!dS[s.value])
        changes.push({ kind: 'removeSub', mainValue: m.value, mainLabel: m.label, value: s.value, label: s.label })
    })
    if (!sameOrderOfCommon(o.subclasses.map((s) => s.value), m.subclasses.map((s) => s.value))) {
      changes.push({
        kind: 'reorderSubs',
        mainValue: m.value,
        mainLabel: m.label,
        newOrder: m.subclasses.filter((s) => oS[s.value]).map((s) => s.label),
      })
    }
  })

  // 3. Removed mains, at the bottom of the list (most destructive — easy to spot)
  orig.mains.forEach((m) => {
    if (!dM[m.value])
      changes.push({
        kind: 'removeMain',
        value: m.value,
        number: m.number,
        label: m.label,
        subs: m.subclasses.map((s) => ({ value: s.value, label: s.label })),
        originalIndex: oIndex.get(m.value),
      })
  })

  const removalCount = changes.filter((c) => c.kind === 'removeMain' || c.kind === 'removeSub').length
  return { changes, count: changes.length, removalCount }
}

// Returns a map: rowKey → 'add' | 'edit' for the small dot on the tree row.
// (Reorder dots would be ambiguous per-row, so reorder lives only in the
// Changes section, not on individual rows.)
function buildRowMarkers(diff) {
  const markers = {}
  diff.changes.forEach((c) => {
    if (c.kind === 'addMain') markers[`m:${c.value}`] = 'add'
    if (c.kind === 'editMain') markers[`m:${c.value}`] = 'edit'
    if (c.kind === 'addSub') markers[`s:${c.value}`] = 'add'
    if (c.kind === 'editSub') markers[`s:${c.value}`] = 'edit'
  })
  return markers
}

// ---- change-block renderer (used on-page AND in the save dialog) ------------

function ChangeBlock({ change, onUndo }) {
  const { kind } = change
  let kindLabel = ''
  let body = null
  let groupKind = 'edit'

  if (kind === 'addMain') {
    groupKind = 'add'
    kindLabel = 'Added class'
    body = (
      <>
        <strong>{change.number}</strong>  {change.label}  <code>{change.value}</code>
        {change.subs.length > 0 && (
          <ul>
            {change.subs.map((s) => (
              <li key={s.value}>{s.label} <code>{s.value}</code></li>
            ))}
          </ul>
        )}
      </>
    )
  } else if (kind === 'removeMain') {
    groupKind = 'remove'
    kindLabel = 'Removed class'
    body = (
      <>
        <strong>{change.number}</strong>  <span className="from">{change.label}</span>  <code>{change.value}</code>
        {change.subs.length > 0 && (
          <>
            <div style={{ marginTop: '0.3rem', color: 'var(--text-muted)' }}>
              Also removes {change.subs.length} subclass{change.subs.length === 1 ? '' : 'es'}:
            </div>
            <ul>
              {change.subs.map((s) => (
                <li key={s.value}><span className="from">{s.label}</span></li>
              ))}
            </ul>
          </>
        )}
      </>
    )
  } else if (kind === 'editMain') {
    groupKind = 'edit'
    kindLabel = 'Edited class'
    body = (
      <>
        {change.before.label !== change.after.label && (
          <div><span className="from">{change.before.label}</span><span className="arrow">→</span><span className="to">{change.after.label}</span></div>
        )}
        {change.before.number !== change.after.number && (
          <div>Number: <span className="from">{change.before.number}</span><span className="arrow">→</span><span className="to">{change.after.number}</span></div>
        )}
        <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}><code>{change.value}</code></div>
      </>
    )
  } else if (kind === 'addSub') {
    groupKind = 'add'
    kindLabel = `Added subclass in ${change.mainLabel}`
    body = <>{change.label}  <code>{change.value}</code></>
  } else if (kind === 'removeSub') {
    groupKind = 'remove'
    kindLabel = `Removed subclass from ${change.mainLabel}`
    body = <><span className="from">{change.label}</span>  <code>{change.value}</code></>
  } else if (kind === 'editSub') {
    groupKind = 'edit'
    kindLabel = `Renamed subclass in ${change.mainLabel}`
    body = (
      <>
        <span className="from">{change.before}</span><span className="arrow">→</span><span className="to">{change.after}</span>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}><code>{change.value}</code></div>
      </>
    )
  } else if (kind === 'reorderMains') {
    groupKind = 'reorder'
    kindLabel = 'Reordered main classes'
    body = (
      <>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginBottom: '0.25rem' }}>New order:</div>
        <div>{change.newOrder.map((m) => `${m.number} ${m.label}`).join(' · ')}</div>
      </>
    )
  } else if (kind === 'reorderSubs') {
    groupKind = 'reorder'
    kindLabel = `Reordered subclasses in ${change.mainLabel}`
    body = (
      <>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginBottom: '0.25rem' }}>New order:</div>
        <div>{change.newOrder.join(' · ')}</div>
      </>
    )
  }

  return (
    <div className={`locarno-change-block kind-${groupKind}`}>
      <div className="locarno-change-body">
        <div className="locarno-change-kind">{kindLabel}</div>
        {body}
      </div>
      {onUndo && <button className="locarno-undo" onClick={onUndo}>Undo</button>}
    </div>
  )
}

// ---- component --------------------------------------------------------------

export default function AdminLocarno() {
  const [original, setOriginal] = useState(null)
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [expanded, setExpanded] = useState({})
  const [selected, setSelected] = useState(null) // { kind:'main'|'sub', mainValue, value }
  const [mode, setMode] = useState('view') // 'view' | 'rename' | 'addSub'
  const [editLabel, setEditLabel] = useState('')
  const [newSub, setNewSub] = useState({ value: '', label: '' })

  const [addingMain, setAddingMain] = useState(false)
  const [newMain, setNewMain] = useState({ value: '', number: '', label: '' })

  const [showSave, setShowSave] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await apiFetch('/api/locarno')
      if (!res.ok) throw new Error(await readError(res, 'Failed to load Locarno tree'))
      const normalized = fromApi(await res.json())
      setOriginal(normalized)
      setDraft(clone(normalized))
      setSelected(null); setMode('view')
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const diff = useMemo(() => structuredDiff(original, draft), [original, draft])
  const dirty = diff.count > 0
  const markers = useMemo(() => buildRowMarkers(diff), [diff])

  const editDraft = useCallback((mutator) => {
    setDraft((prev) => { const next = clone(prev); mutator(next); return next })
  }, [])

  // ---- low-level operations ------------------------------------------------

  const findMain = (t, v) => t.mains.find((m) => m.value === v)

  function moveMain(value, dir) {
    editDraft((t) => {
      const i = t.mains.findIndex((m) => m.value === value)
      const j = i + dir
      if (i < 0 || j < 0 || j >= t.mains.length) return
      ;[t.mains[i], t.mains[j]] = [t.mains[j], t.mains[i]]
    })
  }
  function moveSub(mainValue, value, dir) {
    editDraft((t) => {
      const m = findMain(t, mainValue); if (!m) return
      const i = m.subclasses.findIndex((s) => s.value === value)
      const j = i + dir
      if (i < 0 || j < 0 || j >= m.subclasses.length) return
      ;[m.subclasses[i], m.subclasses[j]] = [m.subclasses[j], m.subclasses[i]]
    })
  }
  function removeSelected() {
    if (!selected) return
    if (selected.kind === 'main') {
      editDraft((t) => { t.mains = t.mains.filter((m) => m.value !== selected.value) })
    } else {
      editDraft((t) => {
        const m = findMain(t, selected.mainValue)
        if (m) m.subclasses = m.subclasses.filter((s) => s.value !== selected.value)
      })
    }
    setSelected(null); setMode('view')
  }
  function commitRename() {
    const label = editLabel.trim()
    if (!label || !selected) return
    editDraft((t) => {
      if (selected.kind === 'main') {
        const m = findMain(t, selected.value); if (m) m.label = label
      } else {
        const m = findMain(t, selected.mainValue)
        const s = m?.subclasses.find((x) => x.value === selected.value)
        if (s) s.label = label
      }
    })
    setMode('view')
  }
  function commitAddSub() {
    const value = newSub.value.trim()
    const label = newSub.label.trim()
    if (!value || !label || !selected || selected.kind !== 'main') return
    if (draft.mains.some((m) => m.subclasses.some((s) => s.value === value))) {
      setError(`Subclass value “${value}” already exists.`); return
    }
    editDraft((t) => { const m = findMain(t, selected.value); if (m) m.subclasses.push({ value, label }) })
    setMode('view'); setNewSub({ value: '', label: '' })
  }
  function commitAddMain() {
    const value = newMain.value.trim()
    const label = newMain.label.trim()
    const number = parseInt(newMain.number, 10)
    if (!value || !label || Number.isNaN(number)) {
      setError('A main class needs a value, a numeric number, and a label.'); return
    }
    if (draft.mains.some((m) => m.value === value)) { setError(`Main class “${value}” already exists.`); return }
    if (draft.mains.some((m) => m.number === number)) { setError(`Main class number ${number} is already used.`); return }
    editDraft((t) => { t.mains.push({ value, number, label, subclasses: [] }) })
    setAddingMain(false); setNewMain({ value: '', number: '', label: '' })
    setExpanded((p) => ({ ...p, [value]: true }))
    setSelected({ kind: 'main', value }); setMode('view')
    setError(null)
  }

  // ---- per-change undo -----------------------------------------------------

  function undoChange(c) {
    setError(null)
    if (c.kind === 'addMain') {
      editDraft((t) => { t.mains = t.mains.filter((m) => m.value !== c.value) })
    } else if (c.kind === 'removeMain') {
      editDraft((t) => {
        const restored = { value: c.value, number: c.number, label: c.label, subclasses: c.subs.map((s) => ({ ...s })) }
        const at = Math.min(c.originalIndex ?? t.mains.length, t.mains.length)
        t.mains.splice(at, 0, restored)
      })
    } else if (c.kind === 'editMain') {
      editDraft((t) => {
        const m = findMain(t, c.value); if (!m) return
        m.label = c.before.label; m.number = c.before.number
      })
    } else if (c.kind === 'addSub') {
      editDraft((t) => {
        const m = findMain(t, c.mainValue); if (!m) return
        m.subclasses = m.subclasses.filter((s) => s.value !== c.value)
      })
    } else if (c.kind === 'removeSub') {
      // restore at end of parent's sub list (good enough — exact original index isn't tracked here)
      editDraft((t) => {
        const m = findMain(t, c.mainValue); if (!m) return
        m.subclasses.push({ value: c.value, label: c.label })
      })
    } else if (c.kind === 'editSub') {
      editDraft((t) => {
        const m = findMain(t, c.mainValue); if (!m) return
        const s = m.subclasses.find((x) => x.value === c.value); if (s) s.label = c.before
      })
    } else if (c.kind === 'reorderMains') {
      // Restore the original order of mains that exist in both; append draft-only mains after.
      editDraft((t) => {
        const origOrder = original.mains.map((m) => m.value)
        const draftSet = new Set(t.mains.map((m) => m.value))
        const restored = []
        origOrder.forEach((v) => { if (draftSet.has(v)) restored.push(findMain(t, v)) })
        t.mains.forEach((m) => { if (!original.mains.find((om) => om.value === m.value)) restored.push(m) })
        t.mains = restored
      })
    } else if (c.kind === 'reorderSubs') {
      editDraft((t) => {
        const m = findMain(t, c.mainValue); if (!m) return
        const om = original.mains.find((x) => x.value === c.mainValue)
        if (!om) return
        const draftSet = new Set(m.subclasses.map((s) => s.value))
        const restored = []
        om.subclasses.forEach((s) => { if (draftSet.has(s.value)) restored.push(m.subclasses.find((x) => x.value === s.value)) })
        m.subclasses.forEach((s) => { if (!om.subclasses.find((os) => os.value === s.value)) restored.push(s) })
        m.subclasses = restored
      })
    }
  }

  // ---- selection helpers ---------------------------------------------------

  function selectMain(value) {
    if (selected?.kind === 'main' && selected.value === value && mode === 'view') return
    setSelected({ kind: 'main', value }); setMode('view')
  }
  function selectSub(mainValue, value) {
    setSelected({ kind: 'sub', mainValue, value }); setMode('view')
  }
  // The ⋮ button toggles the action band — clicking it again closes it.
  // (Clicking the row body only selects; never deselects, to avoid surprises.)
  function toggleMain(value, e) {
    e?.stopPropagation()
    if (selected?.kind === 'main' && selected.value === value) {
      setSelected(null); setMode('view')
    } else {
      setSelected({ kind: 'main', value }); setMode('view')
    }
  }
  function toggleSub(mainValue, value, e) {
    e?.stopPropagation()
    if (selected?.kind === 'sub' && selected.value === value && selected.mainValue === mainValue) {
      setSelected(null); setMode('view')
    } else {
      setSelected({ kind: 'sub', mainValue, value }); setMode('view')
    }
  }
  function toggle(value, e) {
    e?.stopPropagation()
    setExpanded((p) => ({ ...p, [value]: !p[value] }))
  }

  // ---- save flow -----------------------------------------------------------

  function discard() {
    setDraft(clone(original))
    setSelected(null); setMode('view'); setAddingMain(false)
    setNewMain({ value: '', number: '', label: '' }); setNewSub({ value: '', label: '' })
    setError(null)
  }
  async function commit() {
    setSaving(true); setSaveError(null)
    try {
      const res = await apiFetch('/api/admin/locarno/tree', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(toPayload(draft)),
      })
      if (!res.ok) throw new Error(await readError(res, 'Save failed'))
      clearLocarnoTreeCache()
      setShowSave(false)
      await load()
    } catch (e) { setSaveError(e.message) }
    finally { setSaving(false) }
  }

  if (loading && !draft) return <div className="loading">Loading…</div>

  const mains = draft?.mains || []

  return (
    <section className="admin-section admin-locarno">
      {error && <div className="admin-error">{error}</div>}

      {/* Toolbar above the tree — adding a class lives here, not inside rows. */}
      <div className="locarno-toolbar">
        {addingMain ? (
          <form className="locarno-inline-form" onSubmit={(e) => { e.preventDefault(); commitAddMain() }}>
            <input name="value" placeholder="value (e.g. SINIF_99)" value={newMain.value}
              onChange={(e) => setNewMain({ ...newMain, value: e.target.value })} autoFocus />
            <input name="number" type="number" placeholder="no." value={newMain.number}
              onChange={(e) => setNewMain({ ...newMain, number: e.target.value })} />
            <input name="label" placeholder="label" value={newMain.label}
              onChange={(e) => setNewMain({ ...newMain, label: e.target.value })} />
            <button type="submit" className="btn-primary">Add</button>
            <button type="button" className="btn-secondary" onClick={() => { setAddingMain(false); setError(null) }}>Cancel</button>
          </form>
        ) : (
          <button className="btn-link" onClick={() => setAddingMain(true)}>+ Add main class</button>
        )}
      </div>

      {/* Two-column workspace: tree on the left, sticky changes rail on the right
          so admins see the diff while editing instead of scrolling for it. */}
      <div className="locarno-workspace">
      <div className="locarno-tree-col">

      {/* The tree — clean rows, no per-row buttons. Click to select. */}
      <ul className="locarno-tree">
        {mains.map((m) => {
          const mainSelected = selected?.kind === 'main' && selected.value === m.value
          const isOpen = !!expanded[m.value]
          const marker = markers[`m:${m.value}`]
          return (
            <Fragment key={m.value}>
              <li
                className={`locarno-row${mainSelected ? ' is-selected' : ''}`}
                onClick={() => selectMain(m.value)}
              >
                <button className="locarno-toggle" onClick={(e) => toggle(m.value, e)} aria-label="expand">
                  {isOpen ? '▾' : '▸'}
                </button>
                <span className="locarno-num">{m.number}</span>
                <span className="locarno-label">{m.label}</span>
                <span style={{ display: 'flex', alignItems: 'center' }}>
                  <code className="locarno-value">{m.value}</code>
                  {marker && <span className={`locarno-change-dot is-${marker}`} title={`${marker}ed`} />}
                </span>
                <button
                  className={`locarno-row-actions-btn${mainSelected ? ' is-open' : ''}`}
                  onClick={(e) => toggleMain(m.value, e)}
                  aria-label={mainSelected ? 'Close actions' : 'Show actions'}
                  title={mainSelected ? 'Close actions' : 'Show actions'}
                >
                  {mainSelected ? '✕' : '⋮'}
                </button>
              </li>

              {mainSelected && (
                <li className="locarno-action-band">
                  {mode === 'rename' ? (
                    <>
                      <input value={editLabel} autoFocus onChange={(e) => setEditLabel(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setMode('view') }} />
                      <button onClick={commitRename}>Save</button>
                      <button onClick={() => setMode('view')}>Cancel</button>
                    </>
                  ) : mode === 'addSub' ? (
                    <>
                      <input placeholder="subclass value" value={newSub.value} autoFocus
                        onChange={(e) => setNewSub({ ...newSub, value: e.target.value })} />
                      <input placeholder="subclass label" value={newSub.label}
                        onChange={(e) => setNewSub({ ...newSub, label: e.target.value })}
                        onKeyDown={(e) => { if (e.key === 'Enter') commitAddSub(); if (e.key === 'Escape') setMode('view') }} />
                      <button onClick={commitAddSub}>Add</button>
                      <button onClick={() => setMode('view')}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <button onClick={() => { setEditLabel(m.label); setMode('rename') }}>Rename</button>
                      <button onClick={() => moveMain(m.value, -1)} disabled={mains.indexOf(m) === 0}>Move up</button>
                      <button onClick={() => moveMain(m.value, +1)} disabled={mains.indexOf(m) === mains.length - 1}>Move down</button>
                      <button onClick={() => { setExpanded((p) => ({ ...p, [m.value]: true })); setNewSub({ value: '', label: '' }); setMode('addSub') }}>+ Add subclass</button>
                      <button className="btn-delete" onClick={removeSelected}>Remove</button>
                    </>
                  )}
                </li>
              )}

              {isOpen && (
                <li>
                  <ul className="locarno-subs">
                    {m.subclasses.map((s, j) => {
                      const subSelected = selected?.kind === 'sub' && selected.mainValue === m.value && selected.value === s.value
                      const subMarker = markers[`s:${s.value}`]
                      return (
                        <Fragment key={s.value}>
                          <li
                            className={`locarno-row locarno-sub${subSelected ? ' is-selected' : ''}`}
                            onClick={() => selectSub(m.value, s.value)}
                          >
                            <span className="locarno-toggle is-leaf" aria-hidden />
                            <span className="locarno-label">{s.label}</span>
                            <span style={{ display: 'flex', alignItems: 'center' }}>
                              <code className="locarno-value">{s.value}</code>
                              {subMarker && <span className={`locarno-change-dot is-${subMarker}`} title={`${subMarker}ed`} />}
                            </span>
                            <button
                              className={`locarno-row-actions-btn${subSelected ? ' is-open' : ''}`}
                              onClick={(e) => toggleSub(m.value, s.value, e)}
                              aria-label={subSelected ? 'Close actions' : 'Show actions'}
                              title={subSelected ? 'Close actions' : 'Show actions'}
                            >
                              {subSelected ? '✕' : '⋮'}
                            </button>
                          </li>
                          {subSelected && (
                            <li className="locarno-action-band is-sub">
                              {mode === 'rename' ? (
                                <>
                                  <input value={editLabel} autoFocus onChange={(e) => setEditLabel(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setMode('view') }} />
                                  <button onClick={commitRename}>Save</button>
                                  <button onClick={() => setMode('view')}>Cancel</button>
                                </>
                              ) : (
                                <>
                                  <button onClick={() => { setEditLabel(s.label); setMode('rename') }}>Rename</button>
                                  <button onClick={() => moveSub(m.value, s.value, -1)} disabled={j === 0}>Move up</button>
                                  <button onClick={() => moveSub(m.value, s.value, +1)} disabled={j === m.subclasses.length - 1}>Move down</button>
                                  <button className="btn-delete" onClick={removeSelected}>Remove</button>
                                </>
                              )}
                            </li>
                          )}
                        </Fragment>
                      )
                    })}
                    {m.subclasses.length === 0 && (
                      <li className="locarno-row locarno-sub" style={{ color: 'var(--text-muted)', cursor: 'default' }}>
                        <span className="locarno-toggle is-leaf" aria-hidden />
                        <span className="locarno-label" style={{ fontStyle: 'italic' }}>No subclasses</span>
                      </li>
                    )}
                  </ul>
                </li>
              )}
            </Fragment>
          )
        })}
        {mains.length === 0 && (
          <li
            className="locarno-row"
            style={{ cursor: 'default', color: 'var(--text-muted)', display: 'block' }}
          >
            No Locarno classes. Use “+ Add main class” to start.
          </li>
        )}
      </ul>

      </div>{/* /locarno-tree-col */}

      {/* Sticky right rail: save controls + diff. Visible while editing,
          so admins see what they've changed without scrolling. */}
      <aside className={`locarno-changes-col${dirty ? ' is-dirty' : ''}`}>
        <header className="locarno-changes-header">
          <div className="locarno-changes-heading">
            <h3>Pending changes</h3>
            <span className="locarno-changes-count">
              {dirty ? `${diff.count} change${diff.count === 1 ? '' : 's'}` : 'none yet'}
            </span>
          </div>
          <div className="locarno-changes-actions">
            <button className="btn-secondary" onClick={discard} disabled={!dirty || saving}>Discard</button>
            <button className="btn-primary" onClick={() => { setSaveError(null); setShowSave(true) }} disabled={!dirty || saving}>
              Save changes
            </button>
          </div>
        </header>

        {dirty ? (
          <div className="locarno-change-list">
            {diff.changes.map((c, i) => (
              <ChangeBlock key={i} change={c} onUndo={() => undoChange(c)} />
            ))}
          </div>
        ) : (
          <div className="locarno-changes-empty">
            Edit the tree and your changes will appear here, one block per change.
          </div>
        )}
      </aside>

      </div>{/* /locarno-workspace */}

      <ConfirmDialog
        open={showSave}
        title="Save these changes?"
        confirmLabel={`Save ${diff.count} change${diff.count === 1 ? '' : 's'}`}
        danger={diff.removalCount > 0}
        busy={saving}
        onConfirm={commit}
        onCancel={() => !saving && setShowSave(false)}
      >
        <p className="confirm-lead">
          These are applied together in one transaction. Nothing is saved unless all of them succeed.
        </p>
        <div className="locarno-change-list">
          {diff.changes.map((c, i) => (
            <ChangeBlock key={i} change={c} /* read-only in dialog: no onUndo */ />
          ))}
        </div>
        {diff.removalCount > 0 && (
          <p className="confirm-warn">
            {diff.removalCount} removal{diff.removalCount === 1 ? '' : 's'} included. A removal is refused if any design still uses that class or subclass.
          </p>
        )}
        {saveError && <div className="admin-error">{saveError}</div>}
      </ConfirmDialog>
    </section>
  )
}
