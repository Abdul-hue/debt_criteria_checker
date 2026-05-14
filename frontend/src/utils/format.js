export const penceToGbp = (pence) => {
  if (pence == null) return '—'
  return `£${(pence / 100).toFixed(2)}`
}

export const formatDate = (isoString) => {
  if (!isoString) return '—'
  return new Date(isoString).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

export const formatDateTime = (isoString) => {
  if (!isoString) return '—'
  return new Date(isoString).toLocaleString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export const formatPercentage = (value) => {
  if (value == null) return '—'
  return `${Number(value).toFixed(0)}%`
}
