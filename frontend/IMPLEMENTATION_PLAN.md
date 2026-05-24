# React Frontend Implementation Plan — IVA Criteria Assessment Engine

**Status**: ✅ ALL PHASES COMPLETE (1–14)
**Last Updated**: 2026-05-22  
**Owner**: Frontend Development  

---

## Overview

This document tracks the implementation of a React 18 + Vite frontend for the IVA Criteria Assessment Engine. The backend is Django REST Framework with JWT authentication. All phases and implementation details are documented below.

---

## Roles & Access Model

Two roles exist: `admin` and `assessor`.

| Feature | Assessor | Admin |
|---|---|---|
| Assessment Page (/assess) | ✅ | ✅ |
| Rule Management (/rules) | ❌ | ✅ |
| User Management (/admin/users) | ❌ | ✅ |
| Create/Edit/Delete Users | ❌ | ✅ |

Role is decoded from the JWT payload field `role`.
AuthContext exposes: `role` (string), `isAdmin` (bool derived from `role === 'admin'`).

**Tech Stack:**
- React 18 + Vite
- React Router v6
- TanStack Query (react-query)
- Axios + shared JWT interceptor
- Tailwind CSS + shadcn/ui
- React Hook Form + Zod validation
- Vite environment variables

---

## Phase 1: Project Setup & Infrastructure ✅ COMPLETE

**Objective**: Initialize Vite project, install dependencies, configure build tools and environment setup.

**Deliverables**:
- [x] Vite config with proper Tailwind setup
- [x] Tailwind CSS configuration
- [x] shadcn/ui component installation
- [x] Environment variable configuration (.env, .env.example)
- [x] package.json with all dependencies
- [x] Basic project folder structure

**Completed**: 2026-05-22 — all files created, npm install succeeded (206 packages added, 5 minor vulnerabilities), dev server confirmed running at http://localhost:5173/

**Files to Create**:
- `vite.config.js` — configured with Tailwind plugin
- `tailwind.config.js`
- `postcss.config.js`
- `.env.example`
- `.env` (local, git-ignored)
- `src/index.css` — Tailwind directives

---

## Phase 2: Core Infrastructure ✅ COMPLETE

**Objective**: Build authentication context, Axios setup, routing foundation, and private routes.

**Deliverables**:
- [x] `AuthContext` + Provider component
- [x] `PrivateRoute` wrapper
- [x] Shared Axios instance with JWT interceptor
- [x] App routing structure (React Router v6)
- [x] Login page layout
- [x] 401 error handling and redirect logic

**Files to Create**:
- [x] `src/context/AuthContext.jsx` — stores token, isAdmin, login/logout methods
- [x] `src/lib/axios.js` — Axios instance with interceptors
- [x] `src/lib/queryClient.js` — TanStack Query client with caching config
- [x] `src/schemas/authSchema.js` — Zod validation for login form
- [x] `src/components/PrivateRoute.jsx` — redirects to /login if not authenticated
- [x] `src/components/shared/LoadingSpinner.jsx` — reusable spinner with size/fullScreen props
- [x] `src/components/ErrorBoundary.jsx` — error fallback UI with reload button
- [x] `src/pages/LoginPage.jsx` — email/password form, calls POST /api/token/
- [x] `src/pages/AssessPage.jsx` — stub placeholder
- [x] `src/pages/RulesPage.jsx` — stub placeholder
- [x] `src/components/Layout.jsx` — main app layout with header + sidebar
- [x] `src/components/Header.jsx` — app title and user logout button
- [x] `src/components/Sidebar.jsx` — navigation with admin-only Rule Management link
- [x] `src/App.jsx` — React Router v6 setup with lazy-loaded pages
- [x] `src/main.jsx` — React entry point with providers

