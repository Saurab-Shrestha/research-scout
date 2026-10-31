import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * A text box whose value lives in the URL (?q=…) without writing on every keystroke.
 * Writing each keystroke races React Router's updater, which reads a stale copy of the params, so cleared
 * text came back. The box keeps its own state and the URL catches up after a pause; external URL changes
 * (Clear filters, back button) still flow into the box.
 */
export function useUrlText(key = 'q', delay = 250) {
  const [params, setParams] = useSearchParams()
  const urlValue = params.get(key) ?? ''
  const [text, setText] = useState(urlValue)
  const written = useRef(urlValue)

  useEffect(() => {
    if (urlValue === written.current) return
    written.current = urlValue
    setText(urlValue) // eslint-disable-line react-hooks/set-state-in-effect -- adopting an external URL change
  }, [urlValue])

  useEffect(() => {
    if (text === written.current) return
    const t = setTimeout(() => {
      written.current = text
      setParams((p) => { const next = new URLSearchParams(p); if (text) next.set(key, text); else next.delete(key); return next }, { replace: true })
    }, delay)
    return () => clearTimeout(t)
  }, [text, key, delay, setParams])

  return [text, setText] as const
}
