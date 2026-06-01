import { z } from 'zod'

export const ruleSchema = z.object({
  is_active: z.boolean(),
  severity: z.enum(['hard_block', 'flag', 'info']),
  threshold_value: z.number().nullable().optional(),
  description: z.string().optional(),
  implementation_notes: z.string().optional(),
  category: z.string().optional(),
  example_case: z.string().optional(),
  rejection_message: z.string().optional(),
  flag_message: z.string().optional(),
  is_creditor_specific: z.boolean().optional(),
  applies_to_creditors: z.array(z.string()).optional(),
  references: z.array(z.string()).optional(),
  execution_order: z.number().nullable().optional(),
  depends_on_rules: z.array(z.string()).optional(),
  related_rules: z.array(z.string()).optional(),
  last_reviewed: z.string().nullable().optional(),
  review_notes: z.string().optional(),
})
