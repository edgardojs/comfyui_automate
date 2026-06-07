# Containerization Functional Requirements Document (FRD)

**Project:** ComfyUI Sprite Character Prompt Generator  
**Document Version:** 1.2  
**Date:** 2026-06-02  
**Status:** Draft — Corrected Review Version  
**Scope:** Docker-based local deployment for frontend, backend, PostgreSQL, persistent project storage, external ComfyUI connectivity, and optional GPU-enabled LoRA training support.

---

## 1. Purpose

This document defines the functional requirements for containerizing the **ComfyUI Sprite Character Prompt Generator** application.

The goal is to allow the application stack to run through Docker Compose with minimal manual setup while preserving existing application behavior, including:

- Backend API functionality
- Frontend web interface
- PostgreSQL persistence
- Reference image and generated asset storage
- ComfyUI API integration
- LoRA training subprocess support
- Optional GPU-enabled training through an override configuration

The target user should be able to start the application with Docker Compose, access the UI from a browser, connect the backend to an external ComfyUI instance, and preserve generated project data across container restarts and rebuilds.

---

## 2. Current Architecture

| Component | Runtime | Notes |
|---|---|---|
| Backend | Python 3.12+ / FastAPI / Uvicorn | Currently runs natively through Uvicorn |
| Frontend | React 19 / Vite | Development server via `npm run dev`; production build via `vite build` |
| Database | PostgreSQL 16.9 | Already containerized through Docker Compose |
| File Storage | Local filesystem: `./sprite_projects/` | Stores reference images, datasets, LoRA outputs, previews, and generated assets |
| ComfyUI | External HTTP API | Runs separately and is not part of this project’s base container stack |
| LoRA Training | Subprocess execution | Uses `training_runner.py` to call kohya_ss, ai_toolkit, or equivalent training backends |

---

## 3. Target Architecture

### 3.1 Container Topology

```text
┌────────────────────────────────────────────────────────────┐
│                    Docker Bridge Network                   │
│                                                            │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────┐ │
│  │  frontend    │      │   backend    │      │ postgres │ │
│  │  nginx :80   │─────▶│ FastAPI :8000│─────▶│  :5432   │ │
│  └──────────────┘      └──────────────┘      └──────────┘ │
│         │                    │                             │
│         │                    ▼                             │
│         │          ┌────────────────────┐                  │
│         │          │ sprite_projects    │                  │
│         │          │ persistent volume  │                  │
│         │          └────────────────────┘                  │
└─────────┼──────────────────────────────────────────────────┘
          │
          ▼
Host browser
http://localhost:8080

External dependency:
ComfyUI API, typically available at http://host.docker.internal:8188
```

### 3.2 Target Services

| Service | Suggested Base Image | Internal Port | Host Exposure | Responsibility |
|---|---:|---:|---|---|
| `frontend` | `nginx:alpine` | 80 | `8080:80` | Serves production React build and reverse-proxies API traffic |
| `backend` | `python:3.12-slim` | 8000 | Not exposed in production | FastAPI app, project storage handling, ComfyUI API calls, LoRA subprocess orchestration |
| `postgres` | `postgres:16.9-alpine` | 5432 | `127.0.0.1:5432:5432`, optional | PostgreSQL database |

---

## 4. Assumptions and Constraints

1. ComfyUI is an external dependency and is not included in the base Docker Compose stack.
2. The application is intended as a local-first tool, not a public internet-facing production service.
3. PostgreSQL is the required database backend for the containerized deployment.
4. Docker Compose is the target orchestration method.
5. GPU support for LoRA training is optional and must be enabled through a separate override file.
6. The production frontend must be served by Nginx, not by the Vite development server.
7. Runtime secrets must be provided through environment variables or `.env`; secrets must not be baked into images.

---

## 5. Functional Requirements

---

### FR-01: Single-Command Production Startup

**Requirement:**  
The production application stack must start using Docker Compose with a single command.

**Acceptance Criteria:**

- `docker compose up -d` starts the production stack.
- The production stack includes frontend, backend, and PostgreSQL services.
- All required services reach a healthy status.
- The application UI is accessible at `http://localhost:8080`.
- No manual runtime steps are required beyond creating or updating the `.env` file.
- Existing user data persists across restarts.

---

### FR-02: Backend Containerization

