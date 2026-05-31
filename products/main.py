import json
import os
import uuid
from pathlib import Path

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI()

JWT_SECRET = os.getenv("JWT_SECRET", "chave_secreta")

# primary usa products_a.json e replica é products_b.json (e vice-versa na réplica)
REPLICA_ROLE = os.getenv("REPLICA_ROLE", "primary")
PEER_URL = os.getenv("PEER_URL", "http://localhost:5012")

DB_PATH = Path(__file__).parent / (
    "products_a.json" if REPLICA_ROLE == "primary" else "products_b.json"
)

bearer_scheme = HTTPBearer()


# ---------- helpers de armazenamento ----------

def read_db() -> list:
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


def write_db(data: list) -> None:
    DB_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- helper de JWT ----------

def require_admin(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")

    if payload.get("role") != "admin":
        raise HTTPException(403, "Apenas administradores podem criar produtos")

    return payload


def decode_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")


# ---------- schemas ----------

class ProductRequest(BaseModel):
    name: str
    description: str = ""
    price: float
    stock: int = 0


# ---------- endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/products")
def list_products():
    return read_db()


@app.get("/products/{product_id}")
def get_product(product_id: str):
    products = read_db()
    product = next((p for p in products if p["id"] == product_id), None)

    if not product:
        raise HTTPException(404, "Produto não encontrado")

    return product


@app.post("/products", status_code=201)
def create_product(body: ProductRequest, token: dict = Depends(require_admin)):
    if REPLICA_ROLE != "primary":
        raise HTTPException(403, "Escrita permitida apenas na réplica primária")

    product = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "description": body.description,
        "price": body.price,
        "stock": body.stock,
    }

    # propaga para a réplica antes de confirmar (consistência forte)
    try:
        resp = httpx.post(f"{PEER_URL}/_replicate", json=product, timeout=3.0)
        resp.raise_for_status()
    except Exception:
        raise HTTPException(503, "Réplica indisponível — escrita cancelada para manter consistência")

    # só salva localmente após a réplica confirmar
    products = read_db()
    products.append(product)
    write_db(products)

    return product


@app.post("/_replicate", status_code=201)
def replicate(product: dict):
    """Endpoint interno — recebe produto da primária e salva na réplica."""
    products = read_db()
    products.append(product)
    write_db(products)
    return {"ok": True}
