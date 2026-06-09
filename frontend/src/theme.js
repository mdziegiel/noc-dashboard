// Theme system — now uses data-theme attribute on <html> / <body>
// to match generate_dashboard.py's CSS architecture exactly.
// The reference CSS selects themes via [data-theme='light'], [data-theme='midnight'], etc.

export function applyTheme(themeVars) {
  // No-op: theme is applied via data-theme attribute in App.jsx
}

export function resolveTheme(layout) {
  if (!layout) return layout?.theme
  if (!layout.autoTheme) return layout.theme
  const hour = new Date().getHours()
  const dayStart = layout.dayStart ?? 7
  const nightStart = layout.nightStart ?? 19
  if (hour >= dayStart && hour < nightStart) return layout.dayTheme || layout.theme
  return layout.nightTheme || layout.theme
}