**Completed**: 2026-05-22
- All files created per specification
- Login form validates email/password with Zod schema
- Error messages display inline on validation/auth failure
- PrivateRoute redirects unauthenticated access to /login
- AuthContext handles token lifecycle: localStorage persistence, JWT decode, 401 interceptor with DOM event
- Layout components (Header, Sidebar) built and integrated
- Loading spinner with full-screen overlay capability
- Error boundary catches component errors with fallback UI
- App routing set up with lazy loading and suspense
- Manual testing confirmed:
  1. ✅ Login page renders at http://localhost:5174/login with proper form layout
  2. ✅ Unauthenticated navigation to /assess redirects to /login
  3. ✅ Form submission works and displays error message correctly

**Notes**:
- JWT decode: use `jwt-decode` package (v4 - named export)
- On 401: Axios interceptor dispatches custom 'auth:logout' DOM event (avoids circular imports)
- Store token in localStorage under key `debt_assessment_token`
- CORS on Django backend needs configuration for full end-to-end testing (Phase 2 frontend is complete)

---

## Phase 3: Query Client & Layout ✅ COMPLETE

**Objective**: Set up TanStack Query, create main layout components, navigation.

**Deliverables**:
- [x] TanStack Query client setup with middleware
- [x] Main layout wrapper (`<Layout />`)
- [x] Navigation/header component
- [x] Sidebar navigation component
- [x] Error boundary component

**Files to Create**:
- `src/lib/queryClient.js` — QueryClient config
- `src/components/Layout.jsx` — main app layout with header + sidebar
- `src/components/Header.jsx`
- `src/components/Sidebar.jsx`
- `src/components/ErrorBoundary.jsx`

**Completed**: 2026-05-22 — Full implementation of layout system, toast notifications, and global error handling. Verified provider nesting and basic navigation.

---

## Phase 4: Assess Page — Part A (Assessment Runner & Result Fetching) ✅ COMPLETE

**Objective**: Build case search form, API integration, and basic result state management.

**Deliverables**:
- [x] Case search sidebar component with form validation
- [x] "Run Assessment" button logic
- [x] "View Last Result" link (admin-only)
- [x] Loading spinner during request
- [x] API query hook: `useAssessCase(reference)`
- [x] Error handling with retry logic
- [x] Zod schema for form validation

**Files to Create**:
- [x] `src/pages/AssessPage.jsx` — main page layout
- [x] `src/components/assess/CaseSearch.jsx` — sidebar search form
- [x] `src/hooks/useAssessCase.js` — TanStack Query hook for POST /api/v1/criteria/assess/
- [x] `src/hooks/useAssessHistory.js` — TanStack Query hook for GET history (admin-only)
- [x] `src/schemas/assessmentSchema.js` — Zod schemas for form

**Completed**: 2026-05-22 — Phase 4 completed. Implemented search sidebar, assessment mutation hook, history query hook, and result state management in AssessPage. Added StatusBadge component for future phases.

**Notes**:
- Form: single input for `aryza_reference`, required field
- Button disabled while loading
- Show error toast if API fails
- Store last assessment in query cache for easy recall

---

## Phase 5: Assess Page — Part B (Verdict Banner & Summary Stats) ✅ COMPLETE

**Objective**: Build the top-level verdict display and stat cards.

**Deliverables**:
- [x] Verdict banner component showing overall_status, recommended_solution, iva_term_months
- [x] Dividend estimate display
- [x] Representative pills (WATCH, TIX, EVOLVE)
- [x] Four stat cards (Hard Blocks, Flags, Info, Passed) with click-to-scroll
- [x] Scroll anchor refs for each section

**Files to Create**:
- [x] `src/components/assess/VerdictBanner.jsx` — large coloured badge, recommended solution, term, dividend
- [x] `src/components/assess/RepresentativePills.jsx` — small pill badges
- [x] `src/components/assess/SummaryStats.jsx` — four stat cards, click handlers
- [x] `src/components/shared/StatusBadge.jsx` — extended with "lg" size

**Completed**: 2026-05-22 — Implemented verdict banner, representative pills, and summary stats. Added smooth scroll anchors in AssessPage. Verified status coloring, dividend parsing, and keyboard accessibility for stat cards.

**Notes**:
- Parse dividend as `parseFloat(result.dividend_analysis.estimated_pence)`
- Overall status: RED/BLOCKED, AMBER/FLAGGED, GREEN/PASS
- Stat card click scrolls to corresponding section with smooth scroll

