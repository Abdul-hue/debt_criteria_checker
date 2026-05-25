import React, { useState, useMemo, useCallback } from 'react'
import { Search, X, ChevronDown, ChevronRight, Save, RotateCcw } from 'lucide-react'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { useSFSCategories, useUpdateSFSGuideline, useUpdateSFSCategory } from '../../hooks/useSFSGuidelines'
import { useToast } from '../../hooks/useToast'

// ── Y-axis row groups (fixed, not from API) ────────────────────────────────
const ROW_GROUPS = [
  {
    label: 'Constraint Type',
    bgClass: 'bg-slate-100',
    textClass: 'text-slate-600',
    rows: [
      { key: 'min', label: 'Min (Floor)', type: 'boolean' },
      { key: 'max', label: 'Max (Ceiling)', type: 'boolean' },
    ],
  },
  {
    label: 'Base Rates',
    bgClass: 'bg-blue-50',
    textClass: 'text-blue-700',
    rows: [
      { key: 'adult_1', label: '1 Adult' },
      { key: 'adult_2', label: '2 Adults' },
    ],
  },
  {
    label: '1 Adult + Children',
    bgClass: 'bg-violet-50',
    textClass: 'text-violet-700',
    rows: [
      { key: 'adult_1_child_1', label: '1 Adult + 1 Child' },
      { key: 'adult_1_child_2', label: '1 Adult + 2 Children' },
      { key: 'adult_1_child_3', label: '1 Adult + 3 Children' },
      { key: 'adult_1_child_4', label: '1 Adult + 4 Children' },
      { key: 'adult_1_child_5', label: '1 Adult + 5 Children' },
    ],
  },
  {
    label: '2 Adults + Children',
    bgClass: 'bg-indigo-50',
    textClass: 'text-indigo-700',
    rows: [
      { key: 'adult_2_child_1', label: '2 Adults + 1 Child' },
      { key: 'adult_2_child_2', label: '2 Adults + 2 Children' },
      { key: 'adult_2_child_3', label: '2 Adults + 3 Children' },
      { key: 'adult_2_child_4', label: '2 Adults + 4 Children' },
      { key: 'adult_2_child_5', label: '2 Adults + 5 Children' },
    ],
  },
  {
    label: 'Incremental',
    bgClass: 'bg-emerald-50',
    textClass: 'text-emerald-700',
    rows: [
      { key: 'per_child', label: 'Per Child' },
      { key: 'per_vehicle', label: 'Per Vehicle' },
    ],
  },
  {
    label: 'Watch Rates',
    bgClass: 'bg-amber-50',
    textClass: 'text-amber-700',
    rows: [
      { key: 'watch_per_adult', label: 'Watch / Adult' },
      { key: 'non_watch_per_adult', label: 'Non-Watch / Adult' },
      { key: 'watch_per_vehicle', label: 'Watch / Vehicle' },
      { key: 'non_watch_per_vehicle', label: 'Non-Watch / Vehicle' },
    ],
  },
  {
    label: 'Group Formula Rates',
    bgClass: 'bg-teal-50',
    textClass: 'text-teal-700',
    rows: [
      { key: 'first_adult', label: 'First Adult' },
      { key: 'additional_adult', label: 'Additional Adult' },
      { key: 'child_under_16', label: 'Child Under 16' },
      { key: 'child_16_18', label: 'Child 16–18' },
    ],
  },
  {
    label: 'Caps',
    bgClass: 'bg-rose-50',
    textClass: 'text-rose-700',
    rows: [
      { key: 'one_adult_cap', label: '1 Adult Cap' },
      { key: 'two_adults_cap', label: '2 Adults Cap' },
    ],
  },
]

const READ_ONLY_KEYS = new Set(['id', 'created_at', 'updated_at', 'category_group', 'category', 'label'])

function fmtMoney(val) {
  const n = parseFloat(val)
  if (!n || n === 0) return null
  return `£${n.toFixed(2)}`
}

// ── Boolean indicator (read mode) ─────────────────────────────────────────
function BoolDot({ value }) {
  return value ? (
    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-emerald-500 text-white text-[9px] font-bold">✓</span>
  ) : (
    <span className="inline-block w-4 h-4 rounded-full border-2 border-slate-300" />
  )
}

