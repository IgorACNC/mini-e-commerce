import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI()

JWT_SECRET = os.getenv("JWT_SECRET", "chave_secreta")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", 24))
DB_PATH = Path(__file__).parent / "users.json"

bearer_scheme = HTTPBearer()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed

def read_db() -> list:
    return json.loads(DB_PATH.read_text(encoding="utf-8"))

def write_db(data: list) -> None:
    DB_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def create_token(user: dict) -> str:
    payload = {
        "userId": user["id"],
        "email": user["email"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "user"


class LoginRequest(BaseModel):
    email: str
    password: str

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/users/register", status_code=201)
def register(body: RegisterRequest):
    users = read_db()

    if any(u["email"] == body.email for u in users):
        raise HTTPException(409, "E-mail já cadastrado")

    user = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "email": body.email,
        "password": hash_password(body.password),
        "role": body.role,
    }
    users.append(user)
    write_db(users)

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "token": create_token(user),
    }

@app.post("/users/login")
def login(body: LoginRequest):
    users = read_db()
    user = next((u for u in users if u["email"] == body.email), None)

    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(401, "Credenciais inválidas")

    return {"token": create_token(user)}

@app.get("/users/{user_id}")
def get_user(user_id: str, token: dict = Depends(decode_token)):
    if token["userId"] != user_id and token["role"] != "admin":
        raise HTTPException(403, "Acesso negado")

    users = read_db()
    user = next((u for u in users if u["id"] == user_id), None)

    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}
