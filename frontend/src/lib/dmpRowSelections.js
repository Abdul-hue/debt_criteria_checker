// Shared helpers for the per-creditor-row DMP dropdown selections
// (Part 3 of the Aryza-only DMP redesign). Used by both AssessPage.jsx
// (to seed the PCN private-parking default) and CriteriaReport.jsx (to
// render the dropdowns).

// Water suppliers — DEBT_TYPE_UTILITY rows matching one of these get a
// single "Current water bill" toggle instead of a current/previous split
// (water doesn't have a current/previous distinction — Musa's rule).
export const WATER_SUPPLIER_NAMES = [
  'thames water', 'anglian water', 'severn trent', 'united utilities',
  'yorkshire water', 'wessex water', 'welsh water', 'south west water',
  'southern water', 'portsmouth water', 'bristol water', 'ses water',
  'south staffs water', 'affinity water', 'cambridge water',
  'south east water', 'northumbrian water', 'bournemouth water',
]

// Mirrors _PRIVATE_PARKING_NAMES in criteria_engine.py:160-192 — used to
// pre-select "Private" on a PCN row's dropdown; still overridable.
export const PRIVATE_PARKING_NAMES = [
  'parkingeye', 'excel parking services', 'euro car parks', 'ukpc',
  'uk parking control', 'civil enforcement', 'ncp', 'national car parks',
  'smart parking', 'vcs', 'vehicle control services',
  'gemini parking solutions', 'premier park', 'mil collections',
  'highview parking', 'aps parking', 'britannia parking', 'aos parking',
  'your parking space',
]

export function isWaterSupplier(creditorName) {
  const n = (creditorName || '').toLowerCase()
  return WATER_SUPPLIER_NAMES.some((w) => n.includes(w))
}

export function isPrivateParkingOperator(creditorName) {
  const n = (creditorName || '').toLowerCase()
  return PRIVATE_PARKING_NAMES.some((p) => n.includes(p))
}

export function creditorRowKey(creditor) {
  return `${creditor.creditor_name || creditor.original_aryza_name || ''}::${creditor.debt_type_normalised || ''}`
}
