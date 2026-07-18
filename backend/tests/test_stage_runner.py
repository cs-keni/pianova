import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.errors import PianovaError
from app.models.entities import ProcessingRun, ProcessingStatus, Project
from app.services.stage_runner import StageRunner


def test_stage_runner_precommits_and_completes_cas_winner(client: TestClient) -> None:
    with client.app.state.session_factory() as session:
        project = Project(title="Stage runner winner")
        session.add(project)
        session.commit()
        runner = StageRunner(session, stage="test_stage", logger=logging.getLogger(__name__))

        run = runner.precommit_run(
            project_id=project.id,
            configuration={"processor_version": "1.0.0"},
        )

        assert run.id is not None
        assert run.status is ProcessingStatus.RUNNING
        assert run.configuration_json == '{"processor_version": "1.0.0"}'

        runner.commit_success(
            project=project,
            run=run,
            configuration={"diagnostics": {"count": 1}, "processor_version": "1.0.0"},
            project_update=update(Project)
            .where(Project.id == project.id, Project.quantization_revision == 0)
            .values(quantization_revision=1),
            conflict_error=PianovaError("test_conflict", "The test stage lost its CAS.", 409),
        )

        assert project.quantization_revision == 1
        assert run.status is ProcessingStatus.SUCCEEDED
        assert run.completed_at is not None
        assert run.configuration_json == (
            '{"diagnostics": {"count": 1}, "processor_version": "1.0.0"}'
        )


def test_stage_runner_raises_for_cas_loser_and_can_mark_failure(client: TestClient) -> None:
    with client.app.state.session_factory() as session:
        project = Project(title="Stage runner loser")
        session.add(project)
        session.commit()
        runner = StageRunner(session, stage="test_stage", logger=logging.getLogger(__name__))
        run = runner.precommit_run(project_id=project.id, configuration={})

        with client.app.state.session_factory() as other_session:
            other_project = other_session.get(Project, project.id)
            assert other_project is not None
            other_project.quantization_revision = 1
            other_session.commit()

        with pytest.raises(PianovaError, match="lost its CAS") as captured:
            runner.commit_success(
                project=project,
                run=run,
                configuration={"diagnostics": {}},
                project_update=update(Project)
                .where(Project.id == project.id, Project.quantization_revision == 0)
                .values(quantization_revision=1),
                conflict_error=PianovaError(
                    "test_conflict",
                    "The test stage lost its CAS.",
                    409,
                ),
            )

        assert captured.value.code == "test_conflict"
        session.rollback()
        runner.mark_failed(run.id, captured.value.message)

        failed_run = session.get(ProcessingRun, run.id)
        assert failed_run is not None
        assert failed_run.status is ProcessingStatus.FAILED
        assert failed_run.error_message == "The test stage lost its CAS."
        assert failed_run.completed_at is not None
        session.refresh(project)
        assert project.quantization_revision == 1


def test_stage_runner_failure_mark_is_safe_for_missing_run(client: TestClient) -> None:
    with client.app.state.session_factory() as session:
        runner = StageRunner(session, stage="test_stage", logger=logging.getLogger(__name__))

        runner.mark_failed(999_999, "Missing run")
