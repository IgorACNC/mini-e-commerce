# Como executar o projeto

## Pré-requisitos

- Python 3.10 ou superior
- pip

## Instalação

Na raiz do projeto, instale as dependências:

```bash
pip install -r requirements.txt
```

---

## Serviços disponíveis

| Serviço             | Porta |
|---------------------|-------|
| Usuários            | 5001  |
| Produtos (primária) | 5002  |
| Produtos (réplica)  | 5012  |
| Pedidos             | 5003  |
| Gateway             | 8000  |

---

## Rodando os serviços

Cada serviço precisa de um terminal separado. Execute a partir da **raiz do projeto**.

### Serviço de Usuários

```bash
uvicorn users.main:app --port 5001 --reload
```

### Serviço de Produtos

```bash
# Terminal 1 — réplica primária
uvicorn products.main:app --port 5002 --reload

# Terminal 2 — réplica secundária
# Linux/macOS:
REPLICA_ROLE=secondary PEER_URL=http://localhost:5002 uvicorn products.main:app --port 5012 --reload

# Windows (PowerShell):
$env:REPLICA_ROLE="secondary"; $env:PEER_URL="http://localhost:5002"; uvicorn products.main:app --port 5012 --reload
```

### Serviço de Pedidos

```bash
uvicorn orders.main:app --port 5003 --reload
```

---

## Testando o Serviço de Usuários

### 1. Registrar usuário comum

```bash
curl -X POST http://localhost:5001/users/register \
  -H "Content-Type: application/json" \
  -d '{"name": "João", "email": "joao@email.com", "password": "123456"}'
```

Resposta:
```json
{
  "id": "<uuid>",
  "name": "João",
  "email": "joao@email.com",
  "role": "user",
  "token": "<jwt>"
}
```

### 2. Registrar usuário administrador

Para criar produtos é necessário um usuário com `"role": "admin"`.

```bash
curl -X POST http://localhost:5001/users/register \
  -H "Content-Type: application/json" \
  -d '{"name": "Admin", "email": "admin@email.com", "password": "admin123", "role": "admin"}'
```

Guarde o `id` e o `token` retornados.

### 3. Login (obter novo token)

```bash
curl -X POST http://localhost:5001/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@email.com", "password": "admin123"}'
```

### 4. Buscar dados do usuário

```bash
curl http://localhost:5001/users/<id> \
  -H "Authorization: Bearer <token>"
```

---

## Testando o Serviço de Produtos

> As duas réplicas precisam estar rodando antes de criar produtos.

### 1. Criar produto (requer token admin)

```bash
curl -X POST http://localhost:5002/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token_admin>" \
  -d '{"name": "Camiseta", "description": "Algodão premium", "price": 49.90, "stock": 100}'
```

Guarde o `id` do produto retornado.

### 2. Listar produtos (qualquer réplica)

```bash
# Réplica primária
curl http://localhost:5002/products

# Réplica secundária (deve retornar os mesmos dados)
curl http://localhost:5012/products
```

### 3. Buscar produto por ID

```bash
curl http://localhost:5002/products/<id>
```

---

## Testando o Serviço de Pedidos

> O serviço de usuários e o de produtos precisam estar rodando.

### 1. Criar pedido

Use o `id` do usuário e o `id` do produto obtidos nos passos anteriores.

```bash
curl -X POST http://localhost:5003/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"userId": "<id_usuario>", "productId": "<id_produto>", "quantity": 2}'
```

Resposta:
```json
{
  "id": "<uuid>",
  "userId": "<id_usuario>",
  "productId": "<id_produto>",
  "productName": "Camiseta",
  "quantity": 2,
  "totalPrice": 99.80,
  "createdAt": "2026-05-31T19:11:25+00:00"
}
```

### 2. Listar pedidos do usuário

```bash
curl http://localhost:5003/orders/<id_usuario> \
  -H "Authorization: Bearer <token>"
```

---

## Health check

Todos os serviços expõem `GET /health`:

```bash
curl http://localhost:5001/health
curl http://localhost:5002/health
curl http://localhost:5012/health
curl http://localhost:5003/health
```

Resposta esperada:
```json
{ "status": "ok" }
```
