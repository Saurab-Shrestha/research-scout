import { X } from 'lucide-react'
import { useState } from 'react'
import { Input } from '@/components/ui/input'

/** Editable list of short strings: Enter or comma adds, × removes. */
export function TagInput({ id, value, onChange, placeholder }: { id: string; value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = useState('')
  const add = (text = draft) => {
    const t = text.trim().replace(/,$/, '').trim()
    if (t && !value.includes(t)) onChange([...value, t])
    setDraft('')
  }
  return (
    <div className="flex flex-wrap gap-1.5 rounded-md border bg-background p-1.5 focus-within:ring-2 focus-within:ring-ring/40">
      {value.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-sm text-secondary-foreground">
          {t}
          <button type="button" aria-label={`Remove ${t}`} className="-my-1 -mr-1 grid size-6 place-items-center rounded text-muted-foreground hover:bg-background hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring" onClick={() => onChange(value.filter((x) => x !== t))}><X className="size-3.5" /></button>
        </span>
      ))}
      <Input id={id} value={draft} placeholder={placeholder} onBlur={() => add()}
        onChange={(e) => (e.target.value.endsWith(',') ? add(e.target.value) : setDraft(e.target.value))}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } else if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1)) }}
        className="h-8 min-w-40 flex-1 border-0 px-1 shadow-none focus-visible:ring-0" />
    </div>
  )
}
