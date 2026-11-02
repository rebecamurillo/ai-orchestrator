"""The notice pass (story 3-3, D4): one channel line, with no mention, for each test edit a
senior accepted.

It is a channel post, not a thread: the Run stays `running` and no stop exists, so a thread
would invite replies nothing reads. Each unposted `senior_accept` on the Project's Runs since
the channel was stored, whatever the Run's status now, is claimed by inserting its
`chat_notice` row, and the claim is committed before the post. A failed post keeps its
error on the row. There is no state machine and no sweep: a claimed notice is never posted
again (hard rule 7).
"""

from __future__ import annotations

from typing import Final

import structlog

from orchestrator.application.jobs.chat_ports import ChatPollPorts, error_class, redacted
from orchestrator.application.rules.chat_message import AcceptFacts, accept_line, run_link
from orchestrator.application.rules.signals import FILES_KEY
from orchestrator.domain.entities.chat_thread import ChatNotice
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ports.chat import ChatChannel, ChatError

log = structlog.get_logger(__name__)

INTERNAL: Final = "internal: {name}"
REASON_KEY: Final = "reason"


def post_notices(
    ports: ChatPollPorts, channel: ProjectChannel, chat: ChatChannel, token: str
) -> None:
    """Post every unposted `senior_accept` of the channel's Project, oldest first."""
    with ports.chat.writers.uow:
        records = ports.chat.notices.unposted_accepts(channel.project_id, channel.created_at)
    for record in records:
        try:
            _notice_one(ports, channel, chat, token, record)
        except Exception as error:
            _failed(record, error)


def _notice_one(
    ports: ChatPollPorts,
    channel: ProjectChannel,
    chat: ChatChannel,
    token: str,
    record: GateRecord,
) -> None:
    facts = _claim(ports, channel, record)
    if facts is None:
        return
    try:
        chat.post(accept_line(facts, channel.metadata_only), ())
    except ChatError as error:
        _keep_error(ports, record, redacted(error.detail, token))
        _failed(record, error)
        return
    except Exception as error:
        _keep_error(ports, record, INTERNAL.format(name=error_class(error)))
        _failed(record, error)
        return
    log.info("chat notice posted", run_id=str(record.run_id), gate_record_id=str(record.id))


def _claim(ports: ChatPollPorts, channel: ProjectChannel, record: GateRecord) -> AcceptFacts | None:
    chat = ports.chat
    with chat.writers.uow:
        notice = ChatNotice(
            gate_record_id=record.id, run_id=record.run_id, created_at=ports.clock.now()
        )
        if not chat.notices.add(notice):
            return None
        facts = _facts(ports, channel, record)
        chat.writers.uow.commit()
    return facts


def _facts(ports: ChatPollPorts, channel: ProjectChannel, record: GateRecord) -> AcceptFacts:
    chat = ports.chat
    project = chat.projects.get(channel.project_id)
    run = chat.writers.runs.get(record.run_id)
    repository = chat.repositories.get(run.repository_id) if run is not None else None
    rows = chat.writers.steps.list_for_run(record.run_id)
    row = next((row for row in rows if row.path == record.path), None)
    files = record.payload.get(FILES_KEY)
    return AcceptFacts(
        project=project.name if project is not None else "",
        repository=repository.slug if repository is not None else "",
        story_id=row.story_id if row is not None else None,
        files=tuple(str(name) for name in files) if isinstance(files, list) else (),
        reason=str(record.payload.get(REASON_KEY) or ""),
        run_url=run_link(ports.public_base_url, record.run_id),
    )


def _keep_error(ports: ChatPollPorts, record: GateRecord, error: str) -> None:
    with ports.chat.writers.uow:
        ports.chat.notices.set_error(record.id, error)
        ports.chat.writers.uow.commit()


def _failed(record: GateRecord, error: Exception) -> None:
    log.warning(
        "chat notice failed",
        run_id=str(record.run_id),
        gate_record_id=str(record.id),
        error_class=error_class(error),
    )