export default function SFSGuidelinesPage() {
  const [search, setSearch] = useState('')
  const [collapsedCats, setCollapsedCats] = useState({})
  const [editingColId, setEditingColId] = useState(null)
  const [editColValues, setEditColValues] = useState({})
  const [editingCatId, setEditingCatId] = useState(null)
  const [editCatCap, setEditCatCap] = useState('')

  const { data: categories, isLoading, error } = useSFSCategories()
  const updateGuideline = useUpdateSFSGuideline()
  const updateCategory = useUpdateSFSCategory()
  const toast = useToast()

  // ── Column (guideline) editing ─────────────────────────────────────────
  const startEditCol = useCallback((g) => {
    setEditingColId(g.id)
    setEditColValues({ ...g })
  }, [])

  const cancelEditCol = useCallback(() => {
    setEditingColId(null)
    setEditColValues({})
  }, [])

  const handleColChange = useCallback((key, val) => {
    setEditColValues((prev) => ({ ...prev, [key]: val }))
  }, [])

  const saveCol = useCallback(async (id) => {
    try {
      const payload = Object.fromEntries(
        Object.entries(editColValues).filter(([k]) => !READ_ONLY_KEYS.has(k))
      )
      await updateGuideline.mutateAsync({ id, ...payload })
      toast.success('Saved', 'Guideline updated.')
      setEditingColId(null)
      setEditColValues({})
    } catch (err) {
      toast.error('Save failed', err?.response?.data?.error ?? err.message)
    }
  }, [editColValues, updateGuideline, toast])

  // ── Category cap editing ───────────────────────────────────────────────
  const startEditCat = useCallback((cat) => {
    setEditingCatId(cat.id)
    setEditCatCap(cat.upper_cap ?? '')
  }, [])

  const cancelEditCat = useCallback(() => {
    setEditingCatId(null)
    setEditCatCap('')
  }, [])

  const saveCatCap = useCallback(async (id) => {
    try {
      const val = editCatCap === '' ? null : parseFloat(editCatCap)
      await updateCategory.mutateAsync({ id, upper_cap: isNaN(val) ? null : val })
      toast.success('Saved', 'Category cap updated.')
      setEditingCatId(null)
    } catch (err) {
      toast.error('Save failed', err?.response?.data?.error ?? err.message)
    }
  }, [editCatCap, updateCategory, toast])

  // ── Column list (filtered by search) ──────────────────────────────────
  const allGuidelines = useMemo(
    () => (categories ?? []).flatMap((cat) => (cat.guidelines ?? []).map((g) => ({ ...g, _catId: cat.id }))),
    [categories]
  )

  const searchActive = search.trim().length > 0
  const filteredGuidelineIds = useMemo(() => {
    if (!searchActive) return null
    const t = search.toLowerCase()
    return new Set(
      allGuidelines
        .filter((g) => g.label.toLowerCase().includes(t) || g.category.toLowerCase().includes(t))
        .map((g) => g.id)
    )
  }, [searchActive, search, allGuidelines])

  const displayCats = useMemo(() => {
    if (!categories) return []
    if (!searchActive) return categories
    return categories
      .map((cat) => ({
        ...cat,
        guidelines: (cat.guidelines ?? []).filter((g) => filteredGuidelineIds.has(g.id)),
      }))
      .filter((cat) => cat.guidelines.length > 0)
  }, [categories, searchActive, filteredGuidelineIds])

  const totalGuidelines = (categories ?? []).reduce((acc, c) => acc + (c.guidelines?.length ?? 0), 0)

  if (isLoading) return <div className="p-8"><LoadingSpinner /></div>

  if (error) {
    return (
      <div className="p-6">
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          Failed to load guidelines: {error.message}
        </div>
      </div>
    )
  }

  if (!categories?.length) {
    return (
      <div className="p-6 text-sm text-slate-500 bg-white border border-slate-200 rounded-lg px-4 py-8 text-center">
        No SFS guideline categories found. Run{' '}
        <code className="font-mono text-xs bg-slate-100 px-1 py-0.5 rounded">
          python manage.py seed_sfs_guidelines
        </code>{' '}
        to populate.
      </div>
    )
  }

  return (
    <div className="p-6 max-w-full">
      {/* Page header */}
      <div className="mb-6 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">SFS Expenditure Guidelines</h1>
          <p className="mt-1 text-sm text-slate-500">
            Columns = spending categories · Rows = household compositions · All values £ / month
          </p>
        </div>
        <div className="text-xs font-semibold text-slate-400 bg-white border border-slate-200 px-3 py-1.5 rounded-full shadow-sm shrink-0">
          {totalGuidelines} guidelines · {categories?.length ?? 0} category groups
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-5 max-w-sm">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          placeholder="Search by label or category slug..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-8 py-2 text-sm border border-slate-200 rounded-lg bg-white text-slate-900 placeholder-slate-400 outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {search && (
          <button
            onClick={() => setSearch('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {searchActive && displayCats.length === 0 && (
        <div className="text-sm text-slate-500 text-center py-8">No guidelines match "{search}"</div>
      )}

      {/* Transposed table */}
      {displayCats.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="border-collapse text-left text-xs">
              <thead>

                {/* ══ ROW 1: Category group headers ══ */}
                <tr className="border-b border-slate-200">
                  {/* Top-left corner spanning all 3 header rows */}
                  <th
                    rowSpan={3}
                    className="sticky left-0 z-30 bg-slate-50 border-r border-b-2 border-slate-200 px-4 py-3 min-w-[200px] align-bottom"
                  >
                    <span className="text-[10px] font-black uppercase tracking-wider text-slate-500">
                      Composition
                    </span>
                  </th>

                  {displayCats.map((cat) => {
                    const isCollapsed = !searchActive && collapsedCats[cat.id]
                    const colCount = isCollapsed ? 1 : (cat.guidelines ?? []).length
                    const isEditingCap = editingCatId === cat.id

                    return (
                      <th
                        key={cat.id}
                        colSpan={colCount}
                        className="bg-slate-800 text-white px-3 py-2 border-r border-slate-700 whitespace-nowrap"
                      >
                        <div className="flex items-center gap-2">
                          {/* Collapse toggle */}
                          {!searchActive && (
                            <button
                              onClick={() => setCollapsedCats((p) => ({ ...p, [cat.id]: !p[cat.id] }))}
                              className="p-0.5 rounded hover:bg-slate-600 transition-colors shrink-0"
                            >
                              {isCollapsed
                                ? <ChevronRight size={13} />
                                : <ChevronDown size={13} />}
                            </button>
                          )}

                          <span className="font-black text-[11px] uppercase tracking-wider truncate">
                            {cat.name}
                          </span>

                          {/* Group cap */}
                          {!isCollapsed && (
                            <div className="flex items-center gap-1 ml-auto shrink-0" onClick={(e) => e.stopPropagation()}>
                              {isEditingCap ? (
                                <>
                                  <input
                                    autoFocus
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    value={editCatCap}
                                    onChange={(e) => setEditCatCap(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter') saveCatCap(cat.id)
                                      if (e.key === 'Escape') cancelEditCat()
                                    }}
                                    placeholder="No cap"
                                    className="h-5 w-20 text-[10px] bg-slate-700 border border-slate-500 text-white text-right px-1.5 rounded outline-none tabular-nums"
                                  />
                                  <button
                                    onClick={() => saveCatCap(cat.id)}
                                    className="p-0.5 rounded bg-blue-600 hover:bg-blue-500 text-white"
                                  >
                                    <Save size={11} />
                                  </button>
                                  <button
                                    onClick={cancelEditCat}
                                    className="p-0.5 rounded hover:bg-slate-600 text-slate-400"
                                  >
                                    <RotateCcw size={11} />
                                  </button>
                                </>
                              ) : (
                                <button
                                  onClick={() => startEditCat(cat)}
                                  className="text-[9px] px-1.5 py-0.5 rounded-full bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors tabular-nums whitespace-nowrap"
                                >
                                  Cap: {cat.upper_cap ? `£${parseFloat(cat.upper_cap).toFixed(0)}` : '—'}
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </th>
                    )
                  })}
                </tr>

                {/* ══ ROW 2: Individual guideline labels ══ */}
                <tr className="border-b border-slate-100">
                  {displayCats.map((cat) => {
                    const isCollapsed = !searchActive && collapsedCats[cat.id]
                    if (isCollapsed) {
                      return (
                        <th
                          key={cat.id}
                          className="bg-slate-800 px-3 py-2 border-r border-slate-600 text-slate-400 text-[10px] font-semibold text-center italic whitespace-nowrap"
                        >
                          collapsed
                        </th>
                      )
                    }
                    return (cat.guidelines ?? []).map((g, gi) => (
                      <th
                        key={g.id}
                        className={[
                          'px-3 py-2 text-[11px] font-bold text-slate-700 whitespace-nowrap bg-slate-50 border-b border-slate-200',
                          gi === (cat.guidelines.length - 1) ? 'border-r border-slate-200' : '',
                        ].join(' ')}
                      >
                        <div className="max-w-[110px] truncate" title={g.label}>{g.label}</div>
                        <div className="text-[9px] text-slate-400 font-mono mt-0.5 truncate">{g.category}</div>
                      </th>
                    ))
                  })}
                </tr>

                {/* ══ ROW 3: Edit / Save / Cancel per column ══ */}
                <tr className="border-b-2 border-slate-200 bg-white">
                  {displayCats.map((cat) => {
                    const isCollapsed = !searchActive && collapsedCats[cat.id]
                    if (isCollapsed) return <th key={cat.id} className="border-r border-slate-200" />
                    return (cat.guidelines ?? []).map((g, gi) => {
                      const isEditing = editingColId === g.id
                      return (
                        <th
                          key={g.id}
                          className={[
                            'px-2 py-1.5',
                            gi === (cat.guidelines.length - 1) ? 'border-r border-slate-200' : '',
                          ].join(' ')}
                        >
                          {isEditing ? (
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => saveCol(g.id)}
                                className="flex items-center gap-0.5 h-6 px-2 text-[10px] bg-blue-600 hover:bg-blue-500 text-white rounded font-semibold"
                              >
                                <Save size={10} className="mr-0.5" /> Save
                              </button>
                              <button
                                onClick={cancelEditCol}
                                className="h-6 px-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded"
                              >
                                <RotateCcw size={10} />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => startEditCol(g)}
                              className="h-6 px-2 text-[10px] text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded font-semibold"
                            >
                              Edit
                            </button>
                          )}
                        </th>
                      )
                    })
                  })}
                </tr>
              </thead>

              <tbody>
                {ROW_GROUPS.map((rg) =>
                  rg.rows.map((row, ri) => {
                    const isFirstInGroup = ri === 0
                    const isLastInGroup = ri === rg.rows.length - 1
                    const isBoolean = row.type === 'boolean'

                    return (
                      <tr
                        key={row.key}
                        className={[
                          'border-b border-slate-100 transition-colors hover:bg-slate-50/60',
                          isLastInGroup ? 'border-b-2 border-slate-200' : '',
                        ].join(' ')}
                      >
                        {/* ── Sticky left label column ── */}
                        <td className="sticky left-0 z-10 bg-white border-r border-slate-200 px-4 py-2 whitespace-nowrap min-w-[200px]">
                          <div className="flex items-center gap-2">
                            {isFirstInGroup && (
                              <span className={`text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded ${rg.bgClass} ${rg.textClass}`}>
                                {rg.label}
                              </span>
                            )}
                            <span className="text-xs font-semibold text-slate-700 pl-1">
                              {row.label}
                            </span>
                          </div>
                        </td>

                        {/* ── Data cells ── */}
                        {displayCats.map((cat) => {
                          const isCollapsed = !searchActive && collapsedCats[cat.id]
                          if (isCollapsed) {
                            return (
                              <td
                                key={cat.id}
                                className="border-r border-slate-200 bg-slate-50/50"
                              />
                            )
                          }
                          return (cat.guidelines ?? []).map((g, gi) => {
                            const isEditing = editingColId === g.id
                            const val = isEditing ? editColValues[row.key] : g[row.key]
                            const isLastInCat = gi === (cat.guidelines.length - 1)

                            return (
                              <td
                                key={g.id}
                                className={[
                                  'px-3 py-2 text-center',
                                  row.key === 'min' ? 'bg-green-50/50' : '',
                                  row.key === 'max' ? 'bg-red-50/30' : '',
                                  isLastInCat ? 'border-r border-slate-200' : '',
                                ].join(' ')}
                              >
                                {isBoolean ? (
                                  isEditing ? (
                                    <input
                                      type="checkbox"
                                      checked={!!val}
                                      onChange={(e) => handleColChange(row.key, e.target.checked)}
                                      className="h-4 w-4 cursor-pointer accent-emerald-600"
                                    />
                                  ) : (
                                    <BoolDot value={!!val} />
                                  )
                                ) : isEditing ? (
                                  <input
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    value={val ?? ''}
                                    onChange={(e) => handleColChange(row.key, e.target.value)}
                                    className="h-6 w-16 bg-white border border-blue-400 text-slate-900 text-xs text-right px-1.5 rounded outline-none focus:ring-2 focus:ring-blue-300 tabular-nums mx-auto block"
                                  />
                                ) : (
                                  <span className={[
                                    'tabular-nums text-xs',
                                    fmtMoney(val) ? 'text-slate-800 font-medium' : 'text-slate-300',
                                  ].join(' ')}>
                                    {fmtMoney(val) ?? '—'}
                                  </span>
                                )}
                              </td>
                            )
                          })
                        })}
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
