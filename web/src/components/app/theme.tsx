import { Moon, Sun } from 'lucide-react'
import { useEffect, useSyncExternalStore } from 'react'
import { Button } from '@/components/ui/button'

export type ThemeChoice = 'light' | 'dark' | 'system'
const EVENT = 'theme-change'
const media = () => matchMedia('(prefers-color-scheme: dark)')

function read(): ThemeChoice {
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* storage blocked */ }
  return 'system'
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb)
  media().addEventListener('change', cb)
  return () => { window.removeEventListener(EVENT, cb); media().removeEventListener('change', cb) }
}

export function setTheme(choice: ThemeChoice) {
  try { if (choice === 'system') localStorage.removeItem('theme'); else localStorage.setItem('theme', choice) } catch { /* storage blocked */ }
  window.dispatchEvent(new Event(EVENT))
}

/** The saved choice plus what it resolves to; one store so the sidebar toggle and Settings stay in step. */
export function useTheme() {
  const choice = useSyncExternalStore(subscribe, read)
  const dark = useSyncExternalStore(subscribe, () => (choice === 'system' ? media().matches : choice === 'dark'))
  useEffect(() => { document.documentElement.classList.toggle('dark', dark) }, [dark])
  return { choice, dark }
}

export function ThemeToggle() {
  const { dark } = useTheme()
  return (
    <Button variant="ghost" size="icon" aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`} onClick={() => setTheme(dark ? 'light' : 'dark')}>
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}
