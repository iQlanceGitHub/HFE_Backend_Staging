import os
from datetime import datetime, timedelta

from jose import JWTError, jwt, ExpiredSignatureError

from src.api import schemas
from src.configs.config import EnvVar
from fastapi import HTTPException


def create_access_token(data: dict):
    to_encode = data.copy()
    # expire = datetime.utcnow() + timedelta(minutes=EnvVar.AccessTokenExpireMinutes)
    # to_encode.update({"exp": expire})
    expire_minutes = int(
        os.environ.get(EnvVar.AccessTokenExpireMinutes.value, 15)
    )  # Default to 15 minutes if not set
    expire = datetime.utcnow() + timedelta(minutes=expire_minutes)

    # encoded_jwt = jwt.encode(to_encode, EnvVar.SecretKey, algorithm=EnvVar.Algorithm)
    # return encoded_jwt

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        os.environ[EnvVar.SecretKey.value],
        algorithm=os.environ[EnvVar.Algorithm.value],
    )
    return encoded_jwt, expire_minutes


def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(
            token, 
            os.environ[EnvVar.SecretKey.value], 
            algorithms=[os.environ[EnvVar.Algorithm.value]]
        )
        useremail: str = payload.get("sub")
        if useremail is None:
            raise credentials_exception
        token_data = schemas.TokenData(useremail=useremail)
        return token_data
    except ExpiredSignatureError:
        # Handle expired token specifically
        raise HTTPException(
            status_code=401,
            detail="Token expired! Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise credentials_exception