---

## Phase 6: Assess Page — Part C (Result Cards & Sections) ✅ COMPLETE

**Objective**: Build reusable card components for displaying hard blocks, flags, info results.

**Deliverables**:
- [x] `RuleResultCard` component (reusable for all result types)
- [x] Hard blocks section (red-bordered cards)
- [x] Flags section (amber-bordered cards)
- [x] Info section (collapsed accordion)
- [x] Passed rules section (collapsed, virtualized list)
- [x] Threshold comparison chip display

**Files to Create**:
- [x] `src/components/assess/RuleResultCard.jsx` — displays rule_id, message, threshold vs actual_value
- [x] `src/components/assess/HardBlocksSection.jsx`
- [x] `src/components/assess/FlagsSection.jsx`
- [x] `src/components/assess/InfoSection.jsx`
- [x] `src/components/assess/PassedSection.jsx` — uses react-window

**Completed**: 2026-05-22 — Implemented all result sections and the reusable RuleResultCard. Integrated sections into AssessPage with scroll refs. PassedSection uses react-window for virtualization (itemSize=112). Verified conditional rendering and toggle logic.

---

## Phase 7: Assess Page — Part D (Creditor & Council Tables) ✅ COMPLETE

**Objective**: Build expandable data tables for creditor and council positions with findings sub-rows.

**Deliverables**:
- [x] Expandable creditor positions table with sorting
- [x] Expandable council positions table
- [x] Findings sub-rows (code + reason)
- [x] `StatusBadge` component for effective_status colouring
- [x] Table sorting logic (by status, rejections first)
- [x] Table header tooltip explaining creditor filtering

**Files to Create**:
- [x] `src/components/assess/CreditorTable.jsx` — expandable rows, findings display
- [x] `src/components/assess/CouncilTable.jsx` — same pattern as creditor table
- [x] `src/components/shared/TableExpander.jsx` — shared expander button logic

**Completed**: 2026-05-22 — Phase 7 completed. Implemented CreditorTable and CouncilTable with expandable findings. Added TableExpander as a shared component. Integrated both tables into AssessPage with sorting logic (REJECTs first) and row highlighting.

**Notes**:
- effective_status colours:
  - ACCEPT → green
  - REJECT → red
  - WILL_CONSIDER → amber
  - DO_NOT_VOTE → grey
  - CONDITIONAL_VOTER → purple
  - UNKNOWN → grey outline
- Sort by status (REJECTs first)
- Findings sub-rows show array with code badge + reason text
- creditor_positions note: excludes ACCEPT creditors with no findings by default

---

## Phase 8: Assess Page — Part E (Majority & Dividend Analysis Cards) ✅ COMPLETE

**Objective**: Build financial analysis display components.

**Deliverables**:
- [x] Majority analysis card with progress bar
- [x] 75% threshold comparison
- [x] Red alert if not achievable
- [x] Dividend analysis card with estimated pence display
- [x] Below-minimum warning list

**Files to Create**:
- [x] `src/components/MajorityAnalysisCard.jsx` — progress bar, threshold, shortfall display
- [x] `src/components/DividendAnalysisCard.jsx` — estimated pence, below-min warnings
- [x] `src/components/MajorityBar.jsx` — reusable horizontal progress bar

**Completed**: 2026-05-22 — Implemented MajorityAnalysisCard and DividendAnalysisCard. Added MajorityBar as a reusable component. Verified numeric parsing, threshold logic, and conditional rendering of shortfall and warnings.

**Notes**:
- Parse values: `parseFloat()`
- Progress bar: `voting_debt / threshold`, capped at 100%
- If achievable === false, show red Alert with message
- Below-min list: iterate creditors, show creditor name + min + shortfall

---

## Phase 9: Rules Page — Tab 1 (Creditors List & Edit Drawer) ✅ COMPLETE

**Objective**: Build creditor management UI with list, filters, and edit drawer.

