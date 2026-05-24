import React from 'react'
import UsersList from '../components/users/UsersList'

export default function UserManagementPage() {
  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">User Management</h1>
        <p className="mt-1 text-sm text-slate-500">Manage system users and their access roles.</p>
      </div>
      <UsersList />
    </div>
  )
}
