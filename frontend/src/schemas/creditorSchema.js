import { z } from 'zod'

export const creditorSchema = z.object({
  status: z.enum(['ACCEPT', 'REJECT', 'WILL_CONSIDER', 'DO_NOT_VOTE', 'CONDITIONAL_VOTER']),
  representative: z.enum(['WATCH', 'TIX', 'EVOLVE', 'EVERYDAY_LOANS', 'NONE']),
  min_dividend_pence: z.number({ invalid_type_error: 'Must be a number' }).nullable().optional(),
  dividend_notes: z.string().optional().nullable(),
  blocked_until_cleared: z.boolean(),
  blocked_reason: z.string().optional(),
  reject_if_dmp: z.boolean(),
  reject_if_never_made_payment: z.boolean(),
  reject_if_second_iva: z.boolean(),
  reject_if_police_employed: z.boolean(),
  reject_if_majority_share_exceeds_pct: z.number().nullable().optional(),
  reject_if_debt_repayable_within_months: z.number().int().nullable().optional(),
  fees_cap_percentage: z.number().nullable().optional(),
  vehicle_arrears_repossession_months: z.number().int().nullable().optional(),
  requires_arrangement_call_before_proposing: z.boolean(),
  fraud_claim_risk: z.boolean(),
  conditional_voter: z.boolean(),
  conditional_voter_min_dividend_pence: z.number().nullable().optional(),
  trading_names: z.array(z.string()).optional(),
  contact_name: z.string().optional().nullable(),
  contact_email: z.string().email('Invalid email').or(z.literal('')).optional().nullable(),
  contact_phone: z.string().optional().nullable(),
  criteria_notes: z.string().optional().nullable(),
  raw_updated_criteria: z.string().optional().nullable(),
}).superRefine((data, ctx) => {
  if (data.blocked_until_cleared && !data.blocked_reason?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['blocked_reason'],
      message: 'Blocked reason is required when creditor is blocked.',
    })
  }
  if (data.conditional_voter && (data.conditional_voter_min_dividend_pence == null)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['conditional_voter_min_dividend_pence'],
      message: 'Minimum dividend required for conditional voter.',
    })
  }
})
