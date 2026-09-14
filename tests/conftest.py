import os
import subprocess
import time

import httpx
import pymysql
import pytest

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
TOKEN = os.getenv("API_TOKEN", "test-token")

DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "vote"),
    password=os.getenv("DB_PASSWORD", "votepw"),
    database=os.getenv("DB_NAME", "vote"),
)


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        yield c


@pytest.fixture(scope="session")
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


class DBProbe:
    """서버 상태 확인은 /api/result 가 아니라 DB 를 직접 본다 (R7 과 분리)."""

    def _q(self, sql, args=None):
        conn = pymysql.connect(**DB)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)
                return cur.fetchall()
        finally:
            conn.close()

    def count(self) -> int:
        return self._q("SELECT COUNT(*) FROM votes")[0][0]

    def choice_of(self, voter_id: str):
        rows = self._q("SELECT choice FROM votes WHERE voter_id=%s", (voter_id,))
        return rows[0][0] if rows else None

    def group_counts(self) -> dict:
        rows = self._q("SELECT choice, COUNT(*) FROM votes GROUP BY choice")
        return {c: n for c, n in rows}

    def truncate(self):
        self._q("TRUNCATE TABLE votes")


@pytest.fixture(scope="session")
def dbp():
    return DBProbe()


@pytest.fixture(scope="session", autouse=True)
def clean_db(dbp):
    """시나리오는 R-00(빈 DB)부터 시작하므로 세션 시작 시 한 번 비운다."""
    dbp.truncate()
    yield


def restart_app():
    subprocess.run(["docker", "compose", "restart", "app"], check=True)
    for _ in range(30):
        try:
            if httpx.get(f"{BASE_URL}/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("app did not come back after restart")
