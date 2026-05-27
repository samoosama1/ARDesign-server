import { useState } from 'react'
import AdminUsers from '../components/admin/AdminUsers'
import AdminDesigns from '../components/admin/AdminDesigns'
import AdminLocarno from '../components/admin/AdminLocarno'

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState('users')

  return (
    <div className="page admin-page">
      <h1 className="admin-title">Admin</h1>

      <div className="tabs">
        <button
          className={activeTab === 'users' ? 'active' : ''}
          onClick={() => setActiveTab('users')}
        >
          Users
        </button>
        <button
          className={activeTab === 'designs' ? 'active' : ''}
          onClick={() => setActiveTab('designs')}
        >
          Designs
        </button>
        <button
          className={activeTab === 'locarno' ? 'active' : ''}
          onClick={() => setActiveTab('locarno')}
        >
          Locarno
        </button>
      </div>

      {activeTab === 'users' && <AdminUsers />}
      {activeTab === 'designs' && <AdminDesigns />}
      {activeTab === 'locarno' && <AdminLocarno />}
    </div>
  )
}
