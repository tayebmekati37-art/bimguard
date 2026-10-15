from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.projects import get_project_or_404
from app.db.session import get_db
from app.models.user import User
from app.services import report_export
from app.services import reports as report_service

router = APIRouter(tags=["reports"])


def _filename(project_id: str, ext: str) -> str:
    return f"readiness-{project_id}.{ext}"


@router.get("/projects/{project_id}/reports/readiness.json")
def readiness_json(project_id: str, db: Session = Depends(get_db),
                   _user: User = Depends(get_current_user)) -> Response:
    """Readiness report as structured JSON. Same data as the CSV and PDF."""
    project = get_project_or_404(db, project_id)
    report = report_service.build_readiness_report(db, project)
    return Response(
        content=report_export.to_json(report),
        media_type="application/json",
        headers={"Content-Disposition": f'inline; filename="{_filename(project_id, "json")}"'},
    )


@router.get("/projects/{project_id}/reports/readiness.csv")
def readiness_csv(project_id: str, db: Session = Depends(get_db),
                  _user: User = Depends(get_current_user)) -> Response:
    """Readiness report as CSV. Summary at the top, one issue per row."""
    project = get_project_or_404(db, project_id)
    report = report_service.build_readiness_report(db, project)
    return Response(
        content=report_export.to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename(project_id, "csv")}"'},
    )


@router.get("/projects/{project_id}/reports/readiness.pdf")
def readiness_pdf(project_id: str, db: Session = Depends(get_db),
                  _user: User = Depends(get_current_user)) -> Response:
    """Readiness report as PDF."""
    project = get_project_or_404(db, project_id)
    report = report_service.build_readiness_report(db, project)
    return Response(
        content=report_export.to_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_filename(project_id, "pdf")}"'},
    )