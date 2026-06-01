import { useState, useEffect } from 'react'
import { useDepartments } from '../hooks/useDepartments'
import { useUsers } from '../hooks/useUsers'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import EmptyState from '../components/shared/EmptyState'
import DepartmentFormDrawer from '../components/DepartmentFormDrawer'
import DepartmentDetailDrawer from '../components/DepartmentDetailDrawer'
import { Building2, Plus, Users } from 'lucide-react'

export default function DepartmentPage() {
  const { data: departments = [], isLoading, error } = useDepartments()
  const { data: users = [] } = useUsers()
  const [addOpen, setAddOpen] = useState(false)
  const [detailTarget, setDetailTarget] = useState(null)

  // Keep detailTarget in sync when departments refetch after edit
  useEffect(() => {
    if (detailTarget) {
      const updated = departments.find((d) => d.id === detailTarget.id)
      if (updated) setDetailTarget(updated)
    }
  }, [departments])

  if (isLoading) return <div className="p-6"><LoadingSpinner /></div>
  if (error) return (
    <div className="p-6">
      <div className="p-4 bg-red-50 text-red-700 rounded-lg text-sm">Error loading departments.</div>
    </div>
  )

  const userCountMap = users.reduce((acc, u) => {
    if (u.department?.id) {
      acc[u.department.id] = (acc[u.department.id] || 0) + 1
    }
    return acc
  }, {})

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Departments</h1>
          <p className="mt-1 text-sm text-slate-500">Manage department access and rule visibility.</p>
        </div>
        <button
          onClick={() => setAddOpen(true)}
          className="inline-flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-slate-800 transition-colors"
        >
          <Plus size={16} />
          Add Department
        </button>
      </div>

      {departments.length === 0 ? (
        <EmptyState
          icon={<Building2 className="w-8 h-8 text-slate-300" />}
          title="No departments"
          message="No departments have been created yet."
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
                  Description
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Users
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
              {departments.map((dept) => (
                <tr key={dept.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="text-sm font-medium text-slate-900">{dept.name}</div>
                    <div className="text-xs text-slate-400 font-mono mt-0.5">{dept.slug}</div>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-500 max-w-xs truncate">
                    {dept.description || '—'}
                  </td>
                  <td className="px-6 py-4">
                    <span className="inline-flex items-center gap-1.5 text-sm text-slate-600">
                      <Users size={14} className="text-slate-400" />
                      {userCountMap[dept.id] || 0}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    {dept.is_active ? (
                      <span className="inline-flex items-center gap-1.5 text-sm">
                        <span className="h-2 w-2 rounded-full bg-green-500" />
                        <span className="text-green-700">Active</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-sm">
                        <span className="h-2 w-2 rounded-full bg-slate-400" />
                        <span className="text-slate-500">Inactive</span>
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={() => setDetailTarget(dept)}
                      className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded border border-slate-200 hover:bg-slate-50 transition-colors"
                    >
                      Manage
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <DepartmentFormDrawer isOpen={addOpen} onClose={() => setAddOpen(false)} />

      {detailTarget && (
        <DepartmentDetailDrawer
          department={detailTarget}
          isOpen={!!detailTarget}
          onClose={() => setDetailTarget(null)}
        />
      )}
    </div>
  )
}
