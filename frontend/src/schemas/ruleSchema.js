import { z } from 'zod'

export const ruleSchema = z.object({
  is_active: z.boolean(),
  severity: z.enum(['hard_block', 'flag', 'info']),
  threshold_value: z.number().nullable().optional(),
  override_message: z.string().nullable().optional(),
})
