import { useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';

interface Props {
  /** Columns already selected (shown as chips). */
  value: string[];
  onChange: (next: string[]) => void;
  /** All column names from the uploaded file, used for autocomplete. */
  options: string[];
  placeholder?: string;
  id?: string;
}

/**
 * Tag/chip input with type-ahead. The user types a column name; matching
 * columns from the uploaded file appear in a dropdown, and confirmed columns
 * render as removable highlighted chips. Enter / comma / click confirms.
 */
export default function ColumnTokenInput({
  value,
  onChange,
  options,
  placeholder,
  id,
}: Props) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    const chosen = new Set(value.map((v) => v.toLowerCase()));
    return options
      .filter((c) => !chosen.has(c.toLowerCase()))
      .filter((c) => !q || c.toLowerCase().includes(q))
      .slice(0, 8);
  }, [query, options, value]);

  const add = (col: string) => {
    const name = col.trim();
    if (!name) return;
    if (!value.some((v) => v.toLowerCase() === name.toLowerCase())) {
      onChange([...value, name]);
    }
    setQuery('');
    setActive(0);
    setOpen(false);
    inputRef.current?.focus();
  };

  const remove = (col: string) => onChange(value.filter((v) => v !== col));

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === 'Enter' || e.key === ',') && (suggestions[active] || query.trim())) {
      e.preventDefault();
      add(suggestions[active] ?? query);
    } else if (e.key === 'Backspace' && !query && value.length) {
      remove(value[value.length - 1]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <div
        className="mt-2 flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-200 px-2 py-1.5 focus-within:border-primary-400 focus-within:ring-1 focus-within:ring-primary-200 dark:border-slate-700 dark:bg-slate-900"
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((col) => (
          <span
            key={col}
            className="inline-flex items-center gap-1 rounded-md bg-primary-100 px-2 py-0.5 text-xs font-semibold text-primary-700 dark:bg-primary-500/20 dark:text-primary-300"
          >
            {col}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                remove(col);
              }}
              className="rounded hover:bg-primary-200 dark:hover:bg-primary-500/30"
              aria-label={`Remove ${col}`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          id={id}
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={onKeyDown}
          placeholder={value.length ? '' : placeholder}
          className="min-w-[8rem] flex-1 border-0 bg-transparent px-1 py-0.5 text-sm outline-none"
        />
      </div>

      {open && suggestions.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {suggestions.map((c, i) => (
            <li key={c}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  add(c);
                }}
                onMouseEnter={() => setActive(i)}
                className={`block w-full px-3 py-1.5 text-left text-sm ${
                  i === active ? 'bg-primary-50 text-primary-700 dark:bg-primary-500/15 dark:text-primary-300' : 'text-slate-700 dark:text-slate-300'
                }`}
              >
                {c}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
