import { ref, watch } from 'vue'

type Theme = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'trip-planner-theme'

const theme = ref<Theme>(
  (localStorage.getItem(STORAGE_KEY) as Theme) || 'system'
)

const resolvedTheme = ref<'light' | 'dark'>('light')

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light'
  }
  return 'light'
}

function applyTheme(t: Theme) {
  const resolved = t === 'system' ? getSystemTheme() : t
  resolvedTheme.value = resolved
  document.documentElement.setAttribute('data-theme', resolved)
}

function setTheme(t: Theme) {
  theme.value = t
  localStorage.setItem(STORAGE_KEY, t)
  applyTheme(t)
}

function toggleTheme() {
  const current = resolvedTheme.value
  setTheme(current === 'light' ? 'dark' : 'light')
}

watch(theme, (val) => applyTheme(val), { immediate: true })

if (typeof window !== 'undefined' && window.matchMedia) {
  window
    .matchMedia('(prefers-color-scheme: dark)')
    .addEventListener('change', () => {
      if (theme.value === 'system') {
        applyTheme('system')
      }
    })
}

export function useTheme() {
  return {
    theme,
    resolvedTheme,
    setTheme,
    toggleTheme,
  }
}
