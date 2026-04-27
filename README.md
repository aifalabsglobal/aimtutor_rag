<div align="center">

<img src="assets/aimtutor-logo.png" alt="AimTutor" width="180" style="border-radius: 18px;">

# AimTutor

**An agent-native AI tutor with first-class auth and visual web search.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![Clerk](https://img.shields.io/badge/Auth-Clerk-6C47FF?style=flat-square&logo=clerk&logoColor=white)](https://clerk.com/)
[![SerpAPI](https://img.shields.io/badge/Images-SerpAPI-4A90E2?style=flat-square&logo=google&logoColor=white)](https://serpapi.com/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square)](LICENSE)

</div>

---

AimTutor is a downstream of [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) — the agent-native learning companion built on a two-layer plugin model (Tools + Capabilities) — with two production-oriented additions:

1. **Clerk authentication** baked into the Next.js frontend (route protection, sign-in/sign-up, sidebar account UI), gated on env vars so OSS / local dev still works without keys.
2. **SerpAPI image enrichment** wired into the chat `web_search` tool, surfacing a thumbnail gallery inline in the conversation regardless of which text-search provider is active.

Everything else from upstream DeepTutor — Chat, Deep Solve, Quiz, Deep Research, Math Animator, Visualize, Co-Writer, Book Engine, Knowledge Hub, Memory, TutorBot, the CLI — works unchanged. See [DEEPTUTOR_README.md](#-credits--upstream) for the full feature tour.

## ✨ What's new in AimTutor

| Feature | What it does | Where it lives |
|---|---|---|
| **Optional Clerk auth** | Protects every route with [Clerk](https://clerk.com/), shows a sign-in/account widget in the sidebar, with sign-in/sign-up pages. Disables itself cleanly when keys are not set. | `web/middleware.ts`, `web/lib/clerk-config.ts`, `web/components/auth/SidebarAuth.tsx`, `web/app/sign-{in,up}/[[...slug]]/page.tsx` |
| **SerpAPI image search** | Adds a `serpapi` provider (Google + Google Images), plus an `include_images` flag on `web_search` that fetches a thumbnail gallery via SerpAPI alongside any text provider. The chat agent enables it automatically. | `deeptutor/services/search/providers/serpapi.py`, `deeptutor/services/search/__init__.py`, `deeptutor/agents/chat/agentic_pipeline.py`, `web/components/chat/home/TracePanels.tsx` |

## 🚀 Quick start

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend (skip if CLI-only) |
| Git | any | For cloning |

You'll also need an LLM API key (OpenAI / DeepSeek / Anthropic / etc.). Optionally a [SerpAPI key](https://serpapi.com/manage-api-key) for image search and a [Clerk app](https://dashboard.clerk.com/) for auth.

### 1. Clone & install

```bash
git clone https://github.com/<your-org>/aimtutor.git
cd aimtutor

# Backend (creates a venv and installs DeepTutor + web server deps)
python -m venv .venv
.venv\Scripts\activate                  # Windows
# source .venv/bin/activate             # macOS/Linux
pip install -e ".[server]"

# Frontend
cd web && npm install && cd ..
```

### 2. Configure `.env`

```bash
cp .env.example .env
```

Fill in the required fields:

```dotenv
# ── LLM (required) ──────────────────────────────
LLM_BINDING=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...
LLM_HOST=https://api.openai.com/v1

# ── Embeddings (required for Knowledge Base) ────
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_API_KEY=sk-...
EMBEDDING_HOST=https://api.openai.com/v1
EMBEDDING_DIMENSION=3072

# ── SerpAPI image enrichment (optional) ─────────
# When set, chat web_search additionally fetches Google Images thumbnails
# and renders them inline. Works with any SEARCH_PROVIDER.
# `SERP_API_KEY` is also accepted as an alias.
SERPAPI_API_KEY=

# ── Clerk auth (optional) ───────────────────────
# When BOTH are set, Next.js protects routes and shows sign-in.
# Configure the same pair in web/.env.local for local frontend dev.
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
```

### 3. Run

```bash
python scripts/start_web.py
```

Both the backend (`:8001`) and the Next.js frontend (`:3782`) start together. Open http://localhost:3782.

Or run them separately:

```bash
# Terminal 1 — backend
python -m deeptutor.api.run_server

# Terminal 2 — frontend
cd web && npm run dev -- -p 3782
```

## 🔐 Authentication (Clerk)

Auth is **opt-in**. With `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` set:

- Every non-public route is wrapped in [`clerkMiddleware`](web/middleware.ts) and redirects unauthenticated users to `/sign-in`.
- The sidebar shows a `<SignInButton>` (logged out) or `<UserButton>` (logged in) — both responsive to the collapsed/expanded sidebar state.
- `/sign-in/[[...sign-in]]` and `/sign-up/[[...sign-up]]` host Clerk's hosted components.

With the keys unset:

- Middleware passes every request through.
- The `SidebarAuth` component returns `null`, so no Clerk hooks run outside of `<ClerkProvider>` (no build / hydration errors).

This means a single codebase ships both as a public-facing SaaS and as a local OSS tool.

## 🖼️ SerpAPI image enrichment

Whenever the chat agent uses `web_search`, AimTutor calls SerpAPI's `engine=google_images` endpoint in parallel and returns the top thumbnails as part of the tool result. The frontend renders them as a hover-zoom grid directly under the trace, with click-through to the source page.

You can also use `serpapi` as your **primary** search provider:

```dotenv
SEARCH_PROVIDER=serpapi
SERPAPI_API_KEY=your-key
```

The provider supports both `engine=google` (default) and `engine=google_images` modes and slots into the standard `WebSearchResponse` shape.

Programmatic use:

```python
from deeptutor.services.search import web_search

result = web_search("photosynthesis", include_images=True, image_limit=6)
print(result["answer"])           # markdown answer + appended ## Images section
print(result["images"])           # [{thumbnail, original, title, link, source}, ...]
```

## 🛠️ Development

```bash
# Backend
pip install -e ".[dev]"
pytest

# Frontend
cd web
npm run dev          # local dev with hot reload
npm run lint         # eslint
npx tsc --noEmit     # type check
npm run build        # production build
```

The repo follows [Conventional Commits](https://www.conventionalcommits.org/). Branching, coding standards, and PR flow are documented in [CONTRIBUTING.md](CONTRIBUTING.md).

## 📂 Project layout

```text
aimtutor/
├── deeptutor/                       # Python package (agent-native core)
│   ├── agents/chat/agentic_pipeline.py   # chat orchestration (auto-enables image search)
│   ├── capabilities/                # built-in capabilities (chat, deep_solve, ...)
│   ├── services/search/             # web search providers (incl. serpapi)
│   ├── tools/                       # built-in tools (web_search, rag, code_exec, ...)
│   └── runtime/                     # registries & orchestrator
├── deeptutor_cli/                   # Typer CLI entry point
├── web/                             # Next.js 16 frontend
│   ├── app/                         # routes (incl. sign-in / sign-up)
│   ├── components/auth/             # SidebarAuth (Clerk integration)
│   ├── components/chat/home/        # TracePanels with image gallery
│   ├── lib/clerk-config.ts          # auth feature flag
│   └── middleware.ts                # Clerk route protection (opt-in)
├── scripts/start_web.py             # one-command launcher
├── .env.example                     # documented env template
└── README.md                        # this file
```

## 🌐 Deployment

The upstream Docker compose flows still work:

```bash
docker compose up -d                         # build from source
docker compose -f docker-compose.ghcr.yml up # pre-built GHCR image
```

For cloud deploys, set `NEXT_PUBLIC_API_BASE_EXTERNAL` to the public backend URL. Add the Clerk env vars to the build environment of the Next.js container so the middleware activates.

See the full upstream guide for data persistence, custom ports, and dev-mode hot-reload: [HKUDS/DeepTutor → Docker Deployment](https://github.com/HKUDS/DeepTutor#option-c--docker-deployment).

## 🙌 Credits & upstream

AimTutor is built on [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) and inherits its agent-native architecture, capabilities, tools, CLI, and TutorBot system. All upstream features are documented in the project's authoritative README — pull from upstream periodically to stay current:

```bash
git remote add upstream https://github.com/HKUDS/DeepTutor.git
git fetch upstream
git merge upstream/main
```

Notable upstream credits, preserved here:

| Project | Role |
|---|---|
| [nanobot](https://github.com/HKUDS/nanobot) | Powers TutorBot |
| [LlamaIndex](https://github.com/run-llama/llama_index) | RAG pipeline |
| [ManimCat](https://github.com/Wing900/ManimCat) | Math Animator |
| [Clerk](https://clerk.com/) | Authentication SaaS |
| [SerpAPI](https://serpapi.com/) | Google search & images |

## 📄 License

Apache License 2.0 — see [LICENSE](LICENSE).
