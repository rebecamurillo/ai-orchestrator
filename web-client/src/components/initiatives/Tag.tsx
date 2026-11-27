/** The DESIGN.md `tag`: a tertiary upper-case key and a secondary value; an accent link when given `href`. */
interface Props {
  label: string;
  value: string;
  href?: string;
  testId?: string;
}

export default function Tag({ label, value, href, testId }: Props) {
  return (
    <span className="ini-tag">
      <span className="ini-tag-key">{label}</span>{' '}
      {href ? (
        <a className="ini-tag-value" href={href} data-testid={testId}>
          {value}
        </a>
      ) : (
        <span className="ini-tag-value" data-testid={testId}>
          {value}
        </span>
      )}
    </span>
  );
}
