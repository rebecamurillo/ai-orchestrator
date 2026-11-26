/** Every workflow of an initiative in order, the current one in the text colour. */
import { Fragment } from 'react';

import { footWord, type WorkflowFoot as Entry } from '../../lib/initiatives/format';

interface Props {
  workflows: Entry[];
  current: string;
}

export default function WorkflowFoot({ workflows, current }: Props) {
  return (
    <p className="ini-foot">
      {workflows.map((entry, i) => (
        <Fragment key={entry.workflow}>
          {i > 0 ? ' ▸ ' : null}
          <span
            className="ini-foot-entry"
            data-current={entry.workflow === current ? 'true' : undefined}
          >
            <span className="ini-foot-dot" />
            {footWord(entry)}
          </span>
        </Fragment>
      ))}
    </p>
  );
}
