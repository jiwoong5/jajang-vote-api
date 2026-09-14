# 테스트 시나리오 — 짜장면 vs 짬뽕 투표 API

기준 스펙: `test.md`
전제: 인증 토큰은 HTTP 헤더로 전달. 로그인/인증 테이블은 구현 범위 외.
**주의:** `/api/vote`는 토큰 필수이므로 면접관이 호출할 수 있도록 **README에 테스트용 토큰을 기재**해야 한다 (스펙 5번: 면접관이 URL을 직접 호출).

---

## 1. 규칙 추출

| ID | 규칙 (스펙 원문 근거) | 출처 |
|---|---|---|
| R1 | `choice`는 소문자 `jajang` 또는 `jjamppong` 중 하나 | 2-① line 21~24 |
| R2 | 정상 투표는 저장된다 | 2-① |
| R3 | 동일 `voterId`는 한 번만 투표 가능 | 2-① |
| R4 | 이미 투표한 `voterId` 재요청 → 409 | 2-① line 29 |
| R5 | 잘못된 `choice`, 누락된 값 → 오류 처리 | 2-① |
| R6 | `/api/result` 응답은 `jajang`, `jjamppong`, `total` 키 | 2-② |
| R7 | 조회 결과 = 실제 저장된 투표 수 | 2-② |
| R8 | `/health` 정상이면 200 | 2-③ |
| R9 | 동시 요청 시 정상 투표 유실 없음 | 3 |
| R10 | 동시 요청 시 동일 `voterId` 중복 불허 | 3 |
| R11 | 최종 집계 = 실제 성공한 투표 수 | 3 |
| R12 | 재시작 후 기존 투표 데이터 유지 | 6 |
| R13 | 재시작 후 동일 `voterId` 재투표 → 기존 기록 기준 중복 처리 | 6 |
| **R14** | **헤더 토큰 없으면 투표 불가 (401)** | **우리 결정 (D7)** |
| **R15** | **`voterId` 형식은 `user-{int}`** | **우리 결정 (D5, 스펙 line 19 예시 기반)** |

---

## 2. 결정 사항 (스펙 미명시 항목)

| # | 항목 | 비고 | 결정 |
|---|---|---|---|
| D1 | 투표 성공 시 상태 코드 및 응답 body | 스펙에 성공 응답 예시 없음 | **201**, body `{"state":"success"}` |
| D2 | 잘못된 choice / 누락 시 상태 코드 | "적절하게 처리"만 명시 | **400** |
| D3 | 에러 응답 body 형식 | 미명시 | `{"state":"<분기값>"}` — `invalid_choice` / `missing_choice` / `missing_voterId` / `invalid_voter_id` / `invalid_json` / `unauthorized` / `duplicate` |
| D4 | 중복 투표 상태 코드 | line 29 | **409** |
| D5 | `voterId` 형식 제약 | line 19 예시 `"user-123"` | **`user-{int}`** 형식만 허용, 불일치 시 400 |
| D6 | `choice` 대소문자 취급 | line 21~24 소문자만 명시 | **소문자만 유효**, 그 외 400 |
| D7 | 토큰 누락/무효 시 상태 코드 | 토큰 없음 = 인증된 사용자인지 알 수 없음 → 인증 실패(401), 인가(403) 아님 | **401** |
| D8 | `/api/result`, `/health` 인증 여부 | 스펙 5번이 두 URL을 공개 예시로 제시. `/health`는 모니터링 관례상 무인증 | **인증 없이 허용** |
| D9 | body가 JSON이 아닐 때 / Content-Type 불일치 | 미명시 | **400** |
| D10 | `/health` 응답 body | 미명시 | **DB 상태 포함** (예: `{"db":"up"}`) |
| D11 | 투표 0건일 때 응답 | 예시는 0건 상황 없음 | **키를 0으로 내림** |

---

## 3. 동치 분할 / 경계값

