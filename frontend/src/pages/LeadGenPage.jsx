import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowUpRight, ClipboardCheck, ExternalLink, LogOut, PictureInPicture2 } from 'lucide-react'
import LeadGenCheckPanel from '../components/leadgen/LeadGenCheckPanel.jsx'
import { Button, Card, Hint, HintProvider, PageHeader } from '../components/leadgen/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

const POPOUT_SIZE = { width: 400, height: 700 }

const supportsDocumentPip = () =>
  typeof window !== 'undefined' && 'documentPictureInPicture' in window

/** Copy the app's stylesheets into the pop-out document so Tailwind applies. */
function copyStyles(targetDoc) {
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      const css = Array.from(sheet.cssRules).map((r) => r.cssText).join('\n')
      const style = targetDoc.createElement('style')
      style.textContent = css
      targetDoc.head.appendChild(style)
    } catch {
      // Cross-origin sheet (e.g. Google Fonts): link it instead.
      if (sheet.href) {
        const link = targetDoc.createElement('link')
        link.rel = 'stylesheet'
        link.href = sheet.href
        targetDoc.head.appendChild(link)
      }
    }
  }
}

function displayName(user) {
  if (!user) return ''
  const full = [user.first_name, user.last_name].filter(Boolean).join(' ').trim()
  return full || user.username || user.email || ''
}

function Divider() {
  return <span aria-hidden="true" className="hidden sm:block h-6 w-px bg-slate-200" />
}

/**
 * Lead Gen app bar. Lead Gen is its own workflow on the criteria engine, not a
 * CAT screen: the only link out is the clearly labelled, secondary
 * "Back to main app" link (admins only, as before).
 */
function LeadGenHeader({ user, isAdmin, onLogout, popOut }) {
  const name = displayName(user)
  return (
    <header className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-slate-200">
      <div className="mx-auto max-w-6xl h-16 px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand-navy text-white" aria-hidden="true">
            <ClipboardCheck size={18} />
          </span>
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="text-[15px] font-semibold text-slate-900">Lead Gen</span>
            <span className="hidden sm:inline text-sm text-slate-500 truncate">Criteria Check</span>
          </div>
        </div>

        <nav aria-label="Lead Gen" className="flex items-center gap-2 sm:gap-4">
          {/* Pop-out is a desktop convenience; hidden on phone widths. */}
          {popOut && (
            <>
              <span className="hidden sm:block">{popOut}</span>
              <Divider />
            </>
          )}

          {isAdmin && (
            <>
              <Hint label="Leave Lead Gen and go back to the main app">
                <Link
                  to="/"
                  className="inline-flex h-9 items-center gap-1 rounded-md px-2.5 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
                >
                  Back to main app
                  <ArrowUpRight size={15} aria-hidden="true" />
                </Link>
              </Hint>
              <Divider />
            </>
          )}

          <div className="flex items-center gap-3">
            {name && (
              <div className="hidden md:flex items-center gap-2" title={user?.email || name}>
                <span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">
                  {name[0].toUpperCase()}
                </span>
                <span className="max-w-[12rem] truncate text-sm text-slate-700">{name}</span>
              </div>
            )}
            <Hint label="Sign out">
              <Button variant="ghost" size="sm" onClick={onLogout} aria-label="Sign out" className="h-9">
                <LogOut size={16} aria-hidden="true" />
                <span className="hidden sm:inline">Sign out</span>
              </Button>
            </Hint>
          </div>
        </nav>
      </div>
    </header>
  )
}

/**
 * /lead-gen — Lead Gen pre-screen, deliberately outside the CAT layout.
 *
 * Corner-of-screen options (none mandatory):
 *  - "Pop out (always on top)": Document Picture-in-Picture (Chrome/Edge 116+).
 *    The same React tree is portalled into an always-on-top mini window.
 *  - "Open small window": plain popup fallback for other browsers (not
 *    always-on-top — browsers cannot guarantee that for normal windows).
 *  - Install as an app (PWA manifest) for a standalone, resizable window.
 */
