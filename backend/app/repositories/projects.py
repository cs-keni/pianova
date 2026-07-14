from sqlalchemy.orm import Session

from app.models.entities import Project


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, project: Project) -> Project:
        self.session.add(project)
        self.session.flush()
        return project
