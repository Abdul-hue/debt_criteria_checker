import { z } from 'zod'

const baseUserSchema = z.object({
  email: z.string().email('Must be a valid email'),
  first_name: z.string().min(1, 'First name is required'),
  last_name: z.string().min(1, 'Last name is required'),
  role: z.enum(['admin', 'assessor'], { required_error: 'Role is required' }),
  is_active: z.boolean().default(true),
})

export const createUserSchema = baseUserSchema
  .extend({
    username: z
      .string()
      .min(3, 'Username must be at least 3 characters')
      .regex(/^\S+$/, 'Username cannot contain spaces'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirmPassword: z.string().min(1, 'Please confirm your password'),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  })

export const editUserSchema = baseUserSchema.extend({
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .optional()
    .or(z.literal('')),
})
