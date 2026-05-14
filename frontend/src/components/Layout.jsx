import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar.jsx'

export default function Layout() {
  return (
    <div className="min-h-screen bg-[#f3f4f6] text-[#111827]">
      <div className="mx-auto flex min-h-screen max-w-[1400px] gap-6 px-4 py-6 lg:px-8">
        <aside className="hidden w-80 shrink-0 rounded-3xl bg-white p-6 shadow-sm md:block">
          <Sidebar />
        </aside>

        <main className="flex-1 rounded-3xl bg-white p-6 shadow-sm md:p-10">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
