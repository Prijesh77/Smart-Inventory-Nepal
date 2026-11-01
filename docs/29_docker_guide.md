# Docker Guide for This Project (step by step)

## 1. The ideas in plain words

| Word | Meaning | In this project |
|---|---|---|
| **Image** | A packed, read-only "box" with an operating system, programs and our code. Built once from a recipe. | `smart-inventory-api` (Python + FastAPI + our code), `smart-inventory-web` (nginx + built React files), `postgres:16.4` (downloaded) |
| **Dockerfile** | The recipe for building one image. | `backend/Dockerfile`, `frontend/Dockerfile` |
| **Container** | A running copy of an image, like a small separate computer. | `db`, `api`, `web` |
| **Volume** | Storage that survives when a container is deleted. | `pgdata`: the database files |
| **Named volume** (models) | Storage Docker keeps between restarts, like `pgdata`. | `models`: each shop's trained forecast model |
| **Docker Compose** | One file that describes all containers and starts them together. | `docker-compose.yml` |
| **Port mapping** | "Requests to this port on my PC go to that port in the container." | `8080` → web, `5433` → database |

How the three containers work together:

```
Your browser ──► localhost:8080 ──► web (nginx) ──► /api/... ──► api (FastAPI) ──► db (PostgreSQL)
                                     serves React                 reads data/, models/ (mounted)
```

**Why Docker?** Anyone, including an examiner, can run the whole system with the same versions using a few commands, without installing Python, Node or PostgreSQL. And Windows Smart App Control does not matter inside containers, because they run Linux.

## 2. Before you start (one time)

### 2.1 Make Docker Desktop start

Docker Desktop crashes on this PC because of its "Model Runner" (AI) feature. Turn it off:

1. Close Docker Desktop completely (right-click its tray icon → **Quit Docker Desktop**).
2. Press **Win + R**, type `%APPDATA%\Docker` and press Enter.
3. Open `settings-store.json` with Notepad.
4. Find the setting(s) with **`Inference`** in the name (for example `"EnableInference": true`) and change `true` to `false`. Save.
5. Start **Docker Desktop**. Wait until the bottom-left says **Engine running** (about 1 minute).

If Docker Desktop opens long enough, you can do the same through **Settings → AI → untick "Enable Docker Model Runner" → Apply & restart**.

Check in a terminal:

```bash
docker version
```

You should see both a **Client** and a **Server** section. If "Server" shows an error, the engine is not running yet.

### 2.2 Check `.env`

Open `.env` in VS Code. Docker needs these lines (they are already there; do not share their values):

| Line | Used for |
|---|---|
| `POSTGRES_DB=inventory` | Name of the database **inside Docker** |
| `POSTGRES_USER=inventory` | Database user inside Docker |
| `POSTGRES_PASSWORD=...` | Its password. The Docker database is created with it the first time |
| `POSTGRES_PORT=5433` | Port on your PC for the Docker database (5432 is already used by your installed PostgreSQL) |
| `JWT_SECRET_KEY=...` | Signs login tokens. **Required**: Compose stops with an error if it is empty |
| `WEB_PORT=8080` | Optional: the web address port (add this line if missing) |

The `DATABASE_URL` line is **not** used by Docker: `docker-compose.yml` builds its own address pointing to the `db` container.

### 2.3 No data files are needed

The image needs no research data. Each shop's data lives in the database, and its trained
forecast model in the `models` volume. Load the synthetic demo shop with
`docker compose run --rm api python scripts/seed.py` if you want something to look at, or
create a real shop with `scripts/create_shop.py`.

## 3. Start the system

Open a terminal **in the project folder**. In VS Code: Terminal → New Terminal.

### Step 1: build the images and start everything

```bash
docker compose up -d --build
```

- `--build` builds the API and web images from the Dockerfiles. **The first time takes about 3–8 minutes**: it downloads Python, Node, nginx and PostgreSQL, and installs pandas, scikit-learn and so on. Later builds are much faster because Docker reuses unchanged layers.
- `-d` ("detached") runs the containers in the background, so you get your terminal back.

What happens, in order:

1. `db` starts. Its health check waits until PostgreSQL accepts connections.
2. `api` starts only when `db` is healthy. It runs `alembic upgrade head` (creates the 18 tables), then starts FastAPI.
3. `web` starts only when `api` is healthy.

### Step 2: check that all three are running

```bash
docker compose ps
```

Expected: `db`, `api` and `web` with STATUS **Up … (healthy)**. The api may show `(health: starting)` for about 20 s.

### Step 3: load the project data (first time only)

```bash
docker compose run --rm api python scripts/seed.py
```

- `run` starts a **temporary** extra container from the `api` image to run one command; `--rm` deletes it afterwards.
- Expected output: 3 categories, 5 suppliers, 1,969 calendar days, 267 products, 457,480 sales rows, `Seeded in … s`.

### Step 4: create your admin account (first time only)

```bash
docker compose run --rm -it api python scripts/create_user.py --email you@example.com --name "Prijesh" --role admin
```

- `-it` makes it **interactive**, so you can type the password. It is hidden while you type (at least 10 characters).
- This account lives in the **Docker** database. It is separate from the account in your installed PostgreSQL.

