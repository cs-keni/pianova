from sqlalchemy.orm import Session

from app.models.entities import Project


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, project_id: str) -> Project | None:
        return self.session.get(Project, project_id)

    def add(self, project: Project) -> Project:
        self.session.add(project)
        self.session.flush()
        return project
