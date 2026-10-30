interface Props {
  testId: string;
  value: string;
  /** The harness's probed models; `[]` means the harness takes a free-text name. */
  models: string[];
  placeholder?: string;
  /** Text of the blank option; defaults to `—`. */
  blankLabel?: string;
  onChange: (value: string) => void;
}

export default function ModelField({
  testId,
  value,
  models,
  placeholder,
  blankLabel = '—',
  onChange,
}: Props) {
  if (models.length > 0) {
    return (
      <select data-testid={testId} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{blankLabel}</option>
        {models.map((model) => (
          <option key={model} value={model}>
            {model}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      type="text"
      data-testid={testId}
      placeholder={placeholder}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