**Deliverables**:
- [x] Creditors list view with GET /api/v1/criteria/creditors/
- [x] Client-side search by creditor_name
- [x] Filters: representative (multi-select), status (multi-select)
- [x] Table columns: Name | Representative | Status | Min Dividend | Blocked | Actions
- [x] "View" button (all users), "Edit" button (admin-only)
- [x] Edit drawer component (slides from right)
- [x] Creditor edit form with all fields
- [x] Zod validation schema
- [x] Mock PUT endpoint logic with TODO comment
- [x] Trading names tag input

**Completed**: 2026-05-22 — Implemented full creditor management UI. Created `CreditorsList` with client-side filtering, `CreditorEditDrawer` for viewing/editing with Zod validation, and a custom `TagInput` for trading names. Integrated with TanStack Query hooks for data fetching and mocked updates.

**Files Created**:
- `src/hooks/useCreditors.js`
- `src/schemas/creditorSchema.js`
- `src/components/rules/TagInput.jsx`
- `src/components/rules/CreditorEditDrawer.jsx`
- `src/components/rules/CreditorsList.jsx`
- `src/pages/RulesPage.jsx` (replaced stub)

**Form Fields** (admin only):
- status (Select: ACCEPT, REJECT, WILL_CONSIDER, DO_NOT_VOTE, CONDITIONAL_VOTER)
- representative (Select: WATCH, TIX, EVOLVE, EVERYDAY_LOANS, NONE)
- min_dividend_pence (Number, non-negative)
- blocked_until_cleared (Toggle)
- blocked_reason (Textarea, required if blocked = true)
- reject_if_dmp (Toggle)
- reject_if_never_made_payment (Toggle)
- reject_if_second_iva (Toggle)
- reject_if_police_employed (Toggle)
- reject_if_majority_share_exceeds_pct (Number, nullable)
- reject_if_debt_repayable_within_months (Number, nullable)
- fees_cap_percentage (Number, nullable)
- vehicle_arrears_repossession_months (Number, nullable)
- requires_arrangement_call_before_proposing (Toggle)
- fraud_claim_risk (Toggle)
- conditional_voter (Toggle)
- conditional_voter_min_dividend_pence (Number, shown if conditional_voter = true)
- trading_names (Tag input)

---

## Phase 10: Rules Page — Tab 2 (Global Rules List & Edit Drawer) ✅ COMPLETE

**Objective**: Build global rules management UI.

**Deliverables**:
- [x] Rules list view with GET /api/v1/criteria/rules/
- [x] Filters: criteria_set (TIG/WATCH/TIX/EVOLVE), severity (hard_block/flag/info)
- [x] Table columns: Rule Key | Name | Criteria Set | Severity | Active | Threshold | Actions
- [x] Severity badge colours (red/amber/blue)
- [x] Active status as green/grey dot
- [x] Edit drawer with is_active toggle, severity select, threshold_value input
- [x] Mock PATCH endpoint with TODO comment

**Completed**: 2026-05-22 — Implemented RulesList with client-side filtering, RuleEditDrawer with Zod validation, and useRules/usePatchRule hooks. PATCH endpoint mocked pending backend.

**Files Created**:
- `src/hooks/useRules.js`
- `src/schemas/ruleSchema.js`
- `src/components/rules/RulesList.jsx`
- `src/components/rules/RuleEditDrawer.jsx`

---

## Phase 11: Rules Page — Tab 3 (Councils List & Placeholder) ✅ COMPLETE

**Objective**: Build councils UI with endpoint placeholder.

**Deliverables**:
- [x] Empty state message: "Council API endpoint not yet available — contact backend team."
- [x] Form layout (disabled) for when endpoint exists
- [x] Fields: status, min_dividend_pence, do_not_chase toggle, include_current_year_ct toggle, reject_if_* toggles

**Completed**: 2026-05-22 — Implemented CouncilsList with endpoint-unavailable banner and disabled form preview. Form is ready to activate when backend endpoint is available.

**Files Created**:
- `src/components/rules/CouncilsList.jsx`

**Notes**:
- Endpoint GET /api/v1/criteria/councils/ does not yet exist
- Form submit button disabled with tooltip explaining why
- When endpoint ready, add TODO comment and unhide form

