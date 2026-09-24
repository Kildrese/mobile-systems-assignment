## REMOVED Requirements

### Requirement: Next.js TypeScript application runs locally with npm
**Reason**: The single Next.js app is split into a FastAPI backend and a Vite SPA on separate origins.
**Migration**: See `backend-service` ("FastAPI service runs locally with uv") and `frontend-app` ("Vite single-page app runs locally with npm").

### Requirement: Application connects to the database via DATABASE_URL
**Reason**: Only the backend talks to the database now, through SQLAlchemy instead of Drizzle.
**Migration**: See `backend-service` ("Configuration from environment variables" and "Database connection").
