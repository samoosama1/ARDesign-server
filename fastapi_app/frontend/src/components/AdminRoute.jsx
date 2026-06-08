import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

// Mirrors ProtectedRoute, but additionally requires the ADMIN role. Non-admins
// (and anonymous visitors) are bounced to the landing page rather than /login,
// so the admin section's existence isn't advertised to ordinary users.
export default function AdminRoute({ children }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="loading">Loading...</div>
  if (!user || user.role !== 'ADMIN') return <Navigate to="/" replace />
  return children
}
