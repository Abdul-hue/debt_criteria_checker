import React, { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { createUserSchema } from '../../schemas/userSchema'
import { useCreateUser } from '../../hooks/useUsers'
import { useToast } from '../../hooks/useToast'
import { extractErrorMessage } from '../../lib/errorHandler'
import EditDrawer from '../shared/EditDrawer'
import { Eye, EyeOff } from 'lucide-react'

export default function UserCreateDrawer({ isOpen, onClose }) {
  const { mutateAsync: createUser, isPending } = useCreateUser()
  const toast = useToast()
  const [showPassword, setShowPassword] = useState(false)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(createUserSchema),
    defaultValues: { is_active: true, role: 'assessor' },
  })

  const onSubmit = async (data) => {
    try {
      await createUser(data)
      toast.success('User created', 'New user has been created successfully.')
      reset()
      onClose()
    } catch (err) {
      toast.error('Create failed', extractErrorMessage(err))
    }
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  return (
    <EditDrawer isOpen={isOpen} onClose={handleClose} title="Create User">
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
          <input
            {...register('email')}
            type="email"
            className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
          {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
          <div className="relative">
            <input
              {...register('password')}
              type={showPassword ? 'text' : 'password'}
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
        </div>

        <div className="flex items-center justify-between py-1">
          <label className="text-sm font-medium text-slate-700">Active</label>
          <label className="relative inline-flex items-center cursor-pointer">
            <input {...register('is_active')} type="checkbox" className="sr-only peer" defaultChecked />
            <div className="w-11 h-6 bg-slate-200 peer-focus:ring-2 peer-focus:ring-slate-400 rounded-full peer peer-checked:bg-slate-900 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full" />
          </label>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
          <button
            type="button"
            onClick={handleClose}
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
            {isPending ? 'Creating...' : 'Create User'}
          </button>
        </div>
      </form>
    </EditDrawer>
  )
}
