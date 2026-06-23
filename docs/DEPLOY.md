# Deployment

## Backend (Render)

[`render.yaml`](render.yaml) defines a Python web service. Steps:

1. Connect the GitHub repository in Render.
2. Create a Blueprint from `render.yaml`.
3. Set secrets in the dashboard: `EIA_API_KEY`, `CORS_ALLOW_ORIGINS` (your frontend URL), optional `GEMINI_API_KEY`.
4. Confirm health at `https://<service>/ping`.

SQLite on Render is ephemeral on the free tier. For production, configure Snowflake or an external database.

## Frontend (Vercel)

1. Import the repository in Vercel; set root directory to `frontend`.
2. Set `BACKEND_URL` to the Render service URL.
3. Deploy. The Next.js rewrite proxies `/api/*` to the backend.

## Remote MCP (SSE)

For agent clients that cannot spawn a local subprocess:

```bash
cd backend
python mcp_server.py --transport sse --host 0.0.0.0 --port 8765
```

Point MCP clients at `http://<host>:8765/sse` (client-specific configuration).

For local development, keep the default stdio transport:

```bash
python mcp_server.py
```

## Post-deploy checks

```bash
curl -s https://<backend>/api/diagnostics | python3 -m json.tool
curl -s "https://<backend>/api/check_grid?region=CISO"
```
