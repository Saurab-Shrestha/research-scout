import { Checkbox } from '@/components/ui/checkbox'
import { REGIONS } from '@/lib/format'
import { cn } from '@/lib/utils'

const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v])

/** Countries by region; the region checkbox selects or clears all of its countries. */
export function CountryPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">Countries <span className="font-normal text-muted-foreground">({value.length} selected)</span></legend>
      {Object.entries(REGIONS).map(([region, names]) => {
        const codes = Object.keys(names)
        const picked = codes.filter((c) => value.includes(c)).length
        return (
          <div key={region} className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
            <label className="flex w-36 shrink-0 items-center gap-2 pt-1 text-sm">
              <Checkbox checked={picked === codes.length ? true : picked ? 'indeterminate' : false}
                onCheckedChange={() => onChange(picked === codes.length ? value.filter((c) => !codes.includes(c)) : [...new Set([...value, ...codes])])} />
              {region}
            </label>
            <div className="flex flex-wrap gap-1.5">
              {codes.map((c) => (
                <button key={c} type="button" aria-pressed={value.includes(c)} onClick={() => onChange(toggle(value, c))}
                  className={cn('rounded-lg border px-2.5 py-1 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                    value.includes(c) ? 'border-navy bg-navy text-navy-ink' : 'border-border bg-sheet text-muted-foreground hover:border-input hover:text-foreground')}>
                  {names[c]}
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </fieldset>
  )
}
