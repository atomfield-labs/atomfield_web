import { useState, type FormEvent } from 'react';

const NAME_LENGTH = 100;

/**
 * A name; click it to change it.
 */
export default function EditableTitle({
  title,
  onRename,
  className,
  inputClassName,
  label,
}: {
  title: string;
  onRename: (title: string) => void;
  className: string;
  inputClassName: string;
  label: string;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  if (editing === null) {
    return (
      <button
        type="button"
        onClick={() => setEditing(title)}
        title="Rename"
        className={className}
      >
        {title}
      </button>
    );
  }
  const save = (event?: FormEvent) => {
    event?.preventDefault();
    onRename(editing);
    setEditing(null);
  };
  return (
    <form onSubmit={save}>
      <input
        autoFocus
        value={editing}
        onChange={(event) => setEditing(event.target.value)}
        onBlur={() => save()}
        onKeyDown={(event) => event.key === 'Escape' && setEditing(null)}
        maxLength={NAME_LENGTH}
        aria-label={label}
        className={inputClassName}
      />
    </form>
  );
}
