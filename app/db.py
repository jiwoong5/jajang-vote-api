import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)

# voter_id PK 가 중복 투표 방지의 단일 지점. 동시 INSERT 도 DB 가 하나만 통과시킨다.
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS votes (
    voter_id    VARCHAR(100)  NOT NULL PRIMARY KEY,
    choice      VARCHAR(20)   NOT NULL,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_votes_choice CHECK (choice IN ('jajang', 'jjamppong')),
    INDEX idx_votes_choice (choice)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def init_db(retries: int = 30, delay: float = 1.0) -> None:
    """컨테이너 기동 순서상 MySQL 이 늦게 뜰 수 있으므로 재시도한다."""
    last_err = None
    for _ in range(retries):
        try:
            with engine.begin() as conn:
                conn.execute(text(CREATE_TABLE))
            return
        except OperationalError as e:
            last_err = e
            time.sleep(delay)
    raise RuntimeError(f"DB not reachable after {retries} retries") from last_err


def ping() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