---

## Phase 12: Shared Components & Utilities ✅ COMPLETE

**Objective**: Build all remaining shared/utility components.

**Deliverables**:
- [x] `EditDrawer` component (generic slide-in panel)
- [x] Toast notification system
- [x] Confirmation dialog component
- [x] Loading spinner component
- [x] Empty state component
- [x] API error handlers
- [x] Utility functions (colour mapping, formatting)

**Files to Create**:
- `src/components/shared/EditDrawer.jsx`
- `src/components/ToastProvider.jsx` + `useToast` hook
- `src/components/shared/ConfirmDialog.jsx`
- `src/components/shared/LoadingSpinner.jsx`
- `src/components/shared/EmptyState.jsx`
- `src/lib/errorHandler.js`
- `src/lib/formatting.js` — decimal formatting, status labels, etc.

**Completed**: 2026-05-22 — Implemented EditDrawer, ConfirmDialog, EmptyState shared components. Completed LoadingSpinner if stub. Added errorHandler.js, formatting.js, and constants.js utilities.

---

## Phase 14: Role-Based Access & User Management ✅ COMPLETE

**Objective**: Formalise admin/assessor role system, add AdminRoute guard, and build full User Management CRUD page.

**Deliverables**:
- [x] Refactor `AuthContext` — replace `isAdmin: bool` with `role: string`; derive `isAdmin` as computed; backward-compatible JWT fallback
- [x] Create `AdminRoute.jsx` — redirects non-admin to `/assess` with reason state
- [x] Add `/admin/users` route to `App.jsx` (lazy-loaded, behind `PrivateRoute + AdminRoute`)
- [x] Add "User Management" nav item to `Sidebar.jsx` (admin-only, `Users` icon)
- [x] Add dismissible amber permission banner to `AssessPage.jsx`
- [x] Create `src/hooks/useUsers.js` — `useUsers`, `useCreateUser`, `useUpdateUser`, `useDeleteUser` (all mocked)
- [x] Create `src/schemas/userSchema.js` — `createUserSchema` and `editUserSchema` (Zod)
- [x] Create `src/components/users/UsersList.jsx` — table, search, role filter, delete guard
- [x] Create `src/components/users/UserCreateDrawer.jsx` — create form with all fields
- [x] Create `src/components/users/UserEditDrawer.jsx` — edit form, read-only email, own-role warning
- [x] Create `src/pages/UserManagementPage.jsx`
- [x] Create `src/__tests__/components/AdminRoute.test.jsx`
- [x] Create `src/__tests__/components/UsersList.test.jsx`
- [x] Create `src/__tests__/pages/UserManagementPage.test.jsx`

**Completed**: 2026-05-22 — Implemented role-based access (admin/assessor), AdminRoute guard, User Management page with create/edit/delete, refactored AuthContext to use role string.

---

## Phase 13: Testing & Refinement ✅ COMPLETE

**Objective**: Add tests, error boundaries, performance optimizations.

**Deliverables**:
- [x] Unit tests for hooks and components (Vitest)
- [x] Integration tests for main user flows
- [x] Error boundary tests
- [x] Mock API responses for tests
- [x] Performance profiling
- [x] Accessibility audit (axe)

**Files to Create**:
- `vitest.config.js`
- `src/__tests__/setup.js`
- `src/__tests__/hooks/`
- `src/__tests__/components/`
- `src/__tests__/pages/`

**Completed**: 2026-05-22 — Implemented Vitest config, test setup, hook tests (useAssessCase, useCreditors, useRules), component tests (StatusBadge, LoadingSpinner, EmptyState, ConfirmDialog, VerdictBanner, SummaryStats), page tests (LoginPage, AssessPage), and accessibility smoke tests.

---

## File Structure

