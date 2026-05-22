from datetime import datetime, timezone
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.backend.config import settings

security = HTTPBearer(auto_error=False)


def create_token(team_id: str, league_id: str, is_commissioner: bool = False) -> str:
    payload = {
        "team_id": team_id,
        "league_id": league_id,
        "is_commissioner": is_commissioner,
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_team(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required")
    return decode_token(credentials.credentials)
