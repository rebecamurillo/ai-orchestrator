/**
 * The harness list (4.13, FR-33): one line per harness, each ending in the `re-run readiness`
 * link the brief keeps in scope even though Epic 5 is what serves the endpoint — "here the
 * link points to it and shows `not available yet` if 404".
 *
 * The link is an anchor at the proxy path, and the `not available yet` note beside it is
 * stated rather than probed. Two reasons, both structural rather than convenient: the route
 * is not in `contracts/openapi.json` at all, so `src/api/client.ts` — the only caller the
 * browser is allowed (AD-1, and `eslint.config.js` enforces it) — has no method for it; and
 * a route absent from the contract is one this instance provably does not serve, so "not
 * available yet" is a fact about this build, not a guess awaiting a probe. The story that
 * lands `POST /harnesses/{name}/readiness` regenerates the contract and is the one that
 * wires the action — which is exactly the half the brief puts out of scope here.
 *
 * Every harness this epic ships is seeded `enabled: false` and nothing here enables one, so
 * the disabled case is the normal one: the radio is disabled and the line states why in
 * words.
 *
 * A `<fieldset>`/`<legend>` rather than a `<div>` with a `<span>`: a radio group needs an
 * accessible name, and this is the element that gives it one without inventing ARIA.
 */
import type { components } from '../api/schema';
import {
  READINESS_LINK_LABEL,
  READINESS_NOT_AVAILABLE,
  harnessLineText,
  readinessHref,
} from '../lib/newwf/state';

type HarnessOut = components['schemas']['HarnessOut'];

interface Props {
  harnesses: HarnessOut[];
  selected: string;
  onSelect: (name: string) => void;
}

export default function HarnessList({ harnesses, selected, onSelect }: Props) {
  return (
    <fieldset className="newwf-field newwf-harnesses-field">
      <legend className="newwf-field-label">HARNESS</legend>
      <div className="newwf-harnesses">
        {harnesses.map((harness) => (
          <p
            className="newwf-harness"
            key={harness.name}
            data-testid={`newwf-harness-${harness.name}`}
          >
            <label className="newwf-harness-label">
              <input
                type="radio"
                name="newwf-harness"
                value={harness.name}
                disabled={!harness.enabled}
                checked={selected === harness.name}
                onChange={() => onSelect(harness.name)}
              />
              {harnessLineText(harness)}
            </label>
            <a
              className="newwf-harness-readiness"
              data-testid={`newwf-readiness-${harness.name}`}
              href={readinessHref(harness.name)}
            >
              {READINESS_LINK_LABEL}
            </a>
            <span
              className="newwf-harness-note"
              data-testid={`newwf-readiness-${harness.name}-note`}
            >
              {READINESS_NOT_AVAILABLE}
            </span>
          </p>
        ))}
      </div>
    </fieldset>
  );
}
