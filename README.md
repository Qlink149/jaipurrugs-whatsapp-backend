# Jaipur Rugs Bot Backend

This repository contains the Python/FastAPI backend used for the Jaipur Rugs chatbot stack.

Important: production traffic for the Jaipur Rugs WhatsApp and dashboard APIs is handled by the WhatsApp backend deployment:

`https://jaipurrugs-whatsapp-backend.vercel.app`

Use the `whatsapp-integration-updates` branch for backend changes that should be reviewed before production merge.

## Production Architecture

```text
Web chatbot and dashboard
https://qlink-jr.vercel.app
        |
        | HTTP APIs
        v
WhatsApp backend
https://jaipurrugs-whatsapp-backend.vercel.app
        |
        | MongoDB, Pinecone, OpenAI, Jaipur Rugs product API, Gupshup
        v
Bot replies, products, alerts, agent handoff

WhatsApp customer
        |
        v
Gupshup webhook
        |
        v
https://jaipurrugs-whatsapp-backend.vercel.app/gupshup/message/hc
        |
        v
Same backend logic
```

The web chatbot realtime socket is the exception. It uses the VPS WebSocket backend:

`wss://api.vultr3.qlink.in/ws`

Vercel serverless functions are used for HTTP APIs, not long-running WebSocket connections.

## Repositories

| Repo | Purpose | Main working branch |
| --- | --- | --- |
| `JR_frontend` | Web chatbot and admin dashboard UI | `new-changes` |
| `jaipurrugs-whatsapp-backend` | Production WhatsApp/dashboard backend | `whatsapp-integration-updates` for review, then merge |
| `JR_bot_backend` | Local/backend working copy used during development | Keep aligned carefully with WhatsApp backend |

For production backend changes, push to `jaipurrugs-whatsapp-backend` on `whatsapp-integration-updates`. Do not push directly to production `main` unless explicitly approved.

## Main Backend Responsibilities

- Receive WhatsApp messages from Gupshup.
- Send WhatsApp replies through Gupshup.
- Run the OpenAI chatbot agent.
- Search products and format product replies.
- Read/write user sessions in MongoDB.
- Read system prompts from MongoDB.
- Search and update the Pinecone knowledge base.
- Expose dashboard APIs for conversations, leads, alerts, products, prompts, and WhatsApp send.
- Support human agent handoff/takeover.

## Important Routes

| Route | Purpose |
| --- | --- |
| `POST /gupshup/message/hc` | Gupshup WhatsApp webhook |
| `GET /api/conversations` | Dashboard WhatsApp conversation list |
| `GET /api/conversations/{phone}` | Dashboard message history for one WhatsApp number |
| `POST /api/whatsapp/send` | Send manual WhatsApp message from dashboard |
| `POST /api/conversations/{phone}/toggle-ai` | Toggle AI/human mode |
| `POST /api/conversations/{phone}/takeover` | Put conversation in agent mode and notify customer |
| `GET /api/alerts/all` | Agent alert list |
| `DELETE /api/alerts/{id}` | Clear alert |
| `GET /api/products` | Dashboard product list/search |
| `GET/POST /api/prompt` | Dashboard prompt read/write |
| `GET /api/cron/sync-products` | Product sync cron endpoint |

## Agent Takeover Flow

When a dashboard user clicks `Take over` in the WhatsApp chat:

1. Frontend calls `POST /api/conversations/{phone}/takeover`.
2. Backend sets `is_ai` to `False` for that WhatsApp session.
3. Backend appends a handoff message to chat history.
4. Backend sends the customer this WhatsApp message:

```text
Thank you. Our rug specialist will assist you further over a call/message.
```

After this, incoming WhatsApp messages are stored but AI does not reply while `is_ai` is false.

## Prompts And Knowledge

The bot behavior is not only controlled by code.

| Data | Location |
| --- | --- |
| System prompts | MongoDB `JR.internals`, document with `category: "system_prompt"` |
| User sessions | MongoDB `JR.users` and `JR.users_whatsapp` |
| Agent alerts | MongoDB `JR.agent_alerts` |
| KB records | Pinecone namespace configured by `PINECONE_NAMESPACE` |
| Product cache | MongoDB product collections populated from Jaipur Rugs API |

If prompt text changes but no code changes, update MongoDB through the dashboard prompt tools or a controlled script.

## Local Development

Create `.env` from `example.env` and fill required values. Never commit real secrets.

Install dependencies:

```bash
pip install -r requirements.txt
```

Run locally:

```bash
uvicorn qlink_chatbot.main:app --reload
```

Compile check:

```bash
python -m compileall qlink_chatbot
```

## Deployment Notes

Frontend production expects the backend at:

`https://jaipurrugs-whatsapp-backend.vercel.app`

After backend changes:

1. Push to `whatsapp-integration-updates`.
2. Open a PR/compare into the production branch.
3. Merge only after testing.
4. Confirm the deployed route is live with a safe endpoint check.

After frontend changes:

1. Push `JR_frontend/new-changes`.
2. Deploy the frontend Vercel project.
3. Confirm `https://qlink-jr.vercel.app` is ready.

## Safety Rules

- Do not commit `.env`.
- Do not paste or store production keys in README or code.
- Do not force-push production branches.
- Backend WhatsApp production changes should go through `whatsapp-integration-updates`.
- Keep frontend API config pointed at the production WhatsApp backend unless a migration is planned.
