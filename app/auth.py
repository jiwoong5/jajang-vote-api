from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import API_TOKEN

# auto_error=False: 기본값이면 헤더 누락 시 403 을 내므로 직접 401 로 처리한다.
bearer = HTTPBearer(auto_error=False)


def require_token(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    """Authorization: Bearer <token>. 누락/불일치 모두 401 (인증 실패)."""
    if cred is None or cred.scheme.lower() != "bearer" or cred.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
