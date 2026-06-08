import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

// Module-scoped cache: the Locarno tree is constant for the session.
let cache = null
let inflight = null

// Call after an admin edits the Locarno tree so Browse/Upload refetch the
// updated classification instead of serving the stale session copy.
export function clearLocarnoTreeCache() {
  cache = null
  inflight = null
}

export function loadLocarnoTree() {
  if (cache) return Promise.resolve(cache)
  if (inflight) return inflight
  inflight = apiFetch('/api/locarno')
    .then(async (res) => {
      if (!res.ok) throw new Error(`Failed to load Locarno tree (${res.status})`)
      const data = await res.json()
      cache = data
      return data
    })
    .finally(() => { inflight = null })
  return inflight
}

export function useLocarnoTree(enabled = true) {
  const [tree, setTree] = useState(cache)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!enabled || tree) return
    setLoading(true)
    loadLocarnoTree()
      .then((t) => { setTree(t); setError(null) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [enabled, tree])

  return { tree, loading, error }
}
