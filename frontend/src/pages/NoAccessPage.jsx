import { Lock } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useDepartment } from '../hooks/useDepartment'

export default function NoAccessPage() {
  const { user } = useAuth()
  const { data: department } = useDepartment()

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="flex flex-col items-center gap-4 text-center max-w-sm px-4">
        <div className="bg-indigo-100 p-4 rounded-full">
          <Lock className="text-indigo-600 w-8 h-8" />
        </div>
        <h1 className="text-2xl font-semibold text-slate-800">No Pages Assigned</h1>
        <p className="text-slate-500 text-sm leading-relaxed">
          Your account hasn't been assigned any pages yet.
          Please contact your administrator to get access.
        </p>
        <p className="text-xs text-slate-400 mt-4">
          {user?.email} · {department?.name || 'No department'}
        </p>
      </div>
    </div>
  )
}
