import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'

async function readError(res, fallback) {
  try {
    const body = await res.json()
    return body.detail || fallback
  } catch {
    return fallback
  }
}

export default function AdminUsers() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async (search) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (search) params.set('q', search)
      const res = await apiFetch(`/api/admin/users?${params}`)
      if (!res.ok) throw new Error(await readError(res, 'Failed to load users'))
      setUsers(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load('') }, [load])

  async function patchUser(id, body, label) {
    if (!window.confirm(`${label}?`)) return
    setBusyId(id)
    setError(null)
    try {
      const res = await apiFetch(`/api/admin/users/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(await readError(res, 'Update failed'))
      await load(q)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusyId(null)
    }
  }

  async function deleteUser(u) {
    if (!window.confirm(
      `Delete user "${u.username}" and all ${u.patent_count} of their design(s)? This cannot be undone.`
    )) return
    setBusyId(u.id)
    setError(null)
    try {
      const res = await apiFetch(`/api/admin/users/${u.id}`, { method: 'DELETE' })
      if (!res.ok && res.status !== 204) throw new Error(await readError(res, 'Delete failed'))
      await load(q)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="admin-section">
      <form
        className="admin-search"
        onSubmit={(e) => { e.preventDefault(); load(q) }}
      >
        <input
          type="text"
          placeholder="Search username or email…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button type="submit">Search</button>
      </form>

      {error && <div className="admin-error">{error}</div>}
      {loading ? (
        <div className="loading">Loading…</div>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th><th>Username</th><th>Email</th><th>Role</th>
              <th>Active</th><th>Designs</th><th>Joined</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isSelf = u.id === me?.id
              const disabled = busyId === u.id || isSelf
              return (
                <tr key={u.id}>
                  <td>{u.id}</td>
                  <td>{u.username}{isSelf && <span className="admin-badge">you</span>}</td>
                  <td>{u.email}</td>
                  <td>{u.role}</td>
                  <td>{u.is_active ? 'yes' : 'no'}</td>
                  <td>{u.patent_count}</td>
                  <td>{new Date(u.date_joined).toLocaleDateString()}</td>
                  <td className="admin-row-actions">
                    {u.role === 'ADMIN' ? (
                      <button disabled={disabled}
                        onClick={() => patchUser(u.id, { role: 'USER' }, `Demote ${u.username} to USER`)}>
                        Demote
                      </button>
                    ) : (
                      <button disabled={disabled}
                        onClick={() => patchUser(u.id, { role: 'ADMIN' }, `Promote ${u.username} to ADMIN`)}>
                        Promote
                      </button>
                    )}
                    <button disabled={disabled}
                      onClick={() => patchUser(u.id, { is_active: !u.is_active },
                        `${u.is_active ? 'Deactivate' : 'Activate'} ${u.username}`)}>
                      {u.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button className="btn-delete" disabled={disabled} onClick={() => deleteUser(u)}>
                      Delete
                    </button>
                  </td>
                </tr>
              )
            })}
            {users.length === 0 && (
              <tr><td colSpan={8} className="admin-empty">No users.</td></tr>
            )}
          </tbody>
        </table>
      )}
    </section>
  )
}
