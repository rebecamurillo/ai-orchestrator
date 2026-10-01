"""Hold one connection open until a read model changes, or until the wait runs out.

The alternative a watching agent has is a request every five seconds, forever, whether or not
anything happened (agent-delivery-kit plan §7). This is that poll moved inside one request:
the client asks for up to `wait` seconds, this re-reads once a second and answers the moment
the token it was given stops matching.

It is here rather than in `application/` because waiting is time, and time in the layers above
is a `Clock` port (AD-2). It knows nothing about Runs: the caller supplies the read and the
`Watch`, which is what makes it testable without a database and without a real second passing
— `sleep` is injected, and `POLL_INTERVAL_S` is read at each await so a test can flatten it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

#: How often a held connection re-reads. One second: every transition this exists to report is
#: written by a DBOS step, which is far coarser, and thirty reads is the whole cost of the
#: longest hold a route allows.
POLL_INTERVAL_S = 1.0

#: One fresh read of whatever is being watched. Async, because the read itself is blocking I/O
#: that belongs on a worker thread — a held connection must not own the event loop.
type Read[T] = Callable[[], Awaitable[T]]
type Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class Watch[T, K]:
    """What the caller is waiting for: a read it already made, and what unchanged means.

    `first` is read before the wait begins, so a caller can refuse an unknown id without
    holding anything open. `baseline` is usually `token(first)`; a client that passes back the
    token of its previous answer makes it that one instead, which is how a change made between
    two calls is seen on the first read rather than missed.
    """

    first: T
    baseline: K
    token: Callable[[T], K]


async def _real_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def hold_until_changed[T, K](
    read: Read[T],
    watch: Watch[T, K],
    *,
    wait: int,
    sleep: Sleep = _real_sleep,
) -> tuple[T, bool]:
    """`(latest, changed)`: the newest read, and whether its token left the baseline.

    `wait` is a whole number of seconds; `wait=0` answers `watch.first` without reading again.
    """
    if watch.token(watch.first) != watch.baseline:
        return watch.first, True
    latest = watch.first
    for _ in range(wait):
        await sleep(POLL_INTERVAL_S)
        latest = await read()
        if watch.token(latest) != watch.baseline:
            return latest, True
    return latest, False
