# 🏥 ClearCare — AI Medicare Cost Navigator

> Know what you'll pay. Before you go.

ClearCare is a multimodal AI agent that takes your insurance plan 
and care needs — via text, voice, or image — finds nearby in-network 
vs out-of-network hospitals, and estimates your real out-of-pocket cost.

## Tech Stack
- **Frontend:** Next.js 14 + Tailwind CSS → Vercel
- **Backend:** FastAPI + LangGraph → Railway
- **AI:** GPT-4o + Whisper + ElevenLabs
- **Search:** Tavily (live web)
- **Data:** CMS Medicare API + NPI Registry
- **Evals:** Braintrust
- **DB:** Supabase

## Local Development

### Backend
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn main:app --reload

### Frontend
cd frontend
npm install
npm run dev

## Environment Variables
Copy `.env.example` to `backend/.env` and fill in your keys.