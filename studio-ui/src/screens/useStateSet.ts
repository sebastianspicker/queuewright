import { useState } from 'react'

export function useStateSet(initial: string[]) {
  const [value, setValue] = useState(() => new Set(initial))
  return {
    value,
    add(key: string) {
      setValue((current) => new Set(current).add(key))
    },
    toggle(key: string) {
      setValue((current) => {
        const next = new Set(current)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        return next
      })
    },
    replace(keys: string[]) {
      setValue(new Set(keys))
    },
  }
}
