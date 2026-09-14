# 짜장면 vs 짬뽕 투표 API

FastAPI + MySQL 기반 투표 서비스. Docker Compose 로 실행, ngrok 으로 외부 노출.

## 제출 정보

- **소스코드:** https://github.com/jiwoong5/jajang-vote-api
- **Public URL:** https://refusing-foil-ungodly.ngrok-free.dev
- **CI:** GitHub Actions — MySQL 8 서비스 컨테이너 대상 시나리오 테스트 + Docker 빌드

> ngrok 무료 플랜이라 터널을 재시작하면 URL 이 바뀝니다. 위 URL 은 제출 시점 기준입니다.

## API

| Method | Path | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/vote` | **필요** | 투표 |
| GET | `/api/result` | 불필요 | 집계 조회 |
| GET | `/health` | 불필요 | 헬스체크 (DB 상태 포함) |

### 인증

`/api/vote` 는 `Authorization: Bearer <token>` 헤더가 필요합니다.
**테스트용 토큰: `test-token`** (환경변수 `API_TOKEN` 으로 변경 가능)

### Swagger UI

`/docs` 에서 직접 호출해 볼 수 있습니다. 우측 상단 **Authorize** 에 `test-token` 을 입력하면 `/api/vote` 도 실행됩니다.
ngrok 무료 플랜이라 브라우저 첫 접속 시 ngrok 경고 페이지가 한 번 뜹니다 — **Visit Site** 를 누르면 됩니다.

### 호출 예시

```bash
BASE=https://refusing-foil-ungodly.ngrok-free.dev

curl $BASE/health
# {"status":"ok","db":"up"}

curl -X POST $BASE/api/vote \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{"choice":"jajang","voterId":"user-123"}'
# 201 {"state":"success"}

curl $BASE/api/result
# {"jajang":1,"jjamppong":0,"total":1}
```

### 응답 코드

| 코드 | 상황 | body |
|---|---|---|
| 201 | 투표 성공 | `{"state":"success"}` |
| 400 | choice 가 `jajang`/`jjamppong` 이 아님, 필드 누락, `voterId` 형식 불일치, JSON 아님 | `{"state":"invalid_choice" \| "missing_choice" \| "missing_voterId" \| "invalid_voter_id" \| "invalid_json"}` |
| 401 | 토큰 누락 또는 불일치 | `{"state":"unauthorized"}` |
| 409 | 이미 투표한 `voterId` | `{"state":"duplicate"}` |
| 503 | `/health` 에서 DB 연결 실패 | `{"status":"error","db":"down"}` |

`voterId` 는 `user-{정수}` 형식만 허용합니다 (예: `user-0`, `user-123`). `choice` 는 소문자만 유효합니다.

## 실행 방법

```bash
cp .env.example .env          # 필요하면 토큰/비밀번호 수정
docker compose up -d --build  # app(8080) + mysql(3306)
curl localhost:8080/health
```

외부 노출:

```bash
ngrok http 8080               # 로컬 ngrok CLI 사용
# 또는 .env 에 NGROK_AUTHTOKEN 을 넣고
docker compose --profile tunnel up -d   # http://localhost:4040 에서 URL 확인
```

## 테스트

`test-scenario.md` 의 케이스 ID 와 1:1 로 대응하는 pytest 스위트입니다. 실행 중인 서버와 DB 를 대상으로 동작합니다.

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest tests -v
RUN_RESTART_TESTS=1 .venv/Scripts/python -m pytest tests -v   # 컨테이너 재시작 케이스 포함
```

> 테스트는 시작 시 `votes` 테이블을 비웁니다.

## 사용한 기술

- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Core + PyMySQL
- MySQL 8.0 (InnoDB)
- Docker / Docker Compose
- ngrok

## 데이터 저장 방식

테이블 1개.

```sql
CREATE TABLE votes (
    voter_id    VARCHAR(100)  NOT NULL PRIMARY KEY,
    choice      VARCHAR(20)   NOT NULL,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_votes_choice CHECK (choice IN ('jajang', 'jjamppong')),
    INDEX idx_votes_choice (choice)
);
```

- `voter_id` 가 PK. 별도 카운터 테이블 없이 `SELECT choice, COUNT(*) ... GROUP BY choice` 로 집계하므로 조회 결과와 저장된 행이 구조적으로 불일치할 수 없습니다.
- 앱 기동 시 `CREATE TABLE IF NOT EXISTS` 로 스키마를 보장합니다.

## 동시성 및 중복 투표 처리

- 중복 방지를 **DB PK 제약 하나에만** 의존합니다. `SELECT 후 INSERT` 를 하지 않고 바로 `INSERT` 하며, PK 충돌(`IntegrityError`)을 409 로 매핑합니다.
- 동일 `voterId` 로 N 개 요청이 동시에 들어와도 InnoDB 가 정확히 하나만 통과시키므로 앱 레벨 락이나 트랜잭션 격리 조정이 필요 없습니다.
- 서로 다른 `voterId` 요청은 서로 간섭하지 않아 유실 없이 모두 저장됩니다.
- 검증(테스트 C-01, C-02): 상이 voterId 100 동시 요청 → 100 건 저장 / 동일 voterId 50 동시 요청 → 1 건 201, 49 건 409.

## 재시작 후 데이터 유지

- MySQL 데이터 디렉터리를 named volume(`mysql_data`) 에 마운트. `docker compose restart`, `down` / `up` 모두 데이터 유지.
- `restart: unless-stopped` 로 컨테이너 자동 재기동.
- 앱은 기동 시 DB 연결을 최대 30 회 재시도하므로 MySQL 이 늦게 떠도 정상 기동.
- 검증(테스트 P-01, P-02): 재시작 후 집계 동일, 기존 voterId 재투표 시 409.

## Public URL 구성

로컬 Docker 의 8080 포트를 ngrok 으로 터널링. `docker-compose.yml` 에 ngrok 컨테이너(`tunnel` 프로파일)도 포함되어 있어 CLI 없이도 실행 가능.

## 설계 시 중요하게 판단한 사항

1. **중복 방지의 단일 진실 원천을 DB 제약으로** — 앱 코드에서 존재 여부를 확인하는 순간 race condition 이 생깁니다. PK 하나로 동시성·재시작 후 중복·일반 중복을 모두 해결했습니다.
2. **카운터 테이블을 두지 않음** — 집계와 원본이 어긋날 경로 자체를 없앴습니다. 규모가 커지면 그때 캐시를 붙이면 됩니다.
3. **에러 응답 통일** — FastAPI 기본 422 대신 400 으로, 모든 오류 body 를 `{"state": ...}` 하나의 형태로 통일했습니다.
4. **`/api/result`, `/health` 는 무인증** — 스펙이 두 URL 을 공개 예시로 제시했고, 헬스체크는 모니터링 도구가 호출하므로 토큰을 걸 수 없습니다. 집계값에는 보호할 정보도 없습니다.
5. **스펙에 없는 결정은 문서화** — `test-scenario.md` 2번 표에 상태 코드, voterId 형식 등 스펙이 정하지 않은 항목과 결정 근거를 남겼습니다.
