import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import api from '../../lib/axios'
import Spinner from '../shared/Spinner'
import CrmSyncSummaryPanel from '../shared/CrmSyncSummaryPanel'

// Mirrors the set_stage(...) calls in debt_app/services/crm_vote_sync.py, in order.
const STAGES = [
  { key: 'Connecting to CRM', label: 'Connecting to CRM' },
  { key: 'Fetching aggregate vote counts', label: 'Fetching vote totals' },
  { key: 'Fetching latest vote per creditor', label: 'Fetching latest votes' },
  { key: 'Matching creditor names', label: 'Matching creditor names' },
  { key: 'Updating CreditorCriteria records', label: 'Updating general creditors' },
  { key: 'Updating CouncilRule records', label: 'Updating councils' },
  { key: 'Updating CountyCouncil records', label: 'Updating county councils' },
  { key: 'Done', label: 'Done' },
]

function stageIndex(stage) {
  const idx = STAGES.findIndex((s) => s.key === stage)
  return idx === -1 ? 0 : idx
}

function useElapsedSeconds(startedAt, running) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!running || !startedAt) return undefined
    const start = new Date(startedAt).getTime()
    const tick = () => setElapsed(Math.max(0, Math.round((Date.now() - start) / 1000)))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startedAt, running])
  return elapsed
}

/**
 * Manual "sync now" trigger for the CRM vote-summary sync — shows a step-by-step
 * progress list while running, and a summary panel once it finishes.
 */
export default function CrmSyncButton() {
  const [runId, setRunId] = useState(null)
  const [showResult, setShowResult] = useState(false)

  const triggerMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/api/v1/criteria/crm-sync/trigger/')
      return data
    },
    onSuccess: (data) => {
      setShowResult(false)
      setRunId(data.id)
    },
    onError: (error) => {
      // Treat "already running" (409) as "here's the in-progress run", not a failure.
      const existingId = error?.response?.data?.id
      if (error?.response?.status === 409 && existingId) {
        setShowResult(false)
        setRunId(existingId)
      }
    },
  })

  const statusQuery = useQuery({
    queryKey: ['crm-sync-status', runId],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/criteria/crm-sync/status/${runId}/`)
      return data
    },
    enabled: !!runId,
    refetchInterval: (query) => (query.state.data?.status === 'RUNNING' ? 1200 : false),
  })

  const run = statusQuery.data
  const isRunning = run?.status === 'RUNNING'
  const elapsed = useElapsedSeconds(run?.started_at, isRunning)
  const currentStageIdx = stageIndex(run?.stage)

  // Show the result panel once a run we're tracking finishes.
  useEffect(() => {
    if (run && run.status !== 'RUNNING') {
      setShowResult(true)
    }
  }, [run?.status])

  const handleClick = () => {
    setShowResult(false)
    triggerMutation.mutate()
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleClick}
          disabled={isRunning || triggerMutation.isPending}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-brand-navy text-white hover:bg-slate-800 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        >
          {isRunning && <Spinner size={16} />}
          {isRunning ? 'Syncing...' : 'Sync CRM Votes Now'}
        </button>
      </div>

      {isRunning && (
        <div className="w-80 rounded-lg border border-slate-200 bg-white shadow-sm px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Syncing CRM votes
            </span>
            <span className="text-xs tabular-nums text-slate-400">{elapsed}s</span>
          </div>
          <ol className="space-y-1.5">
            {STAGES.slice(0, -1).map((stage, idx) => {
              const done = idx < currentStageIdx
              const active = idx === currentStageIdx
              return (
                <li key={stage.key} className="flex items-center gap-2 text-xs">
                  {done && (
                    <span className="flex-none w-4 h-4 rounded-full bg-emerald-500 text-white flex items-center justify-center text-[10px] leading-none">
                      ✓
                    </span>
                  )}
                  {active && (
                    <span className="flex-none w-4 h-4 flex items-center justify-center">
                      <Spinner size={12} />
                    </span>
                  )}
                  {!done && !active && (
                    <span className="flex-none w-4 h-4 rounded-full border border-slate-200" />
                  )}
                  <span
                    className={
                      active
                        ? 'font-medium text-brand-navy'
                        : done
                        ? 'text-slate-400 line-through decoration-slate-300'
                        : 'text-slate-400'
                    }
                  >
                    {stage.label}
                  </span>
                </li>
              )
            })}
          </ol>
        </div>
      )}

      {showResult && <CrmSyncSummaryPanel run={run} className="w-96" />}
    </div>
  )
}
