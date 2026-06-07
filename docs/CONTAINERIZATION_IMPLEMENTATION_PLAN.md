# Containerization Implementation Plan

**Project:** ComfyUI Sprite Character Prompt Generator  
**Based on:** CONTAINERIZATION_FRD.md v1.2  
**Date:** 2026-06-02  
**Status:** Planning

---

## Overview

This plan breaks the containerization effort into 6 phases, ordered by dependency. Each phase produces a testable milestone. Files are created/modified in the order they're needed.

---

## Phase 1: Backend Dockerfile & .dockerignore

**Goal:** Backend image builds and runs the API successfully.

**FRD Requirements Covered:** FR-02, FR-03, FR-16, FR-19

### Tasks

| # | Task | File | Details |
|---|------|------|---------|
| 1.1 | Create backend `.dockerignore` | `backend/.dockerignore` | Exclude `__pycache__/`, `.venv/`, `tests/`, `*.db`, `*.sqlite3`, `.env`, `sprite_projects/` |
| 1.2 | Create backend `Dockerfile` | `backend/Dockerfile` | Multi-stage: builder installs deps from `requirements.txt`, runtime copies app. Base `python:3.12-slim`. Non-root user. `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]` |
| 1.3 | Build and test backend image locally | — | `docker build -t sprite-backend ./backend` then `docker run --rm -p 8000:8000 sprite-backend`. Verify `/api/health` returns 200 |

### Backend Dockerfile Design

```dockerfile
# Stage 1: Install dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create sprite_projects directory with correct ownership
RUN mkdir -p /app/sprite_projects && chown -R appuser:appuser /app/sprite_projects

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Backend .dockerignore

```gitignore
__pycache__/
*.py[cod]
*$py.class
*.so
.venv/
venv/
env/
.env
.env.*
!.env.example
*.db
*.sqlite3
.pytest_cache/
.mypy_cache/
htmlcov/
.coverage
tests/
sprite_projects/
*.egg-info/
dist/
build/
```

### Acceptance Tests

- [ ] `docker build -t sprite-backend ./backend` succeeds
- [ ] `docker run --rm -p 8000:8000 -e DATABASE_URL=sqlite+aiosqlite:///tmp/test.db sprite-backend` starts
- [ ] `curl http://localhost:8000/api/health` returns `{"status": "ok", "version": "0.1.0"}`
- [ ] Image size < 500 MB

---

## Phase 2: Frontend Dockerfile, Nginx Config & .dockerignore

**Goal:** Frontend image builds, serves the React app, and reverse-proxies API requests.

**FRD Requirements Covered:** FR-04, FR-05, FR-14, FR-16, FR-19

### Tasks

| # | Task | File | Details |
|---|------|------|---------|
| 2.1 | Create frontend `.dockerignore` | `frontend/.dockerignore` | Exclude `node_modules/`, `dist/`, `.vite/`, `test/` |
| 2.2 | Create `nginx.conf` | `frontend/nginx.conf` | SPA fallback, `/api/` reverse proxy to `http://backend:8000`, 10MB upload limit, gzip, WebSocket upgrade headers |
| 2.3 | Create frontend `Dockerfile` | `frontend/Dockerfile` | Multi-stage: `node:20-alpine` builds, `nginx:alpine` serves. Copy `nginx.conf` and built assets |
| 2.4 | Build and test frontend image locally | — | `docker build -t sprite-frontend ./frontend`. Verify Nginx serves the app |

