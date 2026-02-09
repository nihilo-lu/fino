export function formatCurrency(value, currency = 'CNY') {
  if (value === null || value === undefined) return '¥0.00'
  const formatted = parseFloat(value).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return currency === 'CNY' ? `¥${formatted}` : `${currency} ${formatted}`
}
