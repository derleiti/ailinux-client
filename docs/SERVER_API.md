# AILinux Client ↔ Server API Dokumentation

## Übersicht

Der AILinux Client kommuniziert mit dem Server (api.ailinux.me) für:
- **Authentifizierung** - Login/Token-basiert
- **Modelliste** - Tier-abhängig (Free/Pro/Enterprise)
- **KI-Chat** - Automatisches Routing (Ollama für Free, OpenRouter für Pro+)

## Tier-System

| Tier | Modelle | Backend | Limits |
|------|---------|---------|--------|
| Free | 28+ Ollama | ollama (lokal) | 100k Tokens/Tag |
| Pro | 544+ alle | openrouter | 1M Tokens/Tag |
| Enterprise | alle + Priority | openrouter | Unbegrenzt |

## API Endpoints

### 1. Login
POST /v1/auth/login → {user_id, token, tier, client_id}

### 2. Modelliste
GET /v1/client/models → {tier, tier_name, model_count, models[], backend}

### 3. Chat
POST /v1/client/chat → {response, model, tier, backend, tokens_used, latency_ms}

### 4. Tier-Info
GET /v1/client/tier → {tier, name, features[], backend}

## Authentifizierung

Header: Authorization: Bearer <jwt_token>
