import { z } from 'zod'

export const assessmentFormSchema = z.object({
  aryza_reference: z.string()
    .min(1, 'Case reference is required')
    .max(100, 'Reference too long')
    .trim(),
})
