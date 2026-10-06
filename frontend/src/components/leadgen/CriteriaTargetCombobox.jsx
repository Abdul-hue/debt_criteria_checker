import { useEffect, useId, useRef, useState } from 'react'
import clsx from 'clsx'
import { ChevronsUpDown, Loader2, Search } from 'lucide-react'
import { useCriteriaTargets } from '../../hooks/useCriteriaChanges'
import { Button } from './ui.jsx'

const RESULT_CAP = 50 // the targets endpoint returns at most 50 matches

function Highlight({ text, query }) {
  const q = query.trim()
  const i = q ? text.toLowerCase().indexOf(q.toLowerCase()) : -1
  if (i < 0) return text
  return (
    <>
      {text.slice(0, i)}
      <mark className="bg-transparent font-semibold text-slate-900">{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  )
}

/**
 * Type-to-search picker for a criteria row (creditor, council, ...), replacing
 * the long native <select>. Uses the existing targets search endpoint.
 */
export default function CriteriaTargetCombobox({ id, model, label, selected, onSelect }) {
  const listId = useId()
  const inputRef = useRef(null)
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const targets = useCriteriaTargets(model, q)
  const results = targets.data || []

  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 250)
    return () => clearTimeout(t)
  }, [text])

  useEffect(() => { setActive(0) }, [q, model])
  useEffect(() => { setText(''); setQ('') }, [model])

  const choose = (r) => {
    onSelect(r)
    setOpen(false)
    setText('')
  }

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) setOpen(true)
      else setActive((a) => Math.min(a + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter') {
      if (open && results[active]) {
        e.preventDefault()
        choose(results[active])
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  if (selected) {
    return (
      <div className="flex h-10 items-center justify-between gap-2 rounded-md border border-slate-300 bg-slate-50 pl-3 pr-1">
        <span id={id} className="truncate text-sm font-medium text-slate-900">{selected.label}</span>
        <Button
          variant="ghost"
          size="sm"
          aria-label={`Change ${label.toLowerCase()}`}
          onClick={() => { onSelect(null); setTimeout(() => inputRef.current?.focus(), 0) }}
        >
          Change
        </Button>
      </div>
    )
  }

  const optionId = (i) => `${listId}-opt-${i}`

  return (
    <div className="relative">
      <Search size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
      <input
        id={id}
        ref={inputRef}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && results[active] ? optionId(active) : undefined}
        autoComplete="off"
        value={text}
        placeholder={`Search ${label.toLowerCase()}s…`}
        onChange={(e) => { setText(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className="block h-10 w-full rounded-md border border-slate-300 bg-white pl-9 pr-9 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-500/30 focus:border-slate-500"
      />
      <ChevronsUpDown size={15} aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />

      {open && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg">
          <ul id={listId} role="listbox" aria-label={`${label} results`} className="max-h-64 overflow-y-auto py-1">
            {results.map((r, i) => (
              <li
                key={r.id}
                id={optionId(i)}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); choose(r) }}
                onMouseEnter={() => setActive(i)}
                className={clsx('cursor-pointer px-3 py-2 text-sm text-slate-700', i === active && 'bg-slate-100 text-slate-900')}
              >
                <Highlight text={r.label} query={q} />
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-2 border-t border-slate-100 px-3 py-1.5 text-xs text-slate-500" aria-live="polite">
            {targets.isFetching ? (
              <><Loader2 size={12} className="animate-spin" aria-hidden="true" /> Searching…</>
            ) : results.length === 0 ? (
              q ? `No ${label.toLowerCase()}s match “${q}”.` : 'Nothing to show.'
            ) : results.length >= RESULT_CAP ? (
              `Showing the first ${RESULT_CAP} — keep typing to narrow the list.`
            ) : (
              `${results.length} ${results.length === 1 ? 'match' : 'matches'}`
            )}
          </div>
        </div>
      )}
    </div>
  )
}
