from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.copilot.services import answer_query
from app.platform.models import AppUser
from app.platform.permissions import require
from app.shared.database import get_db
from app.shared.schemas import ResponseWrapper

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class Query(BaseModel):
    question: str


@router.post("/query", response_model=ResponseWrapper[dict])
def query(body: Query, db: Session = Depends(get_db),
          _: AppUser = Depends(require("copilot_query", "X"))):  # Kueri copilot: X/R untuk semua peran
    return ResponseWrapper(data=answer_query(db, body.question))