# ClearCare

**AI-powered healthcare cost estimator** — enter your symptoms and insurance plan, and ClearCare finds nearby providers, checks your network status, and calculates your real out-of-pocket cost before you ever step foot in a clinic.

---

## What it does

1. **Describes symptoms** — via text, voice recording, or insurance card upload
2. **Finds nearby providers** — searches the CMS NPI Registry using your zip code
3. **Checks network status** — determines in-network vs out-of-network for your plan
4. **Calculates out-of-pocket cost** — applies your actual deductible, copay, and coinsurance
5. **Generates an AI summary** — plain-English explanation with a specific recommended next step
6. **Speaks the summary aloud** — ElevenLabs TTS for hands-free use

---

## Tech stack

### Backend (Python / FastAPI)
| Component | Purpose |
|---|---|
| FastAPI | REST API server |
| LangGraph | Multi-step AI agent pipeline |
| GPT-4o | Symptom mapping, cost estimation, answer generation |
| LangChain | LLM orchestration |
| Tavily | Live web search for insurance network lookup |
| OpenAI Whisper | Voice transcription |
| ElevenLabs | Text-to-speech for AI summaries |
| Supabase | Session storage and analytics logging |
| CMS NPI Registry | Provider search by zip code (public API) |

### Frontend (Next.js / React)
| Component | Purpose |
|---|---|
| Next.js 14 | React framework |
| TypeScript | Type safety |
| Google Maps API | Provider location map |

### Infrastructure
| Service | Role |
|---|---|
| Railway | Backend hosting |
| Vercel | Frontend hosting |
| Supabase | PostgreSQL database |

---

## Project structure

```
clearcare/
├── backend/
│   ├── main.py                  # FastAPI app, CORS, startup
│   ├── config.py                # Central config — all env vars loaded here
│   ├── railway.json             # Railway deployment config
│   ├── requirements.txt
│   ├── agent/
│   │   ├── graph.py             # LangGraph pipeline (main agent)
│   │   ├── critique.py          # Self-critique and rewrite loop
│   │   ├── tools.py             # LangChain tools (cost, network, search)
│   │   ├── prompts.py           # LLM prompt templates
│   │   ├── analytics.py         # Supabase logging with retry logic
│   │   └── memory.py            # Session/context memory
│   └── routes/
│       ├── estimate.py          # POST /api/estimate/ — main agent route
│       ├── voice.py             # POST /api/voice/transcribe, /speak
│       └── image.py             # POST /api/image/extract — insurance card OCR
│
└── frontend/
    └── app/
        ├── page.tsx             # Main page — layout and state
        ├── globals.css          # All styles
        └── components/
            ├── InputPanel.tsx       # Symptom + insurance text input
            ├── VoiceInput.tsx       # Microphone recording
            ├── InsuranceUpload.tsx  # Insurance card image upload + OCR
            ├── ResultsPanel.tsx     # Cost breakdown and confidence score
            ├── InsuranceSavings.tsx # Insurance savings card
            ├── AIAnalysis.tsx       # AI summary and recommended next step
            ├── HospitalCards.tsx    # Nearby provider cards
            ├── HospitalMap.tsx      # Google Maps provider map
            ├── Header.tsx
            └── Footer.tsx
```

---

## Agent pipeline

The backend runs a **LangGraph multi-step agent** for each request:

```
map_symptoms → assess_severity → find_hospitals → check_network
     → estimate_cost → find_alternatives → generate_answer → critique
```

| Node | What it does |
|---|---|
| `map_symptoms` | Extracts structured care type and plan details from free-text |
| `assess_severity` | Rates urgency (routine / moderate / urgent) |
| `find_hospitals` | Queries NPI Registry with tiered zip code matching |
| `check_network` | Web-searches Tavily to determine in/out-of-network |
| `estimate_cost` | Calculates patient cost using real deductible/copay/coinsurance |
| `find_alternatives` | Finds lower-cost care options in the area |
| `generate_answer` | Builds structured JSON response with summary and next step |
| `critique` | Self-scores the answer and rewrites up to 3× if score < 80 |

---

## Local setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- A Supabase project
- API keys (see below)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

Start the server:

```bash
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_key_here
```

Start the dev server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Environment variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Standard `sk-` key from platform.openai.com |
| `ELEVENLABS_API_KEY` | Yes | Text-to-speech for AI summary audio |
| `ELEVENLABS_VOICE_ID` | No | Defaults to Rachel (`21m00Tcm4TlvDq8ikWAM`) |
| `TAVILY_API_KEY` | Yes | Web search for insurance network lookup |
| `SUPABASE_URL` | Yes | Your Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase service role key |
| `AIRIA_API_KEY` | No | Leave empty — only set if routing through Airia gateway |
| `ENVIRONMENT` | No | `development` or `production` |
| `FRONTEND_URL` | No | CORS origin (e.g. `https://your-app.vercel.app`) |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes | Backend URL (no trailing slash) |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | Yes | Google Maps JavaScript API key |

> **Note:** Use a standard `sk-` OpenAI key in production. Project-scoped `sk-proj-` keys can have IP restrictions that block cloud hosting providers like Railway.

---

## Deployment

### Backend → Railway

1. Connect your GitHub repo to Railway
2. Set root directory to `backend/`
3. Add all backend environment variables in Railway → Variables
4. Railway uses `railway.json` to build and start with `uvicorn`

### Frontend → Vercel

1. Connect your GitHub repo to Vercel
2. Set root directory to `frontend/`
3. Add `NEXT_PUBLIC_API_URL` pointing to your Railway backend URL (no trailing slash)
4. Add `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`

---

## Analytics

Every query is logged to Supabase (`clearcare_queries` table) with:
- Session ID, symptoms, zip code, insurance plan
- Hospitals found, confidence score (before and after self-critique)
- Urgency level, whether defaults were used
- Timestamp

This data is modelled and visualised in **Lightdash**.

---

## Lightdash dashboard

The `lightdash-supabase-quickstart/` folder contains the full analytics stack as code — models, charts, and a dashboard — all connected to the Supabase database.

### Dashboard — ClearCare (`lightdash/dashboards/clearcare.yml`)

| Row | Charts |
|---|---|
| KPIs | Total Queries · Unique Sessions · Avg Confidence Score |
| Volume | Queries Per Day (line) · Queries by Urgency Level (bar) |
| Quality | Avg Final Score Over Time · Avg Confidence vs Final Score |
| Usage | Top Care Types Requested |

### Models

**`clearcare_queries`** — one row per user query

| Field | Description |
|---|---|
| `session_id` | Links to the session that made the query |
| `symptoms` | Raw symptom text entered by the user |
| `care_needed` | Procedure the agent identified (e.g. X-ray, urgent care visit) |
| `zip_code` | User zip code for provider search |
| `insurance` | Insurance plan name |
| `hospitals_found` | Number of providers returned |
| `confidence` | Signal confidence score before self-critique (0–100) |
| `final_score` | Score after self-critique rewrite loop (0–100) |
| `urgency` | Urgency level: low / medium / high / emergency |
| `used_defaults` | True if agent fell back to generic plan values |

**`sessions`** — one row per user session (linked to queries)

### Running Lightdash locally

```bash
cd lightdash-supabase-quickstart
```

Set your Supabase credentials in the warehouse config, then deploy:

```bash
lightdash deploy --project <your-project-uuid>
```

Or push charts and dashboards with:

```bash
lightdash upload --force
```
