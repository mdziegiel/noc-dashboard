// Inject CSS variables from a theme object into document.documentElement
export function applyTheme(themeVars) {
  if (!themeVars) return
  const root = document.documentElement
  Object.entries(themeVars).forEach(([key, value]) => {
    // Convert underscore keys to CSS variable names: card_background -> --card-background
    const cssVar = '--' + key.replace(/_/g, '-')
    root.style.setProperty(cssVar, value)
  })
}

// Determine which theme to use based on auto-switching config
export function resolveTheme(layout) {
  if (!layout) return layout?.theme
  if (!layout.autoTheme) return layout.theme
  const now = new Date()
  const hour = now.getHours()
  const dayStart = layout.dayStart ?? 6
  const nightStart = layout.nightStart ?? 20
  if (hour >= dayStart && hour < nightStart) {
    return layout.dayTheme || layout.theme
  }
  return layout.nightTheme || layout.theme
}
