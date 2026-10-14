# Free online deployment (Render + Neon)

The whole product runs as one Docker web service (API + interface) and one PostgreSQL database.
Both have free plans that do not need a payment card at the time of writing (October 2026):

| Piece | Service | Free plan limits that matter |
|---|---|---|
| Web service | [Render](https://render.com/docs/free), Docker runtime | 512 MB RAM, 0.1 CPU, sleeps after 15 min without traffic (about 1 min to wake up), 750 instance hours per month, 5 GB outbound transfer |
| Database | [Neon](https://neon.com/pricing) | 1 GB storage per project, 100 compute-hours per month, suspends after 5 min idle; data is never deleted for inactivity |

Render's own free PostgreSQL expires after 30 days, which would end before judging, so the
database is on Neon. Both are placed in Frankfurt, the closest region to Cameroon offered by both.

Measured on the application: about 175 MB of memory once started; analysis and simulation
answer in well under a second on one core, the sensitivity grid in about one second (expect a
few seconds on Render's 0.1 CPU).

Render does **not** read the `.env.example` files of the repository: they are for running the
project on your own computer (`.env.example` at the root for Docker, `backend/.env.example` for
the backend without Docker). Online, every variable is entered in Render's Environment page.

## 1. Database (Neon)

1. Sign up at <https://neon.com> (GitHub sign-in works) and create a project: name `salva`,
   PostgreSQL 16 or later, region **AWS Europe Central 1 (Frankfurt)**.
2. On the project dashboard, open **Connect**, choose the default branch and database
   (`neondb`), and **turn connection pooling off** (direct connection).
3. Copy the connection string. It looks like
   `postgresql://neondb_owner:<password>@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`.
   Keep it private: it contains the database password.

The application accepts this string as is (it adds the `psycopg` driver itself). Tables are
created by the migrations at the first start.

## 2. Web service (Render)

1. Sign up at <https://render.com> with the GitHub account that can read
   `SupraCodex/SALVA`, and allow Render to access the repository.
2. **New > Web Service**, pick the repository, then:
   - Branch: `main`; Runtime/Language: **Docker** (the root `Dockerfile` is detected);
   - Region: **Frankfurt**; Instance type: **Free**;
   - Advanced > Health Check Path: `/api/v1/health/live`.
3. Environment variables (Advanced > Add Environment Variable):

   | Key | Value |
   |---|---|
   | `ENV` | `production` |
   | `DATABASE_URL` | the Neon connection string |
   | `JWT_SECRET` | click **Generate** (or `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
   | `ALLOWED_ORIGINS` | `https://<service-name>.onrender.com` (the URL Render shows; can be added after the first deploy) |
   | `WEATHER_ENABLED` | `true` |
   | `LLM_PROVIDER` | `template` (or `gemini` with `LLM_API_KEY`, optional) |
   | `SEED_DEMO` | `true` |
   | `DEMO_USER_EMAIL` | `demo@salva.example` |
   | `DEMO_USER_PASSWORD` | a password of your choice, at least 10 characters |

   Do not set `PORT` (Render provides it) nor `COOKIE_SECURE` (production cookies are secure,
   and Render serves HTTPS).
4. **Create Web Service**. The first build takes several minutes (frontend build, then Python
   packages). At start-up the container applies migrations, loads the reference markets and
   places, creates the demo workspace, then serves the site.
5. When the log shows `Uvicorn running`, open `https://<service-name>.onrender.com`.

Alternative: **New > Blueprint** with the repository uses `render.yaml` (same settings; Render
asks for `DATABASE_URL`, `ALLOWED_ORIGINS` and `DEMO_USER_PASSWORD`).

Every push to `main` redeploys automatically (Settings > Build & Deploy > Auto-Deploy; choose
"After CI checks pass" so a red build is never deployed).

## 3. Check the deployment

1. `https://<service-name>.onrender.com/api/v1/health` returns `"status":"ok"` and
   `"database":"up"`.
2. Sign in with the demo account, open the demo lot, run the analysis in replay mode at
   3 October 2026 09:00, simulate, open the recommendation and ask an example question.
3. Create an account from the sign-in page and create a lot with "Prefill the example lot":
   the automatic weather line should say the temperature comes from the weather service.
4. Open the site on a phone.

## 4. Keep it awake during judging (optional)

A sleeping free service needs about a minute to answer. To avoid that, add a free monitor that
calls the liveness URL every 5 to 10 minutes, for example
[UptimeRobot](https://uptimerobot.com) (HTTP(s) monitor, 5-minute interval) or
[cron-job.org](https://cron-job.org):

`https://<service-name>.onrender.com/api/v1/health/live`

This path does not touch the database, so Neon still suspends when nobody uses the site and its
free compute-hours last the month. One always-on service uses at most 744 of the 750 free hours.
Run `./scripts/warmup.sh https://<service-name>.onrender.com` a few minutes before a live demo.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The page "Service waking up" comes back for minutes, the service restarts again and again | the container stops at start-up, almost always because environment variables are missing (a service that was deleted and created again starts with none). Open **Logs**: a line `PREFLIGHT ERROR: ...` names the problem. Enter every variable of step 2.3 again (same Neon `DATABASE_URL`, `ALLOWED_ORIGINS` with the new URL), set the Health Check Path, then **Manual Deploy > Deploy latest commit** |
| `PREFLIGHT ERROR: DATABASE_URL is not set` | `DATABASE_URL` is missing; paste the Neon connection string |
| `PREFLIGHT ERROR: cannot connect to the database` | the Neon string is wrong or incomplete (copy it again, pooling off), or the Neon project was deleted |
| Deploy fails with `JWT_SECRET must be set...` | `ENV=production` without a 32+ character `JWT_SECRET` |
| `/api/v1/health` returns 503 `database: down` | wrong `DATABASE_URL`, or the Neon project was deleted; copy the string again |
| Signed out after every page reload | the site is opened over plain HTTP or another domain; use the `https://...onrender.com` URL |
| First request takes about a minute | the free service was asleep; see section 4 |
| Weather always "did not answer" | `WEATHER_ENABLED` is not `true`, or Open-Meteo is unreachable; a labelled default temperature is used |