export default function LeadGenPage() {
  const [params] = useSearchParams()
  const compact = params.get('compact') === '1'
  const { user, isAdmin, logout } = useAuth()
  const [pipWindow, setPipWindow] = useState(null)
  const [pipRoot, setPipRoot] = useState(null)
  const isStandalone = typeof window !== 'undefined' && window.matchMedia?.('(display-mode: standalone)').matches
  // The pop-out is the default way in. Browsers only open it from a click, so the
  // page leads with an "Open Lead Gen check" button. The in-page form is the fallback,
  // and is used directly where a pop-out makes no sense: inside the pop-up window itself,
  // an installed app window, or a phone.
  const [inline, setInline] = useState(() => compact || isStandalone
    || (typeof window !== 'undefined' && window.innerWidth < 640))

  const closePip = useCallback(() => {
    setPipRoot(null)
    setPipWindow(null)
  }, [])

  useEffect(() => () => pipWindow?.close(), [pipWindow])

  // Make only this page installable (PWA): attach the Lead Gen manifest while mounted.
  useEffect(() => {
    const link = document.createElement('link')
    link.rel = 'manifest'
    link.href = `${import.meta.env.BASE_URL}lead-gen.webmanifest`
    document.head.appendChild(link)
    return () => link.remove()
  }, [])

  const openPip = async () => {
    try {
      const win = await window.documentPictureInPicture.requestWindow(POPOUT_SIZE)
      copyStyles(win.document)
      win.document.title = 'Lead Gen check'
      win.document.body.className = 'bg-[#f9fafb] text-[#111827] p-3'
      const root = win.document.createElement('div')
      win.document.body.appendChild(root)
      win.addEventListener('pagehide', closePip)
      setPipWindow(win)
      setPipRoot(root)
    } catch {
      openSmallWindow()
    }
  }

  const openSmallWindow = () => {
    window.open(
      '/lead-gen?compact=1',
      'lead-gen-check',
      `popup,width=${POPOUT_SIZE.width},height=${POPOUT_SIZE.height}`,
    )
  }

  const canPip = supportsDocumentPip()
  const openPopOut = canPip ? openPip : openSmallWindow

  const popOut = !inline ? null : canPip ? (
    <Hint label="Keep the check in a small window that stays on top of other apps">
      <Button variant="secondary" size="sm" className="h-9" onClick={openPip} disabled={Boolean(pipWindow)}
              aria-label="Pop out (always on top)">
        <PictureInPicture2 size={15} aria-hidden="true" />
        <span className="hidden sm:inline">Pop out</span>
      </Button>
    </Hint>
  ) : (
    <Hint label="Open the check in a small separate window">
      <Button variant="secondary" size="sm" className="h-9" onClick={openSmallWindow} aria-label="Open small window">
        <ExternalLink size={15} aria-hidden="true" />
        <span className="hidden sm:inline">Small window</span>
      </Button>
    </Hint>
  )

  return (
    <HintProvider>
      <div className="min-h-screen bg-slate-50">
        {!compact && <LeadGenHeader user={user} isAdmin={isAdmin} onLogout={logout} popOut={popOut} />}

        <main className={compact ? 'p-3' : 'mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-6 lg:py-8'}>
          {!compact && (
            <div className="mb-6">
              <PageHeader title="Lead Gen Criteria Check" description="Pre-screen only — not a full assessment" />
            </div>
          )}

          {pipWindow ? (
            <Card className="mx-auto max-w-md px-6 py-8 text-center">
              <PictureInPicture2 size={24} aria-hidden="true" className="mx-auto text-slate-400" />
              <p className="mt-3 text-sm text-slate-700">The Lead Gen check is open in the pop-out window.</p>
              <Button variant="secondary" className="mt-4" onClick={() => { setInline(true); pipWindow.close() }}>
                Bring it back here
              </Button>
            </Card>
          ) : inline ? (
            <LeadGenCheckPanel />
          ) : (
            <Card className="mx-auto max-w-lg px-6 py-10 text-center">
              <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-700" aria-hidden="true">
                <PictureInPicture2 size={22} />
              </span>
              <h2 className="mt-4 text-lg font-semibold text-slate-900">Check cases from a pop-out window</h2>
              <p className="mt-1 text-sm text-slate-500">
                {canPip
                  ? 'A small Lead Gen check that stays on top of your other apps while you work.'
                  : 'A small Lead Gen check in its own window, next to your other apps.'}
              </p>
              <Button variant="primary" size="lg" className="mt-6 w-full sm:w-auto sm:min-w-[16rem]" onClick={openPopOut}>
                <PictureInPicture2 size={16} aria-hidden="true" /> Open Lead Gen check
              </Button>
              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => setInline(true)}
                  className="rounded text-sm text-slate-600 underline-offset-4 hover:text-slate-900 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
                >
                  or check a case on this page
                </button>
              </div>
            </Card>
          )}

          {!compact && !isStandalone && (
            <p className="mt-8 text-xs text-slate-400">
              Tip: use your browser&apos;s &ldquo;Install app&rdquo; option to keep this check in its own small window.
            </p>
          )}
        </main>

        {pipWindow && pipRoot && createPortal(<LeadGenCheckPanel />, pipRoot)}
      </div>
    </HintProvider>
  )
}