| 규칙 | 유효 분할 | 무효 분할 (대표값 1개) | 경계값 |
|---|---|---|---|
| R1 choice | `jajang` / `jjamppong` (2개) | ① 누락 ② 두 값 외 문자열 `"tangsuyuk"` | — |
| R3 voterId | 최초 voterId | 이미 투표한 voterId | — |
| R5 voterId 누락 | 존재 | 누락 | — |
| R15 voterId 형식 | `user-{int}` | 형식 불일치 `"abc"` | `user-0` (최솟값, 유효) / `user--1` (최솟값−1) / `user-1.5` (비정수) |
| R7 집계 | ≥1건 | — | **0건** (최솟값) |
| R9~R11 동시성 | N개 상이 voterId | N개 동일 voterId | N=1 (직렬과 동일) |
| R14 토큰 | 유효 토큰 | 누락 | — |

> 대소문자(`"Jajang"`), 타입 오류(`choice: 1`), 빈 문자열 voterId, 여분 필드, JSON 파싱 실패는 R1/R5/R15의 같은 무효 분할로 보고 6번(여유)으로 내림.

---

## 4. 테스트 케이스

서버 상태는 **DB 직접 조회** (`SELECT voter_id, choice FROM votes`)로 확인.
`/api/result`로 대체하면 R7과 결합돼 원인 분리가 안 됨.

모든 `POST /api/vote`는 별도 표기 없으면 **유효 토큰 헤더 포함**.

실행 순서: R-00 → V-01 → V-02 → R-01 → R-02 → H-01 → V-03~V-08 → R-03 → V-09~V-11 → C-01 → C-02 → P-01 → P-02 → X-*

### 4-1. 성공 → 응답 스키마 + 서버 상태

| ID | 입력 | 기대 응답 | 기대 서버 상태 |
|---|---|---|---|
| V-01 | `POST /api/vote` `{"choice":"jajang","voterId":"user-1"}` | **201**, `Content-Type: application/json`, body `{"state":"success"}` | votes 1건: `(user-1, jajang)` |
| V-02 | `{"choice":"jjamppong","voterId":"user-2"}` | 201, `{"state":"success"}` | votes 2건, `(user-2, jjamppong)` 추가 |
| R-01 | `GET /api/result` 토큰 없이 (V-01, V-02 후) | 200, JSON, 키 정확히 `jajang`/`jjamppong`/`total` 3개, 값 모두 정수 | (읽기 전용) |
| R-02 | 동일 | `{"jajang":1,"jjamppong":1,"total":2}`, `total == jajang + jjamppong` | DB `GROUP BY` 결과와 동일 |
| H-01 | `GET /health` 토큰 없이 | 200, body에 DB 상태 (예: `{"db":"up"}`) | — |

### 4-2. 실패 → 규칙별 무효 분할 1개 + 서버 상태 불변

에러 응답 스키마(`{"state":"<분기값>"}`)는 V-03에서 한 번만 확인. 구현: `tests/test_scenario.py` (케이스 ID 1:1).

| ID | 입력 | 기대 응답 | 기대 서버 상태 |
|---|---|---|---|
| V-03 | `{"choice":"jjamppong","voterId":"user-1"}` (user-1 재투표, **choice를 바꿔서**) | **409**, body `{"state":"<중복 분기값>"}` | votes **2건 그대로**, `user-1`의 choice **여전히 `jajang`** (덮어쓰기 안 됨) |
| V-04 | `{"choice":"tangsuyuk","voterId":"user-3"}` | **400** | 2건 그대로, `user-3` 없음 |
| V-05 | `{"voterId":"user-3"}` (choice 누락) | **400** | 2건 그대로 |
| V-06 | `{"choice":"jajang"}` (voterId 누락) | **400** | 2건 그대로 |
| V-07 | **토큰 없이** `{"choice":"jajang","voterId":"user-3"}` | **401** | 2건 그대로, `user-3` 없음 |
| V-08 | `{"choice":"jajang","voterId":"abc"}` (형식 불일치) | **400** | 2건 그대로 |
| R-03 | V-03~V-08 후 `GET /api/result` | `{"jajang":1,"jjamppong":1,"total":2}` 변화 없음 | — |

### 4-3. 경계값

| ID | 입력 | 기대 응답 | 기대 서버 상태 |
|---|---|---|---|
| R-00 | 빈 DB에서 `GET /api/result` (**실행 순서상 가장 먼저**) | 200, `{"jajang":0,"jjamppong":0,"total":0}` | votes 0건 |
| V-09 | `{"choice":"jajang","voterId":"user-0"}` (int 최솟값) | **201** | votes 3건, `(user-0, jajang)` 추가 |
| V-10 | `{"choice":"jajang","voterId":"user--1"}` (최솟값−1) | **400** | 3건 그대로 |
| V-11 | `{"choice":"jajang","voterId":"user-1.5"}` (비정수) | **400** | 3건 그대로 |

