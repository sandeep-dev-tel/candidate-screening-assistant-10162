from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.api import db
from src.api.models import (
    CandidateRankedOut,
    CriteriaIn,
    CriteriaOut,
    RankRequest,
    RankingOut,
    ResumeOut,
)
from src.api.parsing import extract_structured_fields, extract_text

openapi_tags = [
    {"name": "health", "description": "Service health checks."},
    {"name": "resumes", "description": "Upload and manage resumes."},
    {"name": "criteria", "description": "Create and manage screening criteria."},
    {"name": "ranking", "description": "Rank candidates against criteria and list ranked results."},
]

logger = logging.getLogger("resume_backend")
if not logger.handlers:
    # Basic config for local/dev; production logging can override this via uvicorn config.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(asctime)s %(name)s - %(message)s")


app = FastAPI(
    title="Resume Screening Assistant API",
    description=(
        "Backend APIs for uploading CVs, parsing/extracting fields, submitting criteria, "
        "ranking candidates, and listing ranked candidates. Data is persisted to Postgres."
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normalize_db_json(value: Any) -> Dict[str, Any]:
    """
    Normalize a DB JSON/JSONB value to a Python dict.

    psycopg can return json/jsonb as:
      - already-decoded dict
      - a string containing JSON
      - None

    We also defensively handle unexpected types to avoid 500s when serializing response models.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            logger.warning("Failed to json.loads DB JSON string; returning empty object.")
            return {}
    # Unexpected (e.g., list); wrap to keep response model stable
    return {"value": value}


def _resume_row_to_out(row: Dict[str, Any]) -> ResumeOut:
    return ResumeOut(
        id=row["id"],
        filename=row["filename"],
        content_type=row.get("content_type"),
        extracted=_normalize_db_json(row.get("extracted")),
        created_at=row["created_at"],
    )


def _criteria_row_to_out(row: Dict[str, Any]) -> CriteriaOut:
    return CriteriaOut(
        id=row["id"],
        title=row["title"],
        description=row.get("description"),
        criteria=_normalize_db_json(row.get("criteria")),
        created_at=row["created_at"],
    )


def _ranking_row_to_out(row: Dict[str, Any]) -> RankingOut:
    return RankingOut(
        id=row["id"],
        criteria_id=row["criteria_id"],
        resume_id=row["resume_id"],
        score=float(row["score"]),
        breakdown=_normalize_db_json(row.get("breakdown")),
        created_at=row["created_at"],
    )


# PUBLIC_INTERFACE
@app.get("/", tags=["health"], summary="Health check", description="Simple health check endpoint.")
def health_check():
    """Health check route returning a simple JSON payload."""
    return {"message": "Healthy", "time": datetime.utcnow().isoformat()}


# PUBLIC_INTERFACE
@app.post(
    "/resumes/upload",
    tags=["resumes"],
    summary="Upload a resume (PDF/DOCX) and parse it",
    description=(
        "Accepts a multipart file upload (PDF or DOCX). Extracts text, derives basic structured fields, "
        "and persists the resume record in Postgres."
    ),
    response_model=ResumeOut,
)
async def upload_resume(file: UploadFile = File(..., description="PDF or DOCX resume file.")):
    """Upload and parse a resume file, persisting raw text and extracted JSON to Postgres."""
    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload.")

        raw_text = extract_text(file.filename or "resume", file.content_type, data)
        extracted = extract_structured_fields(raw_text)

        row = db.execute_returning_one(
            "INSERT INTO resumes (filename, content_type, raw_text, extracted) VALUES (%s, %s, %s, %s) "
            "RETURNING id, filename, content_type, extracted, created_at;",
            (file.filename, file.content_type, raw_text, json.dumps(extracted)),
        )
        return _resume_row_to_out(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("upload_resume failed: filename=%s content_type=%s error=%s", file.filename, file.content_type, e)
        raise HTTPException(status_code=500, detail="Failed to upload/parse resume.") from e


# PUBLIC_INTERFACE
@app.get(
    "/resumes",
    tags=["resumes"],
    summary="List uploaded resumes",
    description="Lists uploaded resumes ordered by newest first.",
    response_model=List[ResumeOut],
)
def list_resumes(limit: int = Query(50, ge=1, le=200, description="Max number of resumes to return.")):
    """List resumes (metadata + extracted fields)."""
    try:
        rows = db.fetch_all(
            "SELECT id, filename, content_type, extracted, created_at FROM resumes ORDER BY created_at DESC LIMIT %s;",
            (limit,),
        )
        return [_resume_row_to_out(r) for r in rows]
    except Exception as e:
        logger.exception("list_resumes failed: error=%s", e)
        raise HTTPException(status_code=500, detail="Failed to list resumes.") from e


# PUBLIC_INTERFACE
@app.post(
    "/criteria",
    tags=["criteria"],
    summary="Create criteria",
    description="Create a new set of screening criteria (stored as JSON).",
    response_model=CriteriaOut,
)
def create_criteria(payload: CriteriaIn):
    """Create criteria for screening/ranking."""
    try:
        row = db.execute_returning_one(
            "INSERT INTO criteria (title, description, criteria) VALUES (%s, %s, %s) "
            "RETURNING id, title, description, criteria, created_at;",
            (payload.title, payload.description, json.dumps(payload.criteria)),
        )
        return _criteria_row_to_out(row)
    except Exception as e:
        logger.exception("create_criteria failed: title=%s error=%s", payload.title, e)
        raise HTTPException(status_code=500, detail="Failed to create criteria.") from e


# PUBLIC_INTERFACE
@app.get(
    "/criteria",
    tags=["criteria"],
    summary="List criteria",
    description="List criteria ordered by newest first.",
    response_model=List[CriteriaOut],
)
def list_criteria(limit: int = Query(50, ge=1, le=200, description="Max number of criteria to return.")):
    """List criteria definitions."""
    try:
        rows = db.fetch_all(
            "SELECT id, title, description, criteria, created_at FROM criteria ORDER BY created_at DESC LIMIT %s;",
            (limit,),
        )
        return [_criteria_row_to_out(r) for r in rows]
    except Exception as e:
        logger.exception("list_criteria failed: error=%s", e)
        raise HTTPException(status_code=500, detail="Failed to list criteria.") from e


def _compute_score(criteria: Dict[str, Any], resume_extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute a simple score based on criteria JSON and extracted resume fields.

    Supported example criteria JSON:
      {
        "required_skills": ["python", "sql"],
        "preferred_skills": ["fastapi"],
        "weights": {"required": 5, "preferred": 2}
      }
    """
    required = [s.lower() for s in criteria.get("required_skills", []) if isinstance(s, str)]
    preferred = [s.lower() for s in criteria.get("preferred_skills", []) if isinstance(s, str)]
    weights = criteria.get("weights") or {}
    w_req = float(weights.get("required", 5))
    w_pref = float(weights.get("preferred", 2))

    resume_skills = {s.lower() for s in (resume_extracted.get("skills") or []) if isinstance(s, str)}
    req_hits = [s for s in required if s in resume_skills]
    pref_hits = [s for s in preferred if s in resume_skills]

    # Hard penalty if missing required skills: scale by fraction satisfied.
    req_fraction = (len(req_hits) / len(required)) if required else 1.0
    base = (len(req_hits) * w_req) + (len(pref_hits) * w_pref)
    score = base * req_fraction

    breakdown = {
        "required_skills": required,
        "preferred_skills": preferred,
        "resume_skills": sorted(resume_skills),
        "required_hits": req_hits,
        "preferred_hits": pref_hits,
        "required_fraction": req_fraction,
        "weights": {"required": w_req, "preferred": w_pref},
    }
    return {"score": score, "breakdown": breakdown}


# PUBLIC_INTERFACE
@app.post(
    "/rank",
    tags=["ranking"],
    summary="Rank all resumes against a criteria set",
    description=(
        "Computes a simple heuristic score for each resume against the given criteria and "
        "upserts results into the rankings table."
    ),
    response_model=List[RankingOut],
)
def rank_all(payload: RankRequest):
    """Rank all resumes for a criteria_id, persist results, and return the ranking rows."""
    try:
        criteria_row = db.fetch_one("SELECT id, criteria FROM criteria WHERE id = %s;", (str(payload.criteria_id),))
        if not criteria_row:
            raise HTTPException(status_code=404, detail="criteria_id not found")

        criteria = _normalize_db_json(criteria_row.get("criteria"))

        resumes = db.fetch_all("SELECT id, extracted FROM resumes;")
        ranking_out: List[RankingOut] = []

        for r in resumes:
            resume_id = r["id"]
            extracted = _normalize_db_json(r.get("extracted"))
            computed = _compute_score(criteria, extracted)

            row = db.execute_returning_one(
                "INSERT INTO rankings (criteria_id, resume_id, score, breakdown) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (criteria_id, resume_id) DO UPDATE SET "
                "score = EXCLUDED.score, breakdown = EXCLUDED.breakdown, created_at = now() "
                "RETURNING id, criteria_id, resume_id, score, breakdown, created_at;",
                (str(payload.criteria_id), str(resume_id), float(computed["score"]), json.dumps(computed["breakdown"])),
            )
            ranking_out.append(_ranking_row_to_out(row))

        ranking_out.sort(key=lambda x: x.score, reverse=True)
        return ranking_out
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("rank_all failed: criteria_id=%s error=%s", payload.criteria_id, e)
        raise HTTPException(status_code=500, detail="Failed to rank resumes.") from e


# PUBLIC_INTERFACE
@app.get(
    "/candidates",
    tags=["ranking"],
    summary="List ranked candidates for a criteria set",
    description=(
        "Returns resumes with their ranking for the provided criteria_id, ordered by score desc. "
        "If a resume has not been ranked yet for that criteria, it will not appear."
    ),
    response_model=List[CandidateRankedOut],
)
def list_ranked_candidates(
    criteria_id: UUID = Query(..., description="Criteria UUID."),
    limit: int = Query(50, ge=1, le=200, description="Max candidates to return."),
):
    """List ranked candidates for criteria_id (join resumes + rankings)."""
    try:
        rows = db.fetch_all(
            "SELECT "
            "rnk.id as ranking_id, rnk.criteria_id, rnk.resume_id, rnk.score, rnk.breakdown, rnk.created_at as ranking_created_at, "
            "res.id as res_id, res.filename, res.content_type, res.extracted, res.created_at as resume_created_at "
            "FROM rankings rnk "
            "JOIN resumes res ON res.id = rnk.resume_id "
            "WHERE rnk.criteria_id = %s "
            "ORDER BY rnk.score DESC "
            "LIMIT %s;",
            (str(criteria_id), limit),
        )

        out: List[CandidateRankedOut] = []
        for row in rows:
            resume = ResumeOut(
                id=row["res_id"],
                filename=row["filename"],
                content_type=row.get("content_type"),
                extracted=_normalize_db_json(row.get("extracted")),
                created_at=row["resume_created_at"],
            )
            ranking = RankingOut(
                id=row["ranking_id"],
                criteria_id=row["criteria_id"],
                resume_id=row["resume_id"],
                score=float(row["score"]),
                breakdown=_normalize_db_json(row.get("breakdown")),
                created_at=row["ranking_created_at"],
            )
            out.append(CandidateRankedOut(resume=resume, ranking=ranking))
        return out
    except Exception as e:
        logger.exception("list_ranked_candidates failed: criteria_id=%s error=%s", criteria_id, e)
        raise HTTPException(status_code=500, detail="Failed to list candidates.") from e