### Step 5: open the app

Open **http://localhost:8080** and log in. Try "Run forecast & recommendations" on the Overview page.

### Verified on this PC (30 Oct 2026)

- **First build and start-up:** about 4½ minutes, including downloading the base images; images and containers built and started without errors.
- **Start-up order:** `db` healthy after 7.5 s, then `api` healthy after 12 s (migrations applied), then `web` started.
- **Seed:** 267 products loaded; admin account created.
- **Full run:** "Run forecast & recommendations" completed inside Docker. The risk counts were **identical to the Windows run**: 5 critical, 48 reorder soon, 175 healthy, 39 excess. Same code, model and data give the same decisions on Linux.

## 4. Everyday commands

| Task | Command |
|---|---|
| See what is running | `docker compose ps` |
| Follow the API's log (Ctrl+C to stop following) | `docker compose logs -f api` |
| Last 50 log lines of everything | `docker compose logs --tail 50` |
| Stop everything (data is kept) | `docker compose stop` |
| Start again | `docker compose start` |
| Stop and remove the containers (data is **kept** in the volume) | `docker compose down` |
| **Delete everything including the database** (start from zero) | `docker compose down -v` |
| Rebuild after you change code | `docker compose up -d --build` |
| Rebuild only the frontend | `docker compose up -d --build web` |
| Open a shell inside the API container | `docker compose exec api sh` (type `exit` to leave) |
| Check the database connection from inside | `docker compose exec api python scripts/check_db.py` |
| Open the Docker database in pgAdmin | Host `localhost`, port **5433**, user/password from `.env` |
| See image sizes | `docker images` |
| Free disk space from old images | `docker image prune` |

**Important difference:** `down` keeps your data; `down -v` deletes the database volume (you would need to seed and create the admin again).

## 5. What runs where (useful for the viva)

| | Local development | Docker |
|---|---|---|
| Web address | http://localhost:5173 (Vite, hot reload) | http://localhost:8080 (nginx, built files) |
| API | uvicorn on your PC, port 8000 | `api` container, reachable only through nginx |
| Database | Installed PostgreSQL 18, port 5432, database `inventory` | `db` container, PostgreSQL 16.4, port 5433 |
| Python packages | `.venv` on Windows | Inside the Linux image |

Both can run at the same time: they use different ports and different databases.

## 6. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `error during connect … dockerDesktopLinuxEngine` | The Docker engine is not running. Start Docker Desktop and wait for "Engine running" (section 2.1) |
| `required variable JWT_SECRET_KEY is missing a value` | Add `JWT_SECRET_KEY=…` to `.env` |
| `Bind for 0.0.0.0:8080 failed: port is already allocated` | Something else uses 8080. Set `WEB_PORT=8081` in `.env` and open http://localhost:8081 |
| Same for port 5433 | Set `POSTGRES_PORT=5434` in `.env` |
| `api` keeps restarting (`docker compose ps`) | Read `docker compose logs api`. Often a wrong password: the Docker database keeps the password it was **first** created with. If you changed `POSTGRES_PASSWORD` later, run `docker compose down -v` and start again |
| Login works but "Run forecast" fails with "Model file … not found" | `models/random_forest_v1_final.joblib` is missing. Run `scripts\reproduce_all.py` (or the Random Forest script), then `docker compose restart api` |
| `seed.py` says "Database already has 267 products" | It refuses to load twice. Use `docker compose run --rm api python scripts/seed.py --reset` to wipe and reload (**this also deletes the users**) |
| Page shows "Cannot reach the server" | The `api` container is not healthy yet, or crashed. Check `docker compose ps` and the logs |
| Changes to the code don't appear | Images contain a copy of the code. Rebuild: `docker compose up -d --build` |
| First build is very slow or fails downloading | Check your internet connection; run the same command again (finished layers are reused) |

## 7. What the files do (to explain in the report)

- **`backend/Dockerfile`:**
  - starts from `python:3.12.7-slim`;
  - installs only the API's packages (`backend/requirements-api.txt`);
  - copies `ml/` and `backend/` (code and the festival calendar only; no shop data);
  - creates a normal user and the `/app/models` folder it owns, and runs as that user, not root;
  - on start, migrates the database, then runs uvicorn.
- **`frontend/Dockerfile`** has two stages:
  - **build:** Node 20 runs `npm ci` and `npm run build`;
  - **serve:** nginx 1.27 serves only the built files, so Node is not in the final image.
- **`frontend/nginx.conf`:**
  - serves the React files, with unknown paths falling back to `index.html` so `/inventory` works on refresh;
  - forwards `/api/` to `http://api:8000`;
  - adds security headers, allows 6 MB uploads, and caches hashed assets for a year.
- **`docker-compose.yml`:**
  - three services, with health checks and start-up order;
  - the database address uses the service name `db`; Docker's internal network resolves it;
  - read-only mounts for data, models and results;
  - a named volume for the database files.
- **`.dockerignore`** keeps `.env`, `.venv`, data and notebooks out of the build, so secrets never end up in an image.
