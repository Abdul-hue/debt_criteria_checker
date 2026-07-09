import React, { useState } from 'react'
import { useUsers, useDeleteUser } from '../../hooks/useUsers'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../hooks/useToast'
import { extractErrorMessage } from '../../lib/errorHandler'
import LoadingSpinner from '../shared/LoadingSpinner'
import EmptyState from '../shared/EmptyState'
import ConfirmDialog from '../shared/ConfirmDialog'
import UserCreateDrawer from './UserCreateDrawer'
import UserEditDrawer from './UserEditDrawer'
import { Users, Plus, Pencil, Trash2, Building2 } from 'lucide-react'

function RoleBadge({ role }) {
  if (role === 'admin') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
        Admin
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
      Assessor
    </span>
  )
}

function StatusDot({ isActive }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className={`h-2 w-2 rounded-full ${isActive ? 'bg-green-500' : 'bg-slate-400'}`} />
      <span className={isActive ? 'text-green-700' : 'text-slate-500'}>
        {isActive ? 'Active' : 'Inactive'}
      </span>
    </span>
  )
}

export default function UsersList() {
  const { data: users = [], isLoading } = useUsers()
  const { mutateAsync: deleteUser, isPending: isDeleting } = useDeleteUser()
  const { user: currentUser } = useAuth()
  const toast = useToast()

  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)

  if (isLoading) return <LoadingSpinner />

  const filtered = users.filter((u) => {
    const matchesSearch =
      search === '' ||
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      `${u.first_name} ${u.last_name}`.toLowerCase().includes(search.toLowerCase())
    const matchesRole = roleFilter === 'all' || u.role === roleFilter
    return matchesSearch && matchesRole
  })

  const handleDelete = async () => {
    try {
      await deleteUser(deleteTarget.id)
      toast.success(
        'User deleted',
        `${deleteTarget.first_name} ${deleteTarget.last_name} has been removed.`
      )
      setDeleteTarget(null)
    } catch (err) {
      toast.error('Delete failed', extractErrorMessage(err))
    }
  }

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3 flex-1">
          <input
            type="text"
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full max-w-sm border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <option value="all">All Roles</option>
            <option value="admin">Admin</option>
            <option value="assessor">Assessor</option>
          </select>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="inline-flex items-center gap-2 bg-brand-navy text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-slate-800 transition-colors"
        >
          <Plus size={16} />
          Create User
        </button>
      </div>

      {/* Table or empty state */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<Users className="w-8 h-8 text-slate-300" />}
          title="No users found"
          message={
            search || roleFilter !== 'all'
              ? 'Try adjusting your search or filters.'
              : 'No users have been created yet.'
          }
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Email
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Role
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Department
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-slate-100">
              {filtered.map((u) => {
                const isSelf = currentUser?.user_id === u.id
                return (
                  <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 text-sm font-medium text-slate-900">
                      {u.first_name} {u.last_name}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-600">{u.email}</td>
                    <td className="px-6 py-4">
                      <RoleBadge role={u.role} />
                    </td>
                    <td className="px-6 py-4">
                      {u.department ? (
                        <span className="inline-flex items-center gap-1.5 text-sm text-slate-600">
                          <Building2 size={13} className="text-slate-400" />
                          {u.department.name}
                        </span>
                      ) : (
                        <span className="text-sm text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <StatusDot isActive={u.is_active} />
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setEditTarget(u)}
                          className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded border border-slate-200 hover:bg-slate-50 transition-colors"
                        >
                          <Pencil size={14} />
                          Edit
                        </button>
                        <button
                          onClick={() => !isSelf && setDeleteTarget(u)}
                          disabled={isSelf}
                          title={isSelf ? 'You cannot delete your own account' : ''}
                          className={`inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded border transition-colors ${
                            isSelf
                              ? 'text-slate-300 border-slate-100 cursor-not-allowed'
                              : 'text-red-600 border-red-100 hover:bg-red-50 hover:border-red-200'
                          }`}
                        >
                          <Trash2 size={14} />
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Drawers & dialogs */}
      <UserCreateDrawer isOpen={createOpen} onClose={() => setCreateOpen(false)} />

      {editTarget && (
        <UserEditDrawer
          user={editTarget}
          isOpen={!!editTarget}
          onClose={() => setEditTarget(null)}
        />
      )}

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete User"
        message={
          deleteTarget
            ? `Are you sure you want to delete ${deleteTarget.first_name} ${deleteTarget.last_name}? This cannot be undone.`
            : ''
        }
        confirmLabel="Delete"
        variant="danger"
        loading={isDeleting}
      />
    </div>
  )
}
