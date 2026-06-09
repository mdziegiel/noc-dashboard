// Theme system — uses data-theme attribute on <html>/<body>
// Auto-switching is permanently disabled. dark-noc is the hardcoded default on every page load.
// Manual theme switching is available via the cycle button in the top bar.

export function applyTheme(themeVars) {
  // No-op: theme is applied via data-theme attribute in App.jsx
}

// resolveTheme: always returns dark-noc. Auto-switching removed permanently.
export function resolveTheme() {
  return 'dark-noc'
}