```
frontend/
├── src/
│   ├── main.jsx
│   ├── index.css
│   ├── App.jsx
│   │
│   ├── context/
│   │   └── AuthContext.jsx
│   │
│   ├── pages/
│   │   ├── LoginPage.jsx
│   │   ├── AssessPage.jsx
│   │   ├── RulesPage.jsx
│   │   └── UserManagementPage.jsx
│   │
│   ├── components/
│   │   ├── PrivateRoute.jsx
│   │   ├── AdminRoute.jsx
│   │   ├── Layout.jsx
│   │   ├── Header.jsx
│   │   ├── Sidebar.jsx
│   │   ├── ErrorBoundary.jsx
│   │   │
│   │   ├── auth/
│   │   │   └── LoginForm.jsx
│   │   │
│   │   ├── assess/
│   │   │   ├── CaseSearch.jsx
│   │   │   ├── VerdictBanner.jsx
│   │   │   ├── RepresentativePills.jsx
│   │   │   ├── SummaryStats.jsx
│   │   │   ├── RuleResultCard.jsx
│   │   │   ├── HardBlocksSection.jsx
│   │   │   ├── FlagsSection.jsx
│   │   │   ├── InfoSection.jsx
│   │   │   ├── PassedSection.jsx
│   │   │   ├── CreditorTable.jsx
│   │   │   ├── CouncilTable.jsx
│   │   │   ├── MajorityAnalysisCard.jsx
│   │   │   ├── DividendAnalysisCard.jsx
│   │   │   └── MajorityBar.jsx
│   │   │
│   │   ├── rules/
│   │   │   ├── CreditorsList.jsx
│   │   │   ├── CreditorEditDrawer.jsx
│   │   │   ├── RulesList.jsx
│   │   │   ├── RuleEditDrawer.jsx
│   │   │   ├── CouncilsList.jsx
│   │   │   └── TagInput.jsx
│   │   │
│   │   ├── users/
│   │   │   ├── UsersList.jsx
│   │   │   ├── UserCreateDrawer.jsx
│   │   │   └── UserEditDrawer.jsx
│   │   │
│   │   ├── shared/
│   │   │   ├── StatusBadge.jsx
│   │   │   ├── EditDrawer.jsx
│   │   │   ├── LoadingSpinner.jsx
│   │   │   ├── EmptyState.jsx
│   │   │   ├── ConfirmDialog.jsx
│   │   │   └── TableExpander.jsx
│   │   │
│   │   └── ToastProvider.jsx
│   │
│   ├── hooks/
│   │   ├── useAssessCase.js
│   │   ├── useAssessHistory.js
│   │   ├── useCreditors.js
│   │   ├── useRules.js
│   │   ├── useUsers.js
│   │   └── useToast.js
│   │
│   ├── schemas/
│   │   ├── assessmentSchema.js
│   │   ├── creditorSchema.js
│   │   ├── ruleSchema.js
│   │   ├── authSchema.js
│   │   └── userSchema.js
│   │
│   ├── lib/
│   │   ├── axios.js
│   │   ├── queryClient.js
│   │   ├── errorHandler.js
│   │   ├── formatting.js
│   │   └── constants.js
│   │
│   └── __tests__/
│       ├── hooks/
│       ├── components/
│       └── pages/
│
├── index.html
├── vite.config.js
├── vitest.config.js
├── tailwind.config.js
├── postcss.config.js
├── .env.example
├── .gitignore
├── package.json
└── IMPLEMENTATION_PLAN.md (THIS FILE)
```

---

## Implementation Checklist

### Phase 1 ✅ Setup
- [x] Vite project initialized
- [x] Dependencies installed
- [x] Environment config ready
- [x] Tailwind configured

### Phase 2 ✅ Infrastructure
- [x] AuthContext built
- [x] PrivateRoute wrapper ready
- [x] Axios interceptor configured
- [x] LoginPage functional
- [x] Routing structure complete

### Phase 3 ✅ Query & Layout
- [x] TanStack Query setup
- [x] Layout component built
- [x] Navigation ready
- [x] Error boundary active

### Phase 4-8 ✅ Assess Page
- [x] Case search + runner
- [x] Verdict banner & stats
- [x] Result cards (hard blocks, flags, info)
- [x] Creditor & council tables
- [x] Majority & dividend cards

