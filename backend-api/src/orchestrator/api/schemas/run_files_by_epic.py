"""Response schemas of `GET /runs/{run_id}/files-by-epic` and its `/diff` (AD-40)."""

from __future__ import annotations

from pydantic import BaseModel

from orchestrator.application.use_cases.run_files_by_epic import EpicFiles, StoryDiff


class StoryFilesOut(BaseModel):
    id: str
    title: str
    story_file: str | None
    started: bool
    changed: list[str]


class EpicFilesOut(BaseModel):
    index: int
    title: str
    folder: str
    files: list[str]
    stories: list[StoryFilesOut]


class RunFilesByEpicOut(BaseModel):
    epics: list[EpicFilesOut]

    @classmethod
    def of(cls, epics: tuple[EpicFiles, ...]) -> RunFilesByEpicOut:
        return cls(
            epics=[
                EpicFilesOut(
                    index=e.index,
                    title=e.title,
                    folder=e.folder,
                    files=list(e.files),
                    stories=[
                        StoryFilesOut(
                            id=s.id,
                            title=s.title,
                            story_file=s.story_file,
                            started=s.started,
                            changed=list(s.changed),
                        )
                        for s in e.stories
                    ],
                )
                for e in epics
            ]
        )


class StoryDiffOut(BaseModel):
    path: str
    from_sha: str
    to_sha: str
    diff: str

    @classmethod
    def of(cls, diff: StoryDiff) -> StoryDiffOut:
        return cls(path=diff.path, from_sha=diff.from_sha, to_sha=diff.to_sha, diff=diff.diff)