**Requirement:**  
The FastAPI backend must run inside a Docker container with all required runtime dependencies installed during image build.

**Acceptance Criteria:**

- Backend image builds successfully from the backend source directory.
- Python dependencies are installed from `requirements.txt` or equivalent dependency file.
- Uvicorn starts with host binding set to `0.0.0.0` and port `8000`.
- Backend logs are written to stdout and stderr.
- All existing backend API routes behave the same as in the native run.
- Backend container uses environment variables for runtime configuration.
- Backend container does not require manual shell access to start the API.

**Implementation Guidance:**

- Suggested base image: `python:3.12-slim`
- Suggested working directory: `/app`
- Suggested command:

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### FR-03: Backend Health Endpoint

**Requirement:**  
The backend must expose a lightweight health endpoint for container health checks.

**Acceptance Criteria:**

- Backend exposes `/api/health` (this endpoint already exists and returns `{"status": "ok", "version": "0.1.0"}`).
- The endpoint returns HTTP 200 when the API process is running.
- Docker health checks use `/api/health` instead of `/docs`.
- Health check failure causes Docker to report the service as unhealthy.

**Note on Database Readiness:**  
The current `/api/health` endpoint only verifies that the API process is alive — it does **not** check database connectivity. A separate readiness check that verifies the database connection could be added in the future (e.g., `/api/health/ready`), but for the initial containerization, liveness-only checking is sufficient since the backend already retries database connections on startup.

**Recommended Health Check:**

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 15s
```

---

### FR-04: Frontend Containerization

**Requirement:**  
The React frontend must be built into static assets and served from an Nginx container in production mode.

**Acceptance Criteria:**

- Frontend image uses a multi-stage build.
- Build stage installs frontend dependencies and runs the production build.
- Runtime stage serves static files through Nginx.
- No Vite development server runs in the production frontend container.
- The React app is served from `/usr/share/nginx/html` or equivalent Nginx web root.
- Browser access to `http://localhost:8080` loads the frontend successfully.
- SPA routing works through an Nginx fallback to `index.html`.

**Implementation Guidance:**

- Suggested build image: `node:20-alpine`
- Suggested runtime image: `nginx:alpine`
- Use `npm ci` when a lockfile is present.
- Use `npm run build` to create production assets.

---

### FR-05: Frontend Reverse Proxy

**Requirement:**  
The frontend Nginx container must reverse-proxy backend API requests to the backend service over Docker DNS.

**Acceptance Criteria:**

- Requests to `/api/*` are proxied to `http://backend:8000`.
- Required proxy headers are forwarded:
  - `Host`
  - `X-Real-IP`
  - `X-Forwarded-For`
  - `X-Forwarded-Proto`
- WebSocket upgrade headers are supported for future compatibility.
- Client upload size limit matches backend upload requirements.
- Static assets are served efficiently.

**Recommended Nginx Behavior:**

```nginx
location /api/ {
    set $backend_upstream http://backend:8000;
    proxy_pass $backend_upstream;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}

location / {
    try_files $uri /index.html;
}
```

---

### FR-06: PostgreSQL Service

**Requirement:**  
The containerized stack must use PostgreSQL as the database service.

**Acceptance Criteria:**

- PostgreSQL runs as a Docker Compose service.
- PostgreSQL data is stored in a persistent named volume.
- PostgreSQL reads credentials and database name from `.env`.
- Backend connects to PostgreSQL by using the Docker service hostname `postgres`.
- PostgreSQL health check uses `pg_isready`.
- PostgreSQL is healthy before the backend attempts startup.

**Recommended Environment Variables:**

```env
POSTGRES_USER=sprite_user
POSTGRES_PASSWORD=CHANGE_ME_strong_password_here
POSTGRES_DB=sprite_prompt_generator
DATABASE_URL=postgresql+asyncpg://sprite_user:CHANGE_ME_strong_password_here@postgres:5432/sprite_prompt_generator
```

---

### FR-07: Persistent Project File Storage

**Requirement:**  
User-generated project files must persist across container restarts, rebuilds, and normal shutdowns.

**Acceptance Criteria:**

- Backend mounts a persistent named volume at `/app/sprite_projects`.
- The backend uses `SPRITE_PROJECTS_DIR=/app/sprite_projects`.
- Reference images, datasets, previews, LoRA outputs, and generated assets are written to the persistent volume.
- Project files survive `docker compose down`.
- Project files survive image rebuilds.
- Project files are deleted only when the user intentionally removes the volume, such as by running `docker compose down -v`.
- The backend application user has read/write permission to the mounted volume.

