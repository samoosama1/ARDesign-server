import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../api/client'
import { clearLocarnoTreeCache } from '../../hooks/useLocarnoTree'

async function readError(res, fallback) {
  try {
    const body = await res.json()
    return body.detail || fallback
  } catch {
    return fallback
  }
}

export default function AdminLocarno() {
  const [tree, setTree] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState({})

  // Inline edit + add form state.
  const [editing, setEditing] = useState(null) // { kind: 'main'|'sub', value }
  const [editLabel, setEditLabel] = useState('')
  const [newMain, setNewMain] = useState({ value: '', number: '', label: '' })
  const [newSub, setNewSub] = useState({}) // keyed by main value -> { value, label }

  // Always fetch fresh (bypassing the session cache) so the editor reflects the DB.
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch('/api/locarno')
      if (!res.ok) throw new Error(await readError(res, 'Failed to load Locarno tree'))
      setTree(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Run a mutation, then refresh the editor and invalidate the app-wide cache.
  async function mutate(method, url, body) {
    setError(null)
    try {
      const res = await apiFetch(url, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      })
      if (!res.ok && res.status !== 204) throw new Error(await readError(res, 'Operation failed'))
      clearLocarnoTreeCache()
      await load()
      return true
    } catch (e) {
      setError(e.message)
      return false
    }
  }

  function startEdit(kind, value, label) {
    setEditing({ kind, value })
    setEditLabel(label)
  }

  async function saveEdit() {
    const url = editing.kind === 'main'
      ? `/api/admin/locarno/main-classes/${encodeURIComponent(editing.value)}`
      : `/api/admin/locarno/subclasses/${encodeURIComponent(editing.value)}`
    if (await mutate('PATCH', url, { label: editLabel.trim() })) setEditing(null)
  }

  async function reorderMains(index, dir) {
    const values = tree.main_classes.map((m) => m.value)
    const j = index + dir
    if (j < 0 || j >= values.length) return
    ;[values[index], values[j]] = [values[j], values[index]]
    await mutate('PUT', '/api/admin/locarno/main-classes/order', { ordered_values: values })
  }

  async function reorderSubs(mainValue, index, dir) {
    const values = (tree.subclasses_by_main[mainValue] || []).map((s) => s.value)
    const j = index + dir
    if (j < 0 || j >= values.length) return
    ;[values[index], values[j]] = [values[j], values[index]]
    await mutate('PUT',
      `/api/admin/locarno/main-classes/${encodeURIComponent(mainValue)}/subclasses/order`,
      { ordered_values: values })
  }

  async function addMain(e) {
    e.preventDefault()
    const number = parseInt(newMain.number, 10)
    if (!newMain.value.trim() || !newMain.label.trim() || Number.isNaN(number)) {
      setError('Main class needs a value, a numeric number, and a label.')
      return
    }
    if (await mutate('POST', '/api/admin/locarno/main-classes', {
      value: newMain.value.trim(), number, label: newMain.label.trim(),
    })) setNewMain({ value: '', number: '', label: '' })
  }

  async function addSub(e, mainValue) {
    e.preventDefault()
    const draft = newSub[mainValue] || {}
    if (!draft.value?.trim() || !draft.label?.trim()) {
      setError('Subclass needs a value and a label.')
      return
    }
    if (await mutate('POST', '/api/admin/locarno/subclasses', {
      value: draft.value.trim(), main_class_value: mainValue, label: draft.label.trim(),
    })) setNewSub((prev) => ({ ...prev, [mainValue]: { value: '', label: '' } }))
  }

  if (loading && !tree) return <div className="loading">Loading…</div>

  const mains = tree?.main_classes || []

  return (
    <section className="admin-section admin-locarno">
      {error && <div className="admin-error">{error}</div>}

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
          const subs = tree.subclasses_by_main[m.value] || []
          const isOpen = !!expanded[m.value]
          const subDraft = newSub[m.value] || { value: '', label: '' }
          return (
            <li key={m.value} className="locarno-main">
              <div className="locarno-row">
                <button className="locarno-toggle"
                  onClick={() => setExpanded((p) => ({ ...p, [m.value]: !p[m.value] }))}>
                  {isOpen ? '▾' : '▸'}
                </button>
                <span className="locarno-num">{m.number}</span>
                {editing?.kind === 'main' && editing.value === m.value ? (
                  <>
                    <input className="locarno-edit" value={editLabel}
                      onChange={(e) => setEditLabel(e.target.value)} autoFocus />
                    <button onClick={saveEdit}>Save</button>
                    <button onClick={() => setEditing(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <span className="locarno-label">{m.label}</span>
                    <code className="locarno-value">{m.value}</code>
                    <span className="locarno-actions">
                      <button onClick={() => reorderMains(i, -1)} disabled={i === 0} title="Move up">↑</button>
                      <button onClick={() => reorderMains(i, 1)} disabled={i === mains.length - 1} title="Move down">↓</button>
                      <button onClick={() => startEdit('main', m.value, m.label)}>Rename</button>
                      <button className="btn-delete"
                        onClick={() => mutate('DELETE', `/api/admin/locarno/main-classes/${encodeURIComponent(m.value)}`)}>
                        Delete
                      </button>
                    </span>
                  </>
                )}
              </div>

              {isOpen && (
                <ul className="locarno-subs">
                  {subs.map((s, j) => (
                    <li key={s.value} className="locarno-row locarno-sub">
                      {editing?.kind === 'sub' && editing.value === s.value ? (
                        <>
                          <input className="locarno-edit" value={editLabel}
                            onChange={(e) => setEditLabel(e.target.value)} autoFocus />
                          <button onClick={saveEdit}>Save</button>
                          <button onClick={() => setEditing(null)}>Cancel</button>
                        </>
                      ) : (
                        <>
                          <span className="locarno-label">{s.label}</span>
                          <code className="locarno-value">{s.value}</code>
                          <span className="locarno-actions">
                            <button onClick={() => reorderSubs(m.value, j, -1)} disabled={j === 0} title="Move up">↑</button>
                            <button onClick={() => reorderSubs(m.value, j, 1)} disabled={j === subs.length - 1} title="Move down">↓</button>
                            <button onClick={() => startEdit('sub', s.value, s.label)}>Rename</button>
                            <button className="btn-delete"
                              onClick={() => mutate('DELETE', `/api/admin/locarno/subclasses/${encodeURIComponent(s.value)}`)}>
                              Delete
                            </button>
                          </span>
                        </>
                      )}
                    </li>
                  ))}
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
    </section>
  )
}
