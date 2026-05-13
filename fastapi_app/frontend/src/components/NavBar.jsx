import { NavLink } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function NavBar() {
  const { user, logout } = useAuth()

  return (
    <header className="nav-bar">
      <NavLink to="/" className="nav-brand" end>
        <span className="nav-brand-mark">AR</span>
        <span className="nav-brand-word">Patent</span>
      </NavLink>

      <nav className="nav-links">
        <NavLink to="/" end className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
          Home
        </NavLink>
        <NavLink to="/browse" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
          Browse
        </NavLink>
        <NavLink to="/upload" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
          Upload
        </NavLink>
      </nav>

      <div className="nav-right">
        <span className="username">{user?.username}</span>
        <button className="btn-logout" onClick={logout}>Sign Out</button>
      </div>
    </header>
  )
}