**Required Volumes:**

| Volume | Mount Point | Used By | Purpose |
|---|---|---|---|
| `sprite_projects_data` | `/app/sprite_projects` | backend | Project files, uploads, datasets, generated assets, LoRA outputs |
| `pgdata` | `/var/lib/postgresql/data` | postgres | PostgreSQL database files |

---

### FR-08: Environment Variable Configuration

**Requirement:**  
All runtime configuration must be injectable through environment variables and documented in `.env.example`.

**Acceptance Criteria:**

- `.env.example` includes all required variables.
- `.env` is excluded from version control.
- Backend reads configuration from environment variables.
- PostgreSQL reads user, password, and database name from environment variables.
- Frontend production container uses Nginx proxying and does not require runtime Vite environment injection unless explicitly needed.
- No passwords, API keys, or sensitive values are committed to source control.

**Required Variables:**

```env
# PostgreSQL
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
# This is needed because ComfyUI typically runs on the host or LAN, which uses private IPs.
# Defaults to "host.docker.internal" which is Docker's standard host gateway.
# Add your ComfyUI server's LAN IP/hostname if it's on a different machine, e.g.:
# COMFYUI_ALLOWED_HOSTS=host.docker.internal,192.168.1.200,comfyui.local
```

**Proposed New Variables:**

| Variable | Status | Notes |
|---|---|---|
| `COMFYUI_URL` | ✅ Implemented | Default/fallback ComfyUI server URL. When set, the frontend can omit `server_url` in requests. Use `http://host.docker.internal:8188` in Docker, `http://127.0.0.1:8188` natively. |
| `COMFYUI_ALLOWED_HOSTS` | ✅ Implemented | Comma-separated hostnames/IPs that bypass SSRF private-IP checks. Defaults to `host.docker.internal`. Required when ComfyUI runs on a LAN IP (e.g., `192.168.x.x`) that would otherwise be blocked by SSRF protection. |
| `LOG_LEVEL` | ✅ Implemented | Controls uvicorn/application verbosity. Defaults to `INFO`. |

---

### FR-09: External ComfyUI Connectivity

**Requirement:**  
The backend container must be able to communicate with an external ComfyUI instance.

**Current Behavior:**  
The backend receives the ComfyUI server URL **per-request** from the frontend (via the `server_url` field in API request bodies such as `TestConnectionRequest` and `SubmitRequest`). When `server_url` is not provided, the `COMFYUI_URL` environment variable is used as a fallback default.

**SSRF Protection and Allowed Hosts:**

The backend includes SSRF (Server-Side Request Forgery) protection that blocks requests to private/internal IP addresses (RFC 1918 ranges: `10.x.x.x`, `172.16.x.x`, `192.168.x.x`, etc.) and cloud metadata endpoints. This prevents malicious requests from reaching internal services.

Since ComfyUI typically runs on the same host or LAN as the backend, the SSRF protection would block legitimate ComfyUI connections. To resolve this, the `COMFYUI_ALLOWED_HOSTS` environment variable allows specific hostnames and IPs to bypass private-IP checks:

