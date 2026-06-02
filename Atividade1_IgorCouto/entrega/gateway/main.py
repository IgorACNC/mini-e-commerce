import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

LOG_PATH = Path(__file__).parent / "gateway.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),                          # continua exibindo no terminal
        logging.FileHandler(LOG_PATH, encoding="utf-8"), # salva no arquivo
    ],
)
logger = logging.getLogger("gateway")


SERVICES = {
    "users":    os.getenv("USERS_URL",    "http://localhost:5001"),
    "products": os.getenv("PRODUCTS_URL", "http://localhost:5002"),
    "orders":   os.getenv("ORDERS_URL",   "http://localhost:5003"),
}

HEARTBEAT_INTERVAL = 5   # segundos entre cada verificação
MAX_FAILURES = 2         # falhas consecutivas para marcar como DOWN

# estado de saúde de cada serviço
health_status: dict[str, bool] = {name: True for name in SERVICES}
failure_count: dict[str, int]  = {name: 0    for name in SERVICES}


async def heartbeat_loop():
    async with httpx.AsyncClient(timeout=2.0) as client:
        while True:
            for name, url in SERVICES.items():
                try:
                    resp = await client.get(f"{url}/health")
                    ok = resp.status_code == 200
                except Exception:
                    ok = False

                if ok:
                    if not health_status[name]:
                        # serviço voltou
                        logger.info(
                            "RECOVERED | serviço '%s' voltou a responder em %s",
                            name,
                            datetime.now(timezone.utc).isoformat(),
                        )
                    health_status[name] = True
                    failure_count[name] = 0
                else:
                    failure_count[name] += 1
                    if failure_count[name] >= MAX_FAILURES and health_status[name]:
                        # acabou de passar o limite — marca como DOWN
                        health_status[name] = False
                        logger.warning(
                            "DOWN | serviço '%s' não respondeu %d vezes seguidas. Marcado como indisponível em %s",
                            name,
                            MAX_FAILURES,
                            datetime.now(timezone.utc).isoformat(),
                        )

            await asyncio.sleep(HEARTBEAT_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(heartbeat_loop())
    logger.info("Gateway iniciado. Heartbeat ativo (intervalo: %ds)", HEARTBEAT_INTERVAL)
    yield



app = FastAPI(lifespan=lifespan)


async def proxy(request: Request, service: str, path: str) -> Response:
    method = request.method

    if not health_status[service]:
        logger.warning("REQUEST | %s %s → %s | 503 (serviço indisponível)", method, path, service)
        return Response(
            content=f'{{"detail": "Serviço {service} indisponível no momento"}}',
            status_code=503,
            media_type="application/json",
        )

    url = f"{SERVICES[service]}{path}"

    # repassa os query params (ex: ?page=1)
    if request.url.query:
        url += f"?{request.url.query}"

    # filtra headers hop-by-hop que não devem ser repassados
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "transfer-encoding")
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=await request.body(),
            )
    except Exception:
        logger.error("REQUEST | %s %s → %s | 503 (erro de conexão)", method, path, service)
        return Response(
            content=f'{{"detail": "Erro ao conectar com o serviço {service}"}}',
            status_code=503,
            media_type="application/json",
        )

    logger.info("REQUEST | %s %s → %s | %d", method, path, service, resp.status_code)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type", "application/json"),
    )


@app.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def users_proxy(path: str, request: Request):
    return await proxy(request, "users", f"/users/{path}")


@app.api_route("/products/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def products_proxy(path: str, request: Request):
    return await proxy(request, "products", f"/products/{path}")


@app.api_route("/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def orders_proxy(path: str, request: Request):
    return await proxy(request, "orders", f"/orders/{path}")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "services": {
            name: "up" if up else "down"
            for name, up in health_status.items()
        },
    }