### 4-4. 동시성

| ID | 입력 | 기대 응답 | 기대 서버 상태 |
|---|---|---|---|
| C-01 | 상이한 voterId `user-1001`~`user-1100` 100개 **동시** 요청 | 100개 모두 201 | votes 정확히 +100, `/api/result` total도 +100 |
| C-02 | 동일 voterId `user-9999`로 50개 **동시** 요청 | **정확히 1개** 201, 49개 409 | `user-9999` 1건만 존재, choice는 성공한 요청의 값 |

### 4-5. 재시작

| ID | 입력 | 기대 응답 | 기대 서버 상태 |
|---|---|---|---|
| P-01 | 컨테이너 재시작 → `GET /health`, `GET /api/result` | 200, 재시작 전과 동일한 집계 | votes 건수·내용 동일 |
| P-02 | 재시작 후 `{"choice":"jjamppong","voterId":"user-1"}` | 409 | `user-1` 여전히 `jajang`, 건수 불변 |

### 4-6. 여유 있으면

| ID | 입력 | 기대 응답 | 기대 서버 상태 |
|---|---|---|---|
| X-01 | `{"choice":"Jajang","voterId":"user-500"}` (대소문자) | 400 | 불변 |
| X-02 | `{"choice":1,"voterId":"user-500"}` (타입 오류) | 400 | 불변 |
| X-03 | `{"choice":"jajang","voterId":123}` (타입 오류) | 400 | 불변 |
| X-04 | `{"choice":"jajang","voterId":"user-500","extra":true}` (여분 필드) | 201 (여분 필드 무시) | `user-500` 저장 |
| X-05 | body가 JSON 아님 (`text/plain "hello"`) | 400 | 불변 |
| X-06 | 무효 토큰(형식은 맞지만 검증 실패) | 401 | 불변 |
| X-07 | `{"choice":"jajang","voterId":""}` (빈 문자열) | 400 | 불변 |
| X-08 | DB 중지 후 `GET /health` | **503**, `{"status":"error","db":"down"}` | — |

---

## 5. 규칙 ↔ 테스트 매핑

규칙 하나가 사라지면 최소 하나의 테스트가 깨져야 한다.

| 규칙 | 깨뜨리면 실패해야 하는 테스트 |
|---|---|
| R1 | V-04 (검증 제거 시 저장돼 버림) |
| R2 | V-01, V-02 |
| R3 | V-03 |
| R4 | V-03 (응답 코드) |
| R5 | V-04, V-05, V-06 |
| R6 | R-01 |
| R7 | R-02, R-03, R-00 |
| R8 | H-01 |
| R9 | C-01 |
| R10 | C-02 |
| R11 | C-01, C-02 (result total 확인) |
| R12 | P-01 |
| R13 | P-02 |
| R14 | V-07 |
| R15 | V-08, V-09, V-10, V-11 |

모든 규칙이 최소 1개 테스트에 매핑됨. X 계열은 여유분으로 규칙 매핑 대상 아님.

---

## 6. 테이블 설계와의 연결

```sql
CREATE TABLE votes (
    voter_id    VARCHAR(100)  PRIMARY KEY,
    choice      VARCHAR(20)   NOT NULL CHECK (choice IN ('jajang', 'jjamppong')),
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_votes_choice ON votes (choice);
```

| 테스트 | 테이블 설계에서 보장하는 지점 |
|---|---|
| V-03, C-02, P-02 | `voter_id PRIMARY KEY` — 앱 로직 없이도 DB가 두 번째 INSERT를 거부 |
| V-04 (2차 방어) | `CHECK (choice IN (...))` |
| V-08, V-10, V-11 | 앱 검증 (`^user-\d+$`). DB CHECK로도 가능하나 정규식 지원이 DB마다 달라 앱에서 처리 |
| R-02, R-03, C-01 | 카운터 테이블 없이 `GROUP BY` → 저장 행과 집계 불일치 자체가 불가능 |
| P-01, P-02 | DB 파일/볼륨 영속 (설계 아니라 인프라) |
