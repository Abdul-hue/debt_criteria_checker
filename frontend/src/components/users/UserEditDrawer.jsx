import React, { useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { editUserSchema } from '../../schemas/userSchema'
import { useUpdateUser, useUpdateUserDepartment } from '../../hooks/useUsers'
import { useDepartments } from '../../hooks/useDepartments'
import { useToast } from '../../hooks/useToast'
import { useAuth } from '../../context/AuthContext'
import { extractErrorMessage } from '../../lib/errorHandler'
import EditDrawer from '../shared/EditDrawer'
import { Eye, EyeOff, AlertTriangle } from 'lucide-react'

export default function UserEditDrawer({ user, isOpen, onClose }) {
  const { mutateAsync: updateUser, isPending } = useUpdateUser()
  const { mutateAsync: updateUserDept, isPending: isDeptPending } = useUpdateUserDepartment()
  const { data: departments = [] } = useDepartments()
  const { user: currentUser } = useAuth()
  const toast = useToast()
  const [showPassword, setShowPassword] = useState(false)
  const [selectedDeptId, setSelectedDeptId] = useState('')

  const isSelf = currentUser?.user_id === user?.id

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      first_name: user?.first_name || '',
      last_name: user?.last_name || '',
      role: user?.role || 'assessor',
      is_active: user?.is_active ?? true,
      password: '',
    },
  })

  useEffect(() => {
    if (user) {
      reset({
        first_name: user.first_name,
        last_name: user.last_name,
        role: user.role,
        is_active: user.is_active,
        password: '',
      })
      setSelectedDeptId(user.department?.id ? String(user.department.id) : '')
    }
  }, [user, reset])

  const watchedRole = watch('role')
  const roleChanged = isSelf && watchedRole !== user?.role

  const onSubmit = async (data) => {
    try {
      const payload = { id: user.id, ...data }
      if (!data.password) delete payload.password
      await updateUser(payload)
      const currentDeptId = user.department?.id ? String(user.department.id) : ''
      if (selectedDeptId !== currentDeptId) {
        await updateUserDept({
          userId: user.id,
          department_id: selectedDeptId ? parseInt(selectedDeptId, 10) : null,
        })
      }
      toast.success('User updated', 'Changes have been saved successfully.')
      onClose()
    } catch (err) {
      toast.error('Update failed', extractErrorMessage(err))
    }
  }

  return (
    <EditDrawer
      isOpen={isOpen}
      onClose={onClose}
      title={`Edit User — ${user?.first_name} ${user?.last_name}`}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">First Name</label>
            <input
              {...register('first_name')}
              type="text"
              className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            {errors.first_name && (
              <p className="mt-1 text-xs text-red-600">{errors.first_name.message}</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Last Name</label>
            <input
              {...register('last_name')}
              type="text"
              className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            {errors.last_name && (
              <p className="mt-1 text-xs text-red-600">{errors.last_name.message}</p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <p className="w-full border border-slate-100 bg-slate-50 rounded-md px-3 py-2 text-sm text-slate-500">
            {user?.email}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Role</label>
          <select
            {...register('role')}
            className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <option value="assessor">Assessor</option>
            <option value="admin">Admin</option>
          </select>
          {errors.role && <p className="mt-1 text-xs text-red-600">{errors.role.message}</p>}
          {roleChanged && (
            <div className="mt-2 flex items-start gap-2 p-3 rounded-md bg-amber-50 border border-amber-200">
              <AlertTriangle size={15} className="text-amber-600 mt-0.5 shrink-0" />
              <p className="text-xs text-amber-700">
                Changing your own role will affect your current session.
              </p>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Department</label>
          <select
            value={selectedDeptId}
            onChange={(e) => setSelectedDeptId(e.target.value)}
            className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <option value="">No department</option>
            {departments.filter((d) => d.is_active || d.id === user?.department?.id).map((d) => (
              <option key={d.id} value={String(d.id)}>{d.name}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center justify-between py-1">
          <label className="text-sm font-medium text-slate-700">Active</label>
          <label className="relative inline-flex items-center cursor-pointer">
            <input {...register('is_active')} type="checkbox" className="sr-only peer" />
            <div className="w-11 h-6 bg-slate-200 peer-focus:ring-2 peer-focus:ring-slate-400 rounded-full peer peer-checked:bg-slate-900 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full" />
          </label>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            New Password{' '}
            <span className="text-slate-400 font-normal">(leave blank to keep unchanged)</span>
          </label>
          <div className="relative">
            <input
              {...register('password')}
              type={showPassword ? 'text' : 'password'}
              placeholder="••••••••"
              className="w-full border border-slate-200 rounded-md px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              tabIndex={-1}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {errors.password && (
            <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>
          )}
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
          <button
            type="button"
            onClick={onClose}
            disabled={isPending}
            className="px-4 py-2 text-sm rounded-md border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="px-4 py-2 text-sm rounded-md bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50 transition-colors"
          >
            {isPending ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </EditDrawer>
  )
}
