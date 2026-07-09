import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useCreateDepartment, useUpdateDepartment } from '../hooks/useDepartments'
import { useToast } from '../hooks/useToast'
import { extractErrorMessage } from '../lib/errorHandler'
import EditDrawer from './shared/EditDrawer'

const departmentSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional().default(''),
  is_active: z.boolean().default(true),
})

function slugify(str) {
  return str
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
}

export default function DepartmentFormDrawer({ isOpen, onClose, department }) {
  const isEdit = !!department
  const { mutateAsync: createDept, isPending: isCreating } = useCreateDepartment()
  const { mutateAsync: updateDept, isPending: isUpdating } = useUpdateDepartment()
  const isPending = isCreating || isUpdating
  const toast = useToast()

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(departmentSchema),
    defaultValues: { name: '', description: '', is_active: true },
  })

  const watchedName = watch('name', '')

  useEffect(() => {
    if (isOpen) {
      reset(
        department
          ? { name: department.name, description: department.description || '', is_active: department.is_active }
          : { name: '', description: '', is_active: true }
      )
    }
  }, [isOpen, department, reset])

  const onSubmit = async (data) => {
    try {
      if (isEdit) {
        await updateDept({ id: department.id, ...data })
        toast.success('Department updated', 'Changes have been saved.')
      } else {
        await createDept(data)
        toast.success('Department created', 'New department has been created.')
      }
      reset()
      onClose()
    } catch (err) {
      toast.error(isEdit ? 'Update failed' : 'Create failed', extractErrorMessage(err))
    }
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  return (
    <EditDrawer
      isOpen={isOpen}
      onClose={handleClose}
      title={isEdit ? 'Edit Department' : 'Add Department'}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
          <input
            {...register('name')}
            type="text"
            placeholder="e.g. Lead Generation"
            className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
          {errors.name && <p className="mt-1 text-xs text-red-600">{errors.name.message}</p>}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Slug <span className="text-slate-400 font-normal">(auto-generated)</span>
          </label>
          <div className="w-full border border-slate-100 bg-slate-50 rounded-md px-3 py-2 text-sm text-slate-500 font-mono">
            {slugify(watchedName) || '—'}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
          <textarea
            {...register('description')}
            rows={3}
            placeholder="Optional description..."
            className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
        </div>

        <div className="flex items-center justify-between py-1">
          <label className="text-sm font-medium text-slate-700">Active</label>
          <label className="relative inline-flex items-center cursor-pointer">
            <input {...register('is_active')} type="checkbox" className="sr-only peer" />
            <div className="w-11 h-6 bg-slate-200 peer-focus:ring-2 peer-focus:ring-slate-400 rounded-full peer peer-checked:bg-brand-navy after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full" />
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
            className="px-4 py-2 text-sm rounded-md bg-brand-navy text-white hover:bg-slate-800 disabled:opacity-50 transition-colors"
          >
            {isPending
              ? isEdit ? 'Saving...' : 'Creating...'
              : isEdit ? 'Save Changes' : 'Create Department'}
          </button>
        </div>
      </form>
    </EditDrawer>
  )
}
