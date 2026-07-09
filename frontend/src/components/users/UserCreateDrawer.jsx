import React, { useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { createUserSchema } from '../../schemas/userSchema'
import { useCreateUser, useUpdateUserDepartment } from '../../hooks/useUsers'
import { useDepartments } from '../../hooks/useDepartments'
import { useToast } from '../../hooks/useToast'
import { extractErrorMessage } from '../../lib/errorHandler'
import EditDrawer from '../shared/EditDrawer'
import { Eye, EyeOff, Loader2 } from 'lucide-react'

const INPUT_CLS =
  'w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400'

export default function UserCreateDrawer({ isOpen, onClose }) {
  const { mutateAsync: createUser, isPending } = useCreateUser()
  const { mutateAsync: updateUserDept } = useUpdateUserDepartment()
  const { data: departments = [] } = useDepartments()
  const toast = useToast()

  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [selectedDeptId, setSelectedDeptId] = useState('')
  const [usernameManuallyEdited, setUsernameManuallyEdited] = useState(false)

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(createUserSchema),
    defaultValues: { is_active: true, role: 'assessor' },
  })

  const firstName = watch('first_name')
  const lastName = watch('last_name')

  useEffect(() => {
    if (!usernameManuallyEdited) {
      const suggested = [firstName, lastName]
        .filter(Boolean)
        .map((s) => s.trim())
        .filter(Boolean)
        .join('.')
        .toLowerCase()
        .replace(/\s+/g, '')
      if (suggested) {
        setValue('username', suggested, { shouldValidate: false })
      }
    }
  }, [firstName, lastName, usernameManuallyEdited, setValue])

  const usernameField = register('username')

  const isLoading = isPending || isSubmitting

  const onSubmit = async (data) => {
    try {
      const { confirmPassword: _cp, ...payload } = data
      const newUser = await createUser(payload)
      if (selectedDeptId && newUser?.id) {
        await updateUserDept({ userId: newUser.id, department_id: parseInt(selectedDeptId, 10) })
      }
      toast.success('User created', 'New user has been created successfully.')
      reset()
      setSelectedDeptId('')
      setUsernameManuallyEdited(false)
      onClose()
    } catch (err) {
      toast.error('Create failed', extractErrorMessage(err))
    }
  }

  const handleClose = () => {
    reset()
    setSelectedDeptId('')
    setUsernameManuallyEdited(false)
    onClose()
  }

  return (
    <EditDrawer isOpen={isOpen} onClose={handleClose} title="Create User">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">

        {/* First Name | Last Name */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">First Name</label>
            <input {...register('first_name')} type="text" className={INPUT_CLS} />
            {errors.first_name && (
              <p className="mt-1 text-xs text-red-600">{errors.first_name.message}</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Last Name</label>
            <input {...register('last_name')} type="text" className={INPUT_CLS} />
            {errors.last_name && (
              <p className="mt-1 text-xs text-red-600">{errors.last_name.message}</p>
            )}
          </div>
        </div>

        {/* Username */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
          <input
            {...usernameField}
            onChange={(e) => {
              setUsernameManuallyEdited(true)
              usernameField.onChange(e)
            }}
            type="text"
            placeholder="e.g. abdul.wasay"
            className={INPUT_CLS}
          />
          {errors.username && (
            <p className="mt-1 text-xs text-red-600">{errors.username.message}</p>
          )}
        </div>

        {/* Email */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <input {...register('email')} type="email" className={INPUT_CLS} />
          {errors.email && <p className="mt-1 text-xs text-red-600">{errors.email.message}</p>}
        </div>

        {/* Password | Confirm Password */}
        <div className="grid grid-cols-2 gap-4">
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
            <label className="block text-sm font-medium text-slate-700 mb-1">Confirm Password</label>
            <div className="relative">
              <input
                {...register('confirmPassword')}
                type={showConfirmPassword ? 'text' : 'password'}
                placeholder="Re-enter password"
                className="w-full border border-slate-200 rounded-md px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                tabIndex={-1}
                aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
              >
                {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {errors.confirmPassword && (
              <p className="mt-1 text-xs text-red-600">{errors.confirmPassword.message}</p>
            )}
          </div>
        </div>

        {/* Role */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Role</label>
          <select {...register('role')} className={INPUT_CLS}>
            <option value="assessor">Assessor</option>
            <option value="admin">Admin</option>
          </select>
          {errors.role && <p className="mt-1 text-xs text-red-600">{errors.role.message}</p>}
        </div>

        {/* Department */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Department</label>
          <select
            value={selectedDeptId}
            onChange={(e) => setSelectedDeptId(e.target.value)}
            className={INPUT_CLS}
          >
            <option value="">No department</option>
            {departments.filter((d) => d.is_active).map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>

        {/* Active */}
        <div className="flex items-center justify-between py-1">
          <label className="text-sm font-medium text-slate-700">Active</label>
          <label className="relative inline-flex items-center cursor-pointer">
            <input {...register('is_active')} type="checkbox" className="sr-only peer" defaultChecked />
            <div className="w-11 h-6 bg-slate-200 peer-focus:ring-2 peer-focus:ring-slate-400 rounded-full peer peer-checked:bg-brand-navy after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full" />
          </label>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
          <button
            type="button"
            onClick={handleClose}
            disabled={isLoading}
            className="px-4 py-2 text-sm rounded-md border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isLoading}
            className="px-4 py-2 text-sm rounded-md bg-brand-navy text-white hover:bg-slate-800 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {isLoading && <Loader2 size={14} className="animate-spin" />}
            {isLoading ? 'Creating...' : 'Create User'}
          </button>
        </div>
      </form>
    </EditDrawer>
  )
}
