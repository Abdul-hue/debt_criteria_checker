import { forwardRef } from 'react'
import clsx from 'clsx'
import * as Tooltip from '@radix-ui/react-tooltip'
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'

/**
 * Small, shared presentation primitives for the Lead Gen / criteria pages.
 * Built on the app's existing Tailwind palette (brand-navy, slate, green/amber/red)
 * so these pages match the rest of the CAT frontend without a second design system.
 */

const BUTTON_VARIANTS = {
  primary: 'bg-brand-navy text-white hover:bg-slate-800 focus-visible:ring-slate-700 shadow-sm',
  secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 hover:border-slate-400 focus-visible:ring-slate-500',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:ring-slate-500',
  success: 'bg-green-700 text-white hover:bg-green-800 focus-visible:ring-green-600 shadow-sm',
  danger: 'bg-white text-red-700 border border-red-300 hover:bg-red-50 hover:border-red-400 focus-visible:ring-red-500',
  dangerSolid: 'bg-red-700 text-white hover:bg-red-800 focus-visible:ring-red-600 shadow-sm',
}

const BUTTON_SIZES = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-11 px-5 text-sm gap-2',
}

export const Button = forwardRef(function Button(
  { variant = 'secondary', size = 'md', className, type = 'button', ...props }, ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={clsx(
        'inline-flex items-center justify-center rounded-md font-medium whitespace-nowrap transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
        'disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none',
        BUTTON_VARIANTS[variant], BUTTON_SIZES[size], className,
      )}
      {...props}
    />
  )
})

const CONTROL = 'block w-full rounded-md border bg-white text-sm text-slate-900 placeholder:text-slate-400 '
  + 'transition-colors focus:outline-none focus:ring-2 focus:ring-slate-500/30 focus:border-slate-500 '
  + 'disabled:bg-slate-50 disabled:text-slate-500'

export const TextInput = forwardRef(function TextInput({ className, invalid, size = 'md', ...props }, ref) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={clsx(CONTROL, size === 'lg' ? 'h-11 px-3.5' : 'h-10 px-3',
        invalid ? 'border-red-400 focus:ring-red-500/30 focus:border-red-500' : 'border-slate-300', className)}
      {...props}
    />
  )
})

export function SelectInput({ className, children, ...props }) {
  return (
    <select className={clsx(CONTROL, 'h-10 pl-3 pr-8 border-slate-300', className)} {...props}>
      {children}
    </select>
  )
}

export function TextArea({ className, ...props }) {
  return <textarea className={clsx(CONTROL, 'px-3 py-2 border-slate-300', className)} {...props} />
}

/** Label + control + optional hint/error, with the label correctly associated. */
export function Field({ id, label, hint, error, optional, children, className }) {
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-medium text-slate-800 mb-1.5">
        {label}
        {optional && <span className="ml-1 font-normal text-slate-500">(optional)</span>}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-xs text-red-700 flex items-center gap-1">
          <XCircle size={12} aria-hidden="true" /> {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-slate-500">{hint}</p>
      ) : null}
    </div>
  )
}

/** Plain white surface. Sections inside it are separated by rules, not more cards. */
export function Card({ as: Tag = 'section', className, children, ...props }) {
  return (
    <Tag className={clsx('bg-white border border-slate-200 rounded-lg shadow-[0_1px_2px_rgba(15,23,42,0.04)]', className)} {...props}>
      {children}
    </Tag>
  )
}

export function CardHeader({ title, description, actions, id, className }) {
  return (
    <div className={clsx('flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 py-4 border-b border-slate-200', className)}>
      <div className="min-w-0">
        <h2 id={id} className="text-[15px] font-semibold text-slate-900">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  )
}

export function PageHeader({ title, description, actions }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500 max-w-2xl">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-end gap-3">{actions}</div>}
    </div>
  )
}

/**
 * Colour is never the only signal: every tone carries its own icon and the
 * text label is always rendered.
 */
export const TONES = {
  success: { text: 'text-green-800', bg: 'bg-green-50', border: 'border-green-200', icon: 'text-green-600', Icon: CheckCircle2 },
  warning: { text: 'text-amber-900', bg: 'bg-amber-50', border: 'border-amber-200', icon: 'text-amber-600', Icon: AlertTriangle },
  danger: { text: 'text-red-800', bg: 'bg-red-50', border: 'border-red-200', icon: 'text-red-600', Icon: XCircle },
  neutral: { text: 'text-slate-700', bg: 'bg-slate-50', border: 'border-slate-200', icon: 'text-slate-500', Icon: Info },
}

export function StatusPill({ tone = 'neutral', icon = true, children, className }) {
  const t = TONES[tone] || TONES.neutral
  const { Icon } = t
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium', t.bg, t.border, t.text, className)}>
      {icon && <Icon size={13} aria-hidden="true" className={clsx('shrink-0', t.icon)} />}
      {children}
    </span>
  )
}

/** Tooltip for controls whose purpose isn't obvious from a glance. */
export function Hint({ label, children, side = 'bottom' }) {
  return (
    <Tooltip.Root delayDuration={300}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-xs rounded-md bg-slate-900 px-2.5 py-1.5 text-xs text-white shadow-lg"
        >
          {label}
          <Tooltip.Arrow className="fill-slate-900" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}

export const HintProvider = Tooltip.Provider
