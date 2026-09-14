from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth import require_token
from app.schemas import HealthResponse, ResultResponse, StateResponse, VoteRequest


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="jajang-vs-jjamppong", lifespan=lifespan)


# --- 에러 응답을 {"state": "..."} 로 통일 -------------------------------------

def _validation_state(exc: RequestValidationError) -> str:
    """분기별 state 값. 첫 번째 에러 기준."""
    err = exc.errors()[0]
    loc = err.get("loc", ())
    field = loc[-1] if loc else None
    etype = err.get("type", "")

    if etype == "json_invalid" or field == "body":
        return "invalid_json"
    if etype == "missing":
        return f"missing_{field}"
    if field == "choice":
        return "invalid_choice"
    if field == "voterId":
        return "invalid_voter_id"
    return "invalid_request"


@app.exception_handler(RequestValidationError)
async def on_validation_error(_: Request, exc: RequestValidationError):
    # FastAPI 기본 422 대신 400 (D2/D5/D6/D9)
    return JSONResponse(status_code=400, content={"state": _validation_state(exc)})


@app.exception_handler(HTTPException)
async def on_http_error(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"state": exc.detail})


# --- 엔드포인트 ---------------------------------------------------------------

@app.post("/api/vote", status_code=201, response_model=StateResponse,
          dependencies=[Depends(require_token)])
def vote(req: VoteRequest):
    try:
        with db.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO votes (voter_id, choice) VALUES (:voter_id, :choice)"),
                {"voter_id": req.voterId, "choice": req.choice},
            )
    except IntegrityError:
        # PK 충돌 = 이미 투표한 voterId. SELECT 없이 DB 제약에만 의존하므로 race 없음.
        raise HTTPException(status_code=409, detail="duplicate")
    return {"state": "success"}


@app.get("/api/result", response_model=ResultResponse)
def result():
    with db.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT choice, COUNT(*) AS cnt FROM votes GROUP BY choice")
        ).all()
    counts = {"jajang": 0, "jjamppong": 0}
    for choice, cnt in rows:
        counts[choice] = cnt
    return {**counts, "total": counts["jajang"] + counts["jjamppong"]}


@app.get("/health", response_model=HealthResponse)
def health():
    if db.ping():
        return {"status": "ok", "db": "up"}
    return JSONResponse(status_code=503, content={"status": "error", "db": "down"})
