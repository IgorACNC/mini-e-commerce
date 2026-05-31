import json
import os
import uuid
from datetime import datetime, timezone
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
USERS_URL = os.getenv("USERS_URL", "http://localhost:5001")
PRODUCTS_URL = os.getenv("PRODUCTS_URL", "http://localhost:5002")

DB_PATH = Path(__file__).parent / "orders.json"

bearer_scheme = HTTPBearer()


# ---------- helpers de armazenamento ----------

def read_db() -> list:
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


def write_db(data: list) -> None:
    DB_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- helper de JWT ----------

def decode_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        payload["_raw"] = credentials.credentials  # guarda o token bruto para repassar
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")


# ---------- schemas ----------

class OrderRequest(BaseModel):
    userId: str
    productId: str
    quantity: int = 1


# ---------- endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/orders", status_code=201)
def create_order(body: OrderRequest, token: dict = Depends(decode_token)):
    # usuário só pode criar pedido para si mesmo (admin pode para qualquer um)
    if token["userId"] != body.userId and token["role"] != "admin":
        raise HTTPException(403, "Você só pode criar pedidos para sua própria conta")

    # verifica se o usuário existe
    try:
        user_resp = httpx.get(
            f"{USERS_URL}/users/{body.userId}",
            headers={"Authorization": f"Bearer {token['_raw']}"},
            timeout=3.0,
        )
        if user_resp.status_code == 404:
            raise HTTPException(404, "Usuário não encontrado")
        user_resp.raise_for_status()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Serviço de usuários indisponível")

    # verifica se o produto existe
    try:
        product_resp = httpx.get(f"{PRODUCTS_URL}/products/{body.productId}", timeout=3.0)
        if product_resp.status_code == 404:
            raise HTTPException(404, "Produto não encontrado")
        product_resp.raise_for_status()
        product = product_resp.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Serviço de produtos indisponível")

    if product["stock"] < body.quantity:
        raise HTTPException(400, f"Estoque insuficiente. Disponível: {product['stock']}")

    order = {
        "id": str(uuid.uuid4()),
        "userId": body.userId,
        "productId": body.productId,
        "productName": product["name"],
        "quantity": body.quantity,
        "totalPrice": round(product["price"] * body.quantity, 2),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    orders = read_db()
    orders.append(order)
    write_db(orders)

    return order


@app.get("/orders/{user_id}")
def get_orders(user_id: str, token: dict = Depends(decode_token)):
    if token["userId"] != user_id and token["role"] != "admin":
        raise HTTPException(403, "Acesso negado")

    orders = read_db()
    user_orders = [o for o in orders if o["userId"] == user_id]

    return user_orders
