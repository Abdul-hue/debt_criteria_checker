import Header from './Header.jsx'
import Sidebar from './Sidebar.jsx'

/**
 * Layout component
 * Outer wrapper: flex flex-col h-screen bg-gray-50
 */
export default function Layout({ children }) {
  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header at the top, fixed height h-14 */}
      <Header />

      {/* Below header: flex flex-1 overflow-hidden */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Sidebar fixed width w-56, full height, no overflow */}
        <Sidebar />

        {/* Right: main with flex-1 overflow-y-auto p-6 */}
        <main className="flex-1 overflow-y-auto p-6">
          {/* Renders {children} inside main */}
          {children}
        </main>
      </div>
    </div>
  )
}
