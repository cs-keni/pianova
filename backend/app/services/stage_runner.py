import json
import logging

from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update

from app.core.errors import PianovaError
from app.models.entities import ProcessingRun, ProcessingStatus, Project, utc_now


class StageRunner:
    """Persist the transaction boundaries shared by symbolic processing stages."""

    def __init__(self, session: Session, *, stage: str, logger: logging.Logger) -> None:
        self.session = session
        self.stage = stage
        self.logger = logger

    def precommit_run(
        self,
        *,
        project_id: str,
        configuration: dict[str, object],
    ) -> ProcessingRun:
        """Create and commit a durable RUNNING audit row before stage work begins."""
        run = ProcessingRun(
            project_id=project_id,
            stage=self.stage,
            status=ProcessingStatus.RUNNING,
            configuration_json=json.dumps(configuration, sort_keys=True),
            started_at=utc_now(),
        )
        self.session.add(run)
        self.session.commit()
        return run

    def commit_success(
        self,
        *,
        project: Project,
        run: ProcessingRun,
        configuration: dict[str, object],
        project_update: Update,
        conflict_error: PianovaError,
    ) -> None:
        """Commit stage output only when its project compare-and-swap wins."""
        run.configuration_json = json.dumps(configuration, sort_keys=True)
        run.status = ProcessingStatus.SUCCEEDED
        run.completed_at = utc_now()
        self.session.flush()
        updated = self.session.execute(project_update.execution_options(synchronize_session=False))
        if getattr(updated, "rowcount", 0) != 1:
            raise conflict_error
        self.session.commit()
        self.session.refresh(project)

    def mark_failed(self, run_id: int, message: str) -> None:
        """Record failure after the caller rolls back stage output changes."""
        try:
            run = self.session.get(ProcessingRun, run_id)
            if run is None:
                return
            run.status = ProcessingStatus.FAILED
            run.error_message = message
            run.completed_at = utc_now()
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.logger.exception("Could not persist failed %s run %s", self.stage, run_id)
