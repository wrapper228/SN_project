# Deployment

## Cloud Backend

Deploy the FastAPI backend on any small VM or platform service that can expose HTTP.

Command:

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## Telegram Frontend

Run separately with:

- `TELEGRAM_BOT_TOKEN`
- `BACKEND_URL`

Command:

```bash
python -m bot.app
```

## Local Windows Client

Run on the user's PC with:

- `BACKEND_URL`
- `CLIENT_ID`
- `ANTHROPIC_API_KEY`

Command:

```bash
python -m client.watchdog
```