- **Default:** `host.docker.internal` (Docker's standard host gateway)
- **Loopback addresses** (`127.x.x.x`) are always allowed
- **Add your ComfyUI server's LAN IP/hostname** if it runs on a different machine (e.g., `COMFYUI_ALLOWED_HOSTS=host.docker.internal,192.168.1.200,comfyui.local`)

**Firewall Consideration:**

When running in Docker, the host firewall (e.g., UFW) must allow traffic from Docker container IPs to the ComfyUI port. For UFW:

```bash
# Allow Docker containers (172.16.0.0/12) to reach ComfyUI on port 8188
sudo ufw insert 2 allow from 172.16.0.0/12 to any port 8188 proto tcp comment "Allow Docker containers to reach ComfyUI"
```

**Acceptance Criteria:**

- ✅ The backend can reach ComfyUI instances on the host network.
- ✅ Docker Compose includes `extra_hosts` mapping for Linux host access:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

- ✅ The backend connection test endpoint (`/api/comfyui/test`) works from inside the container.
- ✅ SSRF and outbound URL validation protections in `comfyui.py` remain active.
- ✅ `COMFYUI_ALLOWED_HOSTS` allows specific hostnames/IPs to bypass private-IP checks.
- ✅ ComfyUI connection failures are logged clearly and returned to the user as actionable errors.
- ✅ Error messages include guidance on adding the hostname to `COMFYUI_ALLOWED_HOSTS`.

---

### FR-10: LoRA Training Subprocess Support

**Requirement:**  
The backend container must support LoRA training subprocess execution without losing existing training workflow behavior.

**Acceptance Criteria:**

- `training_runner.py` can spawn configured training commands from inside the backend container.
- Training outputs are written to `/app/sprite_projects` or subdirectories under it.
- Training logs are persisted or retrievable through the application.
- Cancellation or shutdown signals are propagated to child training processes.
- Zombie subprocesses are avoided.
- CPU-only subprocess execution is supported in the base container where feasible.
- GPU-enabled training is supported through a separate Docker Compose override file.

**Implementation Guidance:**

- Use `init: true` in the backend service to improve signal handling.
- Add required runtime packages intentionally.
- Do not install unnecessary training dependencies in the base image if they substantially increase image size.
- Consider a separate training worker image if GPU training dependencies become too large or complex.

---

### FR-11: Optional GPU Override for LoRA Training

**Requirement:**  
GPU-enabled LoRA training must be available through an optional Docker Compose override file.

**Acceptance Criteria:**

- A `docker-compose.gpu.yml` file is provided.
- GPU override does not affect users who run the standard CPU/local stack.
- GPU override documents NVIDIA container runtime requirements.
- GPU override enables backend or training worker access to GPU devices.
- GPU-enabled training writes outputs to the same persistent project volume.

**Example Invocation:**

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

### FR-12: Docker Networking

**Requirement:**  
The application services must communicate over a user-defined Docker bridge network.

**Acceptance Criteria:**

- Docker Compose creates a user-defined bridge network named `app_network` or equivalent.
- Frontend, backend, and PostgreSQL services are attached to the same network.
- Services resolve each other by Compose service name.
- Frontend reaches backend using `http://backend:8000`.
- Backend reaches PostgreSQL using the hostname `postgres`.
- Only necessary ports are exposed to the host.

**Production Port Exposure:**

| Service | Host Exposure | Required? | Notes |
|---|---:|---|---|
| frontend | `8080:80` | Yes | Main browser entry point |
| backend | None | No | Access through frontend Nginx proxy |
| postgres | `127.0.0.1:5432:5432` | Optional | Useful for local debugging; should not bind publicly |

---

### FR-13: Development Mode Support

**Requirement:**  
Developers must be able to run the application in development mode with hot reload.

**Acceptance Criteria:**

- A separate development override file is provided.
- Recommended filename: `docker-compose.dev.yml`.
- Backend source code is mounted into the backend container.
- Backend runs Uvicorn with `--reload` in development mode.
- Frontend source code is mounted into a development frontend container.
- Frontend runs the Vite development server in development mode.
- Development mode must not be confused with production mode.
- Documentation clearly states which Compose command starts each mode.

**Required Commands:**

Production:

```bash
docker compose -f docker-compose.yml up -d
```

Development:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

**Important Note:**  
The development override should not be named `docker-compose.override.yml` unless automatic override behavior is intentional. Docker Compose automatically applies `docker-compose.override.yml` when present.

---

### FR-14: Health Checks and Service Readiness

**Requirement:**  
Each service must expose a reliable health check for Docker Compose readiness.

**Acceptance Criteria:**

- PostgreSQL uses `pg_isready`.
- Backend uses `/api/health` (the existing endpoint).
- Frontend uses an HTTP request to `/`.
- Backend depends on PostgreSQL health before startup.
- Frontend depends on backend health before startup.
- Health check commands use tools available in the image.

**Frontend Health Check Guidance:**

Because `nginx:alpine` may not include `curl` by default, either:

1. Use `wget` if available, or
2. Install `curl` intentionally during image build, or
3. Use an alternative lightweight health check command.

Example:

```yaml
healthcheck:
  test: ["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1:80/ || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 3
```

---

### FR-15: Security Requirements

**Requirement:**  
Containers must follow reasonable Docker security practices for a local-first application.

**Acceptance Criteria:**

- Backend container runs as a non-root user where feasible.
- Frontend container runs as a non-root user where feasible.
- Secrets are not baked into images.
- `.env` is listed in `.gitignore`.
- `.env.example` contains only placeholder values.
- Unnecessary host ports are not exposed.
- PostgreSQL, if exposed, binds only to `127.0.0.1`.
- Docker images use minimal base images.
- Build context excludes unnecessary files.
- File permissions for mounted volumes are documented.

**Recommended UID/GID Handling:**

The backend should support configurable application user IDs to reduce volume permission issues:

```env
APP_UID=1000
APP_GID=1000
```

If UID/GID customization is not implemented, documentation must explain how to fix volume ownership issues.

---

### FR-16: Build Caching and Build Efficiency

**Requirement:**  
Docker builds must use layer caching effectively.

**Acceptance Criteria:**

- Backend dependency files are copied before backend source code.
- Frontend dependency files are copied before frontend source code.
- Backend image rebuilds should not reinstall dependencies when only source code changes.
- Frontend image rebuilds should not reinstall dependencies when only source code changes.
- `.dockerignore` files exclude unnecessary files.

**Required Exclusions:**

```text
.git
node_modules
.venv
venv
__pycache__
.pytest_cache
.mypy_cache
.dist
build
dist
sprite_projects
*.db
*.sqlite
.env
```

---

### FR-17: Graceful Shutdown

**Requirement:**  
The stack must shut down cleanly without data corruption or orphaned processes.

**Acceptance Criteria:**

- Uvicorn receives SIGTERM and exits cleanly.
- PostgreSQL receives SIGTERM and shuts down cleanly.
- Running training subprocesses receive cancellation or termination signals.
- `docker compose down` completes without force-killing services under normal conditions.
- Documentation explains that `docker compose down -v` deletes persistent volumes.

---

### FR-18: Logging and Debugging

**Requirement:**  
Container logs must support routine debugging.

**Acceptance Criteria:**

- Backend logs to stdout and stderr.
- Frontend Nginx logs access and error output to Docker logs.
- PostgreSQL logs are accessible through Docker logs.
- `docker compose logs -f` shows logs for all services.
- `docker compose logs backend` shows backend application logs.
- `LOG_LEVEL` or equivalent variable controls backend verbosity.
- ComfyUI connection failures and training subprocess failures are logged with actionable context.

---

### FR-19: Image Size Management

**Requirement:**  
Production images must remain reasonably sized for local development and deployment.

**Acceptance Criteria:**

- Frontend production image target is under 50 MB where feasible.
- Backend base image target is under 500 MB when LoRA/GPU training dependencies are not bundled.
- GPU or training-heavy image variants may exceed 500 MB if documented.
- Development dependencies are not installed in production images unless required.
- Multi-stage builds are used where beneficial.

---

## 6. Required File Deliverables

| File | Action | Description |
|---|---|---|
| `backend/Dockerfile` | Create | Backend production image definition |
| `frontend/Dockerfile` | Create | Frontend production multi-stage image definition |
| `frontend/nginx.conf` | Create | Nginx configuration for SPA routing and API reverse proxy |
| `docker-compose.yml` | Modify/Create | Production Compose stack |
| `docker-compose.dev.yml` | Create | Development hot-reload override |
| `docker-compose.gpu.yml` | Create | Optional GPU-enabled training override |
| `frontend/Dockerfile.dev` | Create | Frontend development image for Vite dev server with hot reload |
| `.dockerignore` | Create | Root build context exclusions, if root context is used |
| `backend/.dockerignore` | Create | Backend-specific exclusions |
| `frontend/.dockerignore` | Create | Frontend-specific exclusions |
| `.env.example` | Modify/Create | Document required environment variables |
| `.gitignore` | Modify | Ensure `.env` and generated artifacts are excluded |
| `README.md` | Modify | Add Docker quickstart, development mode, GPU mode, and troubleshooting |

---

## 7. Target Production Docker Compose Specification

```yaml
services:
  postgres:
    image: postgres:16.9-alpine
    container_name: sprite_prompt_db
    env_file: .env
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER:-sprite_user} -d $${POSTGRES_DB:-sprite_prompt_generator}"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - app_network

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: sprite_prompt_api
    env_file: .env
    environment:
      SPRITE_PROJECTS_DIR: /app/sprite_projects
      CORS_ORIGINS: http://localhost:8080
    expose:
      - "8000"
    volumes:
      - sprite_projects_data:/app/sprite_projects
    depends_on:
      postgres:
        condition: service_healthy
    extra_hosts:
      - "host.docker.internal:host-gateway"
    init: true
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    restart: unless-stopped
    networks:
      - app_network

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: sprite_prompt_web
    ports:
      - "8080:80"
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "wget -q --spider http://localhost/ || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - app_network

volumes:
  pgdata:
  sprite_projects_data:

networks:
  app_network:
    driver: bridge
```

---

## 8. Recommended Development Compose Override

Filename:

```text
docker-compose.dev.yml
```

Example:

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
      - ./frontend:/app
      - /app/node_modules
    command: ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

Run development mode with:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

---

## 9. Recommended GPU Compose Override

Filename:

```text
docker-compose.gpu.yml
```

Example:

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

Run GPU-enabled mode with:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Documentation must explain host requirements, including NVIDIA drivers and NVIDIA Container Toolkit.

---

## 10. Non-Goals

The following are out of scope for this containerization effort:

- Containerizing ComfyUI itself
- Kubernetes manifests
- Helm charts
- CI/CD pipeline implementation
- Public production TLS termination
- Public internet deployment hardening
- Multi-architecture builds
- Cloud deployment automation
- Replacing the existing application architecture

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ComfyUI is unreachable from backend container | Prompt submission or preview generation fails | Add `host.docker.internal` mapping for Linux host access; provide connection test endpoint (`/api/comfyui/test-connection`); proposed `COMFYUI_URL` env var would allow a default server URL |
| Volume permission issues | Backend cannot read or write project files | Run backend with documented UID/GID strategy; document ownership fixes |
| GPU training dependencies increase backend image size | Slow builds and large images | Keep GPU/training dependencies in override image or separate worker where feasible |
| LoRA subprocesses do not receive termination signals | Zombie processes or stuck training jobs | Use `init: true`; explicitly propagate SIGTERM/SIGINT to child processes |
| PostgreSQL credentials are inconsistent | Backend cannot connect to database | Keep `.env.example`, Compose, and application defaults aligned |
| Development override is accidentally applied in production | Production runs with hot reload or dev server | Use `docker-compose.dev.yml` instead of automatic `docker-compose.override.yml` |
| Backend health check uses wrong endpoint | Health check fails silently | Use the existing `/api/health` endpoint (not `/health` or `/docs`) |
| Frontend health check uses missing binary | Health check fails even when Nginx works | Use available tool such as `wget` or install `curl` intentionally |

---

## 12. Success Criteria

Containerization is considered successful when:

1. `docker compose -f docker-compose.yml up -d` starts the production stack.
2. PostgreSQL, backend, and frontend health checks pass.
3. The UI is accessible at `http://localhost:8080`.
4. Backend API requests work through the frontend Nginx reverse proxy.
5. Prompt generation and character management work as before.
6. Reference image upload and generated asset storage persist across restarts.
7. ComfyUI integration works when the frontend passes `server_url` per-request, or when the proposed `COMFYUI_URL` default is configured.
8. LoRA training subprocess execution works in the base environment where supported.
9. GPU-enabled LoRA training works when the GPU override is used on a properly configured host.
10. `docker compose down` does not delete user data.
11. `docker compose down -v` is documented as destructive.
12. Development mode works through `docker-compose.dev.yml` with hot reload.
13. No sensitive configuration values are committed to version control.
14. No required functionality from the native run is lost.

---

## 13. Open Questions

The following items should be confirmed before implementation is considered final:

1. Should LoRA training run inside the backend container, or should it be moved to a dedicated worker container?
2. Should direct backend host access on `127.0.0.1:8000` be enabled only in development mode?
3. Should the backend health endpoint verify database connectivity (readiness probe), or should it only verify API process liveness? The current `/api/health` endpoint only checks liveness. A separate `/api/health/ready` endpoint could be added for readiness.
4. What maximum upload size is required for reference images and datasets?
5. Are training backends expected to be installed inside the image, mounted from the host, or configured as separate services?
6. Should the application support both PostgreSQL and SQLite in non-container development, or should PostgreSQL be required everywhere?

