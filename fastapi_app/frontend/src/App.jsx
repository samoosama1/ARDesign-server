import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { AuthProvider } from './hooks/useAuth'
import ProtectedRoute from './components/ProtectedRoute'
import NavBar from './components/NavBar'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import LandingPage from './pages/LandingPage'
import BrowsePage from './pages/BrowsePage'
import UploadPage from './pages/UploadPage'

function AuthedLayout() {
  return (
    <>
      <NavBar />
      <Outlet />
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            element={
              <ProtectedRoute>
                <AuthedLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<LandingPage />} />
            <Route path="/browse" element={<BrowsePage />} />
            <Route path="/upload" element={<UploadPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
