import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import PianovaError
from app.models.entities import Project
from app.repositories.projects import ProjectRepository


class ProjectService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = ProjectRepository(session)

    def create(self, title: str) -> Project:
        project = Project(title=title.strip())
        if not project.title:
            raise PianovaError("invalid_title", "Project title cannot be blank.", 422)
        project_dir: Path | None = None
        try:
            self.repository.add(project)
            project_dir = self.settings.workspace_dir / "projects" / project.id
            project_dir.mkdir(parents=True, exist_ok=False)
            self.session.commit()
        except PianovaError:
            raise
        except Exception as error:
            self.session.rollback()
            if project_dir is not None:
                shutil.rmtree(project_dir, ignore_errors=True)
            raise PianovaError(
                "project_creation_failed",
                "The project could not be created.",
                500,
            ) from error
        return project