### Frontend Dockerfile Design

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### nginx.conf Design

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Maximum upload size (matches backend MAX_REQUEST_BODY_SIZE)
    client_max_body_size 10M;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript image/svg+xml;
    gzip_min_length 256;

    # API reverse proxy
    location /api/ {
        proxy_pass http://backend:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### Frontend .dockerignore

```gitignore
node_modules/
dist/
.vite/
test/
coverage/
.env
.env.*
*.log
```

### Acceptance Tests

- [ ] `docker build -t sprite-frontend ./frontend` succeeds
- [ ] Image size < 50 MB
- [ ] Nginx serves `index.html` at `/`
- [ ] `/api/` requests are proxied (will fail without backend, but Nginx config is correct)

---

## Phase 3: Docker Compose Production Stack

**Goal:** Full stack starts with `docker compose up -d` and all services are healthy.

**FRD Requirements Covered:** FR-01, FR-06, FR-07, FR-08, FR-09, FR-12, FR-14, FR-15

### Tasks

| # | Task | File | Details |
|---|------|------|---------|
| 3.1 | Rewrite `docker-compose.yml` | `docker-compose.yml` | Add `backend`, `frontend` services. Define `app_network`. Add `sprite_projects_data` volume. Add health checks. Add `depends_on` with conditions |
| 3.2 | Update `.env.example` | `.env.example` | Add `DATABASE_URL`, `SPRITE_PROJECTS_DIR`, `CORS_ORIGINS`, `COMFYUI_TIMEOUT`, `COMFYUI_URL` (proposed) |
| 3.3 | Update `.gitignore` | `.gitignore` | Ensure `.env` is excluded (already is). Add Docker-related entries if needed |
| 3.4 | Test full stack | — | `docker compose up -d`, verify all health checks pass, UI loads at `http://localhost:8080` |

### docker-compose.yml Design

Key changes from current file:
- Add `backend` service (build from `./backend`, health check, `init: true`, `extra_hosts`)
- Add `frontend` service (build from `./frontend`, depends on backend health)
- Add `app_network` bridge network
- Add `sprite_projects_data` volume
- Backend `expose: ["8000"]` (internal only, no host port in production)
- Frontend `ports: ["8080:80"]`
- Backend `env_file: .env` + explicit `environment` for `SPRITE_PROJECTS_DIR` and `CORS_ORIGINS`
- Backend `depends_on: postgres: condition: service_healthy`
- Frontend `depends_on: backend: condition: service_healthy`

### .env.example Updates

Add these entries to the existing `.env.example`:

```env
# PostgreSQL database credentials
POSTGRES_USER=sprite_user
POSTGRES_PASSWORD=CHANGE_ME_strong_password_here
POSTGRES_DB=sprite_prompt_generator

# Backend
DATABASE_URL=postgresql+asyncpg://sprite_user:CHANGE_ME_strong_password_here@postgres:5432/sprite_prompt_generator
SPRITE_PROJECTS_DIR=/app/sprite_projects
CORS_ORIGINS=http://localhost:8080
COMFYUI_TIMEOUT=10.0

# ComfyUI external API
# When running in Docker, use host.docker.internal to reach ComfyUI on the host.
# When running natively, use http://127.0.0.1:8188 or your LAN IP.
COMFYUI_URL=http://host.docker.internal:8188

# ComfyUI allowed hosts — comma-separated hostnames/IPs that bypass SSRF private-IP checks.
# Defaults to "host.docker.internal". Add your ComfyUI server's LAN IP/hostname if
# it's on a different machine, e.g.: host.docker.internal,192.168.1.200,comfyui.local
COMFYUI_ALLOWED_HOSTS=host.docker.internal
```

### Acceptance Tests

- [ ] `docker compose up -d` starts all 3 services
- [ ] `docker compose ps` shows all services as `healthy`
- [ ] `http://localhost:8080` loads the frontend UI
- [ ] `http://localhost:8080/api/health` returns `{"status": "ok", "version": "0.1.0"}` through Nginx proxy
- [ ] `docker compose down` stops all services cleanly
- [ ] `docker compose down` does NOT delete volume data
- [ ] `docker compose down -v` DOES delete volume data

---

## Phase 4: Development Mode Override

**Goal:** Developers can run with hot-reload using `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`.

**FRD Requirements Covered:** FR-13

### Tasks

| # | Task | File | Details |
|---|------|------|---------|
| 4.1 | Create `docker-compose.dev.yml` | `docker-compose.dev.yml` | Override backend: mount source, add `--reload`, expose port 8000. Override frontend: use `Dockerfile.dev`, mount source, expose port 5173 |
| 4.2 | Create `frontend/Dockerfile.dev` | `frontend/Dockerfile.dev` | Simple `node:20-alpine` image with `npm install` and Vite dev server |
| 4.3 | Test development mode | — | Verify hot-reload works for both backend and frontend |

### docker-compose.dev.yml Design

```yaml
services:
  backend:
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - ./backend:/app
      - sprite_projects_data:/app/sprite_projects
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports:
      - "5173:5173"
    volumes:
      - ./frontend/src:/app/src
      - /app/node_modules
    command: ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

### frontend/Dockerfile.dev Design

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

### Acceptance Tests

- [ ] `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` starts dev stack
- [ ] Backend hot-reloads when Python files change
- [ ] Frontend hot-reloads when React files change
- [ ] `http://localhost:5173` loads the frontend in dev mode
- [ ] `http://localhost:8000/api/health` is accessible directly for debugging

---

## Phase 5: GPU Override & Backend Code Changes

**Goal:** GPU training works via override file; proposed env vars are implemented.

**FRD Requirements Covered:** FR-10, FR-11, FR-08 (proposed variables)

### Tasks

| # | Task | File | Details |
|---|------|------|---------|
| 5.1 | Create `docker-compose.gpu.yml` | `docker-compose.gpu.yml` | Add NVIDIA GPU device reservation to backend service |
| 5.2 | Add `COMFYUI_URL` env var support | `backend/app/api/comfyui.py` | Read `COMFYUI_URL` from env as default/fallback when `server_url` is not provided in requests |
| 5.2a | Add `COMFYUI_ALLOWED_HOSTS` env var support | `backend/app/api/comfyui.py` | Comma-separated hostnames/IPs that bypass SSRF private-IP checks. Default: `host.docker.internal`. Allows Docker containers to reach ComfyUI on host/LAN |
| 5.3 | Add `LOG_LEVEL` env var support | `backend/app/main.py` | Read `LOG_LEVEL` from env and configure uvicorn/logging level accordingly |
| 5.4 | Add `/api/health/ready` endpoint (optional) | `backend/app/main.py` | Add readiness probe that checks database connectivity |
| 5.5 | Test GPU override | — | Verify `docker compose -f docker-compose.yml -f docker-compose.gpu.yml config` shows GPU resources |

### docker-compose.gpu.yml Design

```yaml
services:
  backend:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    environment:
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: compute,utility
```

### COMFYUI_URL Implementation Notes

In `backend/app/api/comfyui.py`, the `server_url` field in request models currently has no default. The change would be:

1. Add `COMFYUI_URL = os.environ.get("COMFYUI_URL", "")` at module level
2. Make `server_url` in `TestConnectionRequest` and `SubmitRequest` optional with `default=None`
3. When `server_url` is `None`, fall back to `COMFYUI_URL`
4. If both are empty, return a validation error

### COMFYUI_ALLOWED_HOSTS Implementation Notes

The backend includes SSRF protection that blocks requests to private/internal IP addresses (RFC 1918 ranges). Since ComfyUI typically runs on the same host or LAN as the backend, legitimate connections would be blocked. The `COMFYUI_ALLOWED_HOSTS` environment variable resolves this:

1. Add `COMFYUI_ALLOWED_HOSTS` env var (default: `host.docker.internal`) — comma-separated list of hostnames/IPs
2. In `_validate_server_url()`, skip private-IP checks for hostnames in `_ALLOWED_HOSTS`
3. In `_SSRFSafeTransport.handle_async_request()`, skip SSRF checks for allowed hosts
4. In `_is_private_ip()`, resolve allowed hosts and exempt their IPs from blocking
5. Error messages for blocked private IPs include guidance on adding the hostname to `COMFYUI_ALLOWED_HOSTS`

**Firewall note:** When running in Docker, the host firewall (e.g., UFW) must allow traffic from Docker container IPs (`172.16.0.0/12`) to the ComfyUI port (8188). Without this rule, connections will time out even after SSRF checks pass.

### LOG_LEVEL Implementation Notes

In `backend/app/main.py`:

1. Add `LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()`
2. Pass `log_level=LOG_LEVEL` to uvicorn configuration
3. Configure Python logging level based on `LOG_LEVEL`

### Acceptance Tests

- [ ] `docker compose -f docker-compose.yml -f docker-compose.gpu.yml config` validates
- [ ] `COMFYUI_URL` env var is read as fallback when `server_url` is not provided
- [ ] `COMFYUI_ALLOWED_HOSTS` allows private-IP hostnames to bypass SSRF checks
- [ ] `LOG_LEVEL=debug` increases uvicorn verbosity
- [ ] `/api/health/ready` returns 200 when DB is connected, 503 when not (if implemented)
- [ ] ComfyUI test-connection works from Docker container via `host.docker.internal:8188`
- [ ] ComfyUI test-connection works with LAN IPs added to `COMFYUI_ALLOWED_HOSTS`
- [ ] SSRF protection still blocks cloud metadata endpoints (169.254.169.254)

---

## Phase 6: Documentation & Final Validation

**Goal:** README is updated, all commands documented, full integration test passes.

**FRD Requirements Covered:** FR-01, FR-17, FR-18

### Tasks

| # | Task | File | Details |
|---|------|------|---------|
| 6.1 | Update `README.md` | `README.md` | Add Docker quickstart, development mode, GPU mode, troubleshooting sections |
| 6.2 | Create root `.dockerignore` | `.dockerignore` | Root-level exclusions for any root-context builds |
| 6.3 | Full integration test | — | Run through all success criteria from FRD §12 |
| 6.4 | Verify graceful shutdown | — | `docker compose down` completes within 30s without force-kill |

### README.md Sections to Add

```markdown
## Docker Deployment

### Production Mode

```bash
cp .env.example .env
# Edit .env with your settings
docker compose up -d
```

Access at http://localhost:8080

### Development Mode

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

- Frontend: http://localhost:5173 (hot reload)
- Backend: http://localhost:8000 (hot reload)

### GPU Mode (LoRA Training)

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Requires: NVIDIA drivers + NVIDIA Container Toolkit

### Stopping

```bash
docker compose down          # Stop services (data preserved)
docker compose down -v       # Stop services AND delete all data
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Volume permission errors | `sudo chown -R 1000:1000 sprite_projects_data` |
| ComfyUI unreachable | Set `COMFYUI_URL=http://host.docker.internal:8188` in `.env` |
| ComfyUI "private IP not allowed" error | Add your ComfyUI server's hostname/IP to `COMFYUI_ALLOWED_HOSTS` in `.env` (e.g., `COMFYUI_ALLOWED_HOSTS=host.docker.internal,192.168.1.200`) |
| ComfyUI connection times out from Docker | Ensure host firewall allows Docker containers to reach port 8188: `sudo ufw insert 2 allow from 172.16.0.0/12 to any port 8188 proto tcp` |
| Backend won't start | Check `docker compose logs backend` |
| Frontend shows blank page | Check `docker compose logs frontend` |
```

### Acceptance Tests (FRD §12 Success Criteria)

- [ ] 1. `docker compose up -d` starts the production stack
- [ ] 2. All health checks pass
- [ ] 3. UI accessible at `http://localhost:8080`
- [ ] 4. API requests work through Nginx reverse proxy
- [ ] 5. Prompt generation and character management work
- [ ] 6. Reference image upload persists across restarts
- [ ] 7. ComfyUI integration works with `server_url` per-request and via `COMFYUI_URL` env var fallback
- [ ] 7a. ComfyUI test-connection works from Docker container via `host.docker.internal:8188`
- [ ] 7b. LAN IPs in `COMFYUI_ALLOWED_HOSTS` bypass SSRF private-IP checks
- [ ] 7c. Cloud metadata endpoints (169.254.169.254) are still blocked by SSRF protection
- [ ] 8. LoRA training subprocess works (CPU-only base)
- [ ] 9. GPU override works on NVIDIA-equipped host
- [ ] 10. `docker compose down` preserves data
- [ ] 11. `docker compose down -v` documented as destructive
- [ ] 12. Development mode works with hot reload
- [ ] 13. No sensitive values in version control
- [ ] 14. No functionality lost vs. native run

---

## File Creation Order

Files should be created in this order to allow incremental testing:

| Order | File | Phase | Can Test After |
|-------|------|-------|---------------|
| 1 | `backend/.dockerignore` | 1 | — |
| 2 | `backend/Dockerfile` | 1 | Backend image builds |
| 3 | `frontend/.dockerignore` | 2 | — |
| 4 | `frontend/nginx.conf` | 2 | — |
| 5 | `frontend/Dockerfile` | 2 | Frontend image builds |
| 6 | `docker-compose.yml` | 3 | Full stack starts |
| 7 | `.env.example` (update) | 3 | Full stack starts |
| 8 | `.gitignore` (update) | 3 | — |
| 9 | `frontend/Dockerfile.dev` | 4 | Dev mode works |
| 10 | `docker-compose.dev.yml` | 4 | Dev mode works |
| 11 | `docker-compose.gpu.yml` | 5 | GPU config validates |
| 12 | `backend/app/api/comfyui.py` (update) | 5 | COMFYUI_URL and COMFYUI_ALLOWED_HOSTS work |
| 13 | `backend/app/main.py` (update) | 5 | LOG_LEVEL works |
| 14 | `.dockerignore` (root) | 6 | — |
| 15 | `README.md` (update) | 6 | — |

---

## Estimated Effort

| Phase | Description | Estimated Time |
|-------|-------------|---------------|
| 1 | Backend Dockerfile | 1–2 hours |
| 2 | Frontend Dockerfile + Nginx | 1–2 hours |
| 3 | Docker Compose production stack | 1–2 hours |
| 4 | Development mode override | 1 hour |
| 5 | GPU override + backend code changes | 2–3 hours |
| 6 | Documentation + final validation | 1–2 hours |
| **Total** | | **7–12 hours** |

---

## Open Questions to Resolve Before Implementation

These are carried forward from FRD §13 and should be decided before starting:

1. **LoRA training location** — Keep in backend container for now (simpler), or separate worker? **Recommendation:** Keep in backend container for initial implementation; refactor to worker if image size becomes problematic.
2. **Backend port exposure** — Only in dev mode? **Recommendation:** Yes, only expose `127.0.0.1:8000` in dev override.
3. **Health endpoint DB check** — Add readiness probe? **Recommendation:** Skip for initial implementation; add `/api/health/ready` later if needed.
4. **Upload size** — 10 MB (matches current `MAX_REQUEST_BODY_SIZE`). **Recommendation:** Keep at 10 MB; configure in Nginx via `client_max_body_size`.
5. **Training backends** — Install in image or mount? **Recommendation:** Mount from host for now; document the approach.
6. **SQLite support** — Keep SQLite for non-container dev? **Recommendation:** Yes, keep SQLite as fallback for native development; PostgreSQL required for containers.