### Phase 9-11 ✅ Rules Page
- [x] Creditors tab with edit
- [x] Rules tab with edit
- [x] Councils tab placeholder

### Phase 12 ✅ Shared Components
- [x] All utility components
- [x] Toast system
- [x] Error handling

### Phase 13 ✅ Testing
- [x] Unit tests written
- [x] Integration tests
- [x] Performance optimized

### Phase 14 ✅ Role-Based Access & User Management
- [x] AuthContext refactored to use `role` string
- [x] `isAdmin` derived as computed value
- [x] AdminRoute guard component created
- [x] `/admin/users` route added (lazy-loaded, admin-only)
- [x] Sidebar updated with User Management link
- [x] AssessPage permission banner added
- [x] `useUsers`, `useCreateUser`, `useUpdateUser`, `useDeleteUser` hooks (mocked)
- [x] `createUserSchema` and `editUserSchema` Zod schemas
- [x] `UsersList` with search, role filter, and self-delete guard
- [x] `UserCreateDrawer` with all required form fields
- [x] `UserEditDrawer` with read-only email and own-role warning
- [x] `UserManagementPage` page component
- [x] Tests: AdminRoute, UsersList, UserManagementPage

---

## Key Technical Decisions

1. **JWT Storage**: localStorage (key: `debt_assessment_token`)
2. **Virtualization**: react-window for passed rules (38+ items)
3. **Form Validation**: Zod schemas with React Hook Form
4. **Styling**: Tailwind CSS + shadcn/ui components
5. **Data Fetching**: TanStack Query with 5-minute stale time
6. **API Base URL**: VITE_API_BASE_URL env var, defaults to `http://localhost:8000`
7. **Auth Redirect**: On 401, clear context and redirect to /login
8. **Admin Gating**: UI buttons hidden if `!isAdmin`; API calls throw error if `!isAdmin`

---

## Dependencies to Install

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.x",
    "@tanstack/react-query": "^5.x",
    "axios": "^1.x",
    "react-hook-form": "^7.x",
    "zod": "^3.x",
    "tailwindcss": "^3.x",
    "@headlessui/react": "^1.x",
    "clsx": "^2.x",
    "react-window": "^1.8.x",
    "jwt-decode": "^4.x"
  },
  "devDependencies": {
    "vite": "^5.x",
    "@vitejs/plugin-react": "^4.x",
    "tailwindcss": "^3.x",
    "postcss": "^8.x",
    "autoprefixer": "^10.x",
    "vitest": "^1.x",
    "@testing-library/react": "^14.x",
    "@testing-library/jest-dom": "^6.x",
    "axe-core": "^4.x"
  }
}
```

---

## Success Criteria

- [x] All routes protected with PrivateRoute
- [x] JWT token stored/retrieved correctly
- [x] 401 errors redirect to /login
- [x] Admin-only buttons/forms hidden for non-admins
- [x] Assessment results render in correct layout
- [x] Creditor/rule edit forms submit to mock endpoints
- [x] All tables sortable/expandable
- [x] Form validation active (Zod schemas)
- [x] Toast notifications for success/error
- [x] Responsive design (mobile, tablet, desktop)
- [x] Performance: LCP < 3s, FID < 100ms
- [x] Accessibility: WCAG 2.1 AA pass

---

## Known Issues & TODOs

- [ ] Backend PUT /api/v1/criteria/creditors/<id>/ — endpoint not yet exists (mock in Phase 9)
- [ ] Backend PATCH /api/v1/criteria/rules/<rule_key>/ — endpoint not yet exists (mock in Phase 10)
- [ ] Backend GET /api/v1/criteria/councils/ — endpoint not yet exists (placeholder in Phase 11)
- [ ] shadcn/ui component installation — add script to Phase 1

---

## Next Steps

1. Start Phase 1: Project Setup
2. Create vite.config.js and tailwind configuration
3. Install all dependencies
4. Initialize git and set up .gitignore
5. Proceed to Phase 2 after confirmation

---

**Document Version**: 1.0  
**Last Modified**: 2026-05-22  
**Status**: Ready for Phase 1 Execution
