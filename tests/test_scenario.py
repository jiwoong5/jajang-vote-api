"""
test-scenario.md 의 케이스 ID 와 1:1 대응.
실행 순서가 의미 있으므로 pytest 기본 파일 순서(정의 순)에 의존한다.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.conftest import restart_app

RESULT_KEYS = {"jajang", "jjamppong", "total"}


def vote(client, auth, body, headers=None):
    return client.post("/api/vote", json=body, headers=headers if headers is not None else auth)


# ---------------------------------------------------------------- 4-3 경계값 (R-00 은 가장 먼저)

def test_R00_result_on_empty_db(client, dbp):
    r = client.get("/api/result")
    assert r.status_code == 200
    assert r.json() == {"jajang": 0, "jjamppong": 0, "total": 0}
    assert dbp.count() == 0


# ---------------------------------------------------------------- 4-1 성공

def test_V01_vote_jajang(client, auth, dbp):
    r = vote(client, auth, {"choice": "jajang", "voterId": "user-1"})
    assert r.status_code == 201
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"state": "success"}
    assert dbp.count() == 1
    assert dbp.choice_of("user-1") == "jajang"


def test_V02_vote_jjamppong(client, auth, dbp):
    r = vote(client, auth, {"choice": "jjamppong", "voterId": "user-2"})
    assert r.status_code == 201
    assert r.json() == {"state": "success"}
    assert dbp.count() == 2
    assert dbp.choice_of("user-2") == "jjamppong"


def test_R01_result_schema(client):
    r = client.get("/api/result")  # 토큰 없이 (D8)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert set(body.keys()) == RESULT_KEYS
    assert all(isinstance(v, int) for v in body.values())


def test_R02_result_matches_db(client, dbp):
    body = client.get("/api/result").json()
    assert body == {"jajang": 1, "jjamppong": 1, "total": 2}
    assert body["total"] == body["jajang"] + body["jjamppong"]
    g = dbp.group_counts()
    assert body["jajang"] == g.get("jajang", 0)
    assert body["jjamppong"] == g.get("jjamppong", 0)


def test_H01_health(client):
    r = client.get("/health")  # 토큰 없이 (D8)
    assert r.status_code == 200
    assert r.json()["db"] == "up"


# ---------------------------------------------------------------- 4-2 실패 + 서버 상태 불변

def test_V03_duplicate_voter_keeps_original(client, auth, dbp):
    r = vote(client, auth, {"choice": "jjamppong", "voterId": "user-1"})
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/json")
    assert set(r.json().keys()) == {"state"}  # 에러 스키마는 여기서 한 번만
    assert r.json()["state"] == "duplicate"
    assert dbp.count() == 2
    assert dbp.choice_of("user-1") == "jajang"  # 덮어쓰기 안 됨


def test_V04_invalid_choice(client, auth, dbp):
    r = vote(client, auth, {"choice": "tangsuyuk", "voterId": "user-3"})
    assert r.status_code == 400
    assert dbp.count() == 2
    assert dbp.choice_of("user-3") is None


def test_V05_missing_choice(client, auth, dbp):
    r = vote(client, auth, {"voterId": "user-3"})
    assert r.status_code == 400
    assert dbp.count() == 2


def test_V06_missing_voter_id(client, auth, dbp):
    r = vote(client, auth, {"choice": "jajang"})
    assert r.status_code == 400
    assert dbp.count() == 2


def test_V07_missing_token(client, auth, dbp):
    r = vote(client, auth, {"choice": "jajang", "voterId": "user-3"}, headers={})
    assert r.status_code == 401
    assert dbp.count() == 2
    assert dbp.choice_of("user-3") is None


def test_V08_voter_id_bad_format(client, auth, dbp):
    r = vote(client, auth, {"choice": "jajang", "voterId": "abc"})
    assert r.status_code == 400
    assert dbp.count() == 2


def test_R03_result_unchanged_after_failures(client):
    assert client.get("/api/result").json() == {"jajang": 1, "jjamppong": 1, "total": 2}


# ---------------------------------------------------------------- 4-3 경계값 (voterId)

def test_V09_voter_id_min_int(client, auth, dbp):
    r = vote(client, auth, {"choice": "jajang", "voterId": "user-0"})
    assert r.status_code == 201
    assert dbp.count() == 3
    assert dbp.choice_of("user-0") == "jajang"


def test_V10_voter_id_below_min(client, auth, dbp):
    r = vote(client, auth, {"choice": "jajang", "voterId": "user--1"})
    assert r.status_code == 400
    assert dbp.count() == 3


def test_V11_voter_id_non_integer(client, auth, dbp):
    r = vote(client, auth, {"choice": "jajang", "voterId": "user-1.5"})
    assert r.status_code == 400
    assert dbp.count() == 3


# ---------------------------------------------------------------- 4-4 동시성

def test_C01_concurrent_distinct_voters(client, auth, dbp):
    before = dbp.count()
    before_total = client.get("/api/result").json()["total"]
    ids = [f"user-{i}" for i in range(1001, 1101)]

    def go(vid):
        return vote(client, auth, {"choice": "jajang", "voterId": vid}).status_code

    with ThreadPoolExecutor(max_workers=50) as ex:
        codes = list(ex.map(go, ids))

    assert codes.count(201) == 100
    assert dbp.count() == before + 100
    assert client.get("/api/result").json()["total"] == before_total + 100


def test_C02_concurrent_same_voter(client, auth, dbp):
    before = dbp.count()
    choices = ["jajang" if i % 2 == 0 else "jjamppong" for i in range(50)]

    def go(choice):
        return vote(client, auth, {"choice": choice, "voterId": "user-9999"}).status_code

    with ThreadPoolExecutor(max_workers=50) as ex:
        codes = list(ex.map(go, choices))

    assert codes.count(201) == 1
    assert codes.count(409) == 49
    assert dbp.count() == before + 1
    assert dbp.choice_of("user-9999") in ("jajang", "jjamppong")


# ---------------------------------------------------------------- 4-5 재시작 (docker compose 필요)

RESTART = os.getenv("RUN_RESTART_TESTS") == "1"


@pytest.mark.skipif(not RESTART, reason="set RUN_RESTART_TESTS=1")
def test_P01_data_survives_restart(client, dbp):
    before_result = client.get("/api/result").json()
    before_count = dbp.count()
    restart_app()
    assert client.get("/health").status_code == 200
    assert client.get("/api/result").json() == before_result
    assert dbp.count() == before_count


@pytest.mark.skipif(not RESTART, reason="set RUN_RESTART_TESTS=1")
def test_P02_duplicate_after_restart(client, auth, dbp):
    r = vote(client, auth, {"choice": "jjamppong", "voterId": "user-1"})
    assert r.status_code == 409
    assert dbp.choice_of("user-1") == "jajang"


# ---------------------------------------------------------------- 4-6 여유

@pytest.mark.parametrize("case_id,body", [
    ("X01_uppercase_choice", {"choice": "Jajang", "voterId": "user-500"}),
    ("X02_choice_type_error", {"choice": 1, "voterId": "user-500"}),
    ("X03_voter_id_type_error", {"choice": "jajang", "voterId": 123}),
    ("X07_empty_voter_id", {"choice": "jajang", "voterId": ""}),
])
def test_X_invalid_bodies(client, auth, dbp, case_id, body):
    before = dbp.count()
    r = vote(client, auth, body)
    assert r.status_code == 400
    assert dbp.count() == before


def test_X05_non_json_body(client, auth, dbp):
    before = dbp.count()
    r = client.post("/api/vote", content=b"hello",
                    headers={**auth, "Content-Type": "text/plain"})
    assert r.status_code == 400
    assert dbp.count() == before


def test_X06_wrong_token(client, dbp):
    before = dbp.count()
    r = client.post("/api/vote", json={"choice": "jajang", "voterId": "user-500"},
                    headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    assert dbp.count() == before
