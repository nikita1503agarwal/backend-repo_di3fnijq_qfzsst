import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from database import db, create_document, get_documents
from schemas import Regulationdoc, Flashcard, Inspiration
import requests

# Optional: PDF parsing
from io import BytesIO
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except Exception:
    pdf_extract_text = None

app = FastAPI(title="STEM Racing Regulations Learning API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------- Models -----------------------------
class AddRegulationRequest(BaseModel):
    title: str
    source_url: str

class GenerateFlashcardsRequest(BaseModel):
    doc_id: Optional[str] = None
    text: Optional[str] = None
    count: int = Field(5, ge=1, le=20)
    tag: Optional[str] = None

class ExplainRequest(BaseModel):
    text: str

class InspirationQuery(BaseModel):
    query: str


# ----------------------------- Utilities -----------------------------
AERO_KEYWORDS = [
    "downforce", "drag", "lift", "ground effect", "diffuser", "wing",
    "endplate", "vortex", "boundary layer", "laminar", "turbulent",
    "ride height", "floor", "beam wing", "front wing", "rear wing",
    "DRS", "cooling", "radiator", "airbox", "splitter", "gurney flap",
]

REG_KEYWORDS = [
    "must", "shall", "should", "may", "not", "minimum", "maximum",
    "tolerances", "dimensions", "weight", "width", "height", "length",
    "clearance", "radius", "material", "fastener", "safety", "inspection"
]

def simple_explain(text: str) -> dict:
    t = text.strip()
    bullets: List[str] = []
    lower = t.lower()
    # Identify constraints
    for kw in ["minimum", "maximum", "must", "shall", "not", "prohibited", "required"]:
        if kw in lower:
            bullets.append(f"Identifies a compliance rule: contains the word '{kw}'.")
            break
    # Extract numbers and units
    import re
    numbers = re.findall(r"[0-9]+(?:\.[0-9]+)?\s?(mm|cm|m|kg|deg|°|%|in|inch|nm|n|lbs)?", t, flags=re.IGNORECASE)
    if numbers:
        bullets.append("Specifies quantitative limits or measurements.")
    # Find common regulation keywords
    present = [kw for kw in REG_KEYWORDS if kw in lower][:6]
    if present:
        bullets.append("Key terms: " + ", ".join(present))
    # Compliance tip
    bullets.append("Tip: Convert units to a single system and create a checklist to verify each constraint before scrutineering.")
    return {
        "summary": t[:300] + ("..." if len(t) > 300 else ""),
        "bullets": bullets
    }


def generate_flashcards_from_text(text: str, n: int, tag: Optional[str]) -> List[dict]:
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s for s in sentences if len(s) > 20][:200]
    cards = []
    i = 0
    for s in sentences:
        if i >= n:
            break
        # Create simple Q/A by turning a statement into a question
        q = s
        q = re.sub(r"(must|shall|should)\b", r"What \1", q, flags=re.IGNORECASE)
        if q == s:
            q = "What does this regulation state? " + s[:120]
        a = s
        cards.append({"question": q, "answer": a, "tag": tag})
        i += 1
    return cards


def fetch_pdf_text(url: str) -> str:
    if not pdf_extract_text:
        raise HTTPException(status_code=500, detail="PDF extraction library not available")
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        with BytesIO(r.content) as bio:
            text = pdf_extract_text(bio) or ""
        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
        return text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch/parse PDF: {str(e)[:200]}")


def wiki_search_extract(query: str) -> dict:
    # Use Wikipedia API (no key required)
    try:
        sr = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1,
            },
            timeout=15,
        ).json()
        if not sr.get("query", {}).get("search"):
            return {"title": query, "extract": "No results found."}
        page_title = sr["query"]["search"][0]["title"]
        summary = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/" + page_title,
            timeout=15,
        ).json()
        return {"title": summary.get("title", page_title), "extract": summary.get("extract", "")}
    except Exception:
        return {"title": query, "extract": "Lookup failed."}


def analyze_aero(text: str) -> List[str]:
    lower = text.lower()
    highlights = []
    if any(k in lower for k in ["ground effect", "venturi", "floor"]):
        highlights.append("Uses ground-effect via the floor/venturi to create strong underbody downforce.")
    if any(k in lower for k in ["wing", "rear wing", "front wing", "gurney"]):
        highlights.append("Optimized wing package; look for gurney flaps and efficient endplates to manage vortices.")
    if any(k in lower for k in ["drag", "slippery", "cd "]):
        highlights.append("Low drag philosophy visible in bodywork packaging and cooling exits.")
    if any(k in lower for k in ["diffuser", "beam wing"]):
        highlights.append("Powerful diffuser/beam-wing interaction stabilizes the rear at speed.")
    if not highlights:
        highlights.append("General balance of downforce and drag; packaging and ride height control are key.")
    return highlights


# ----------------------------- Routes -----------------------------
@app.get("/")
def read_root():
    return {"message": "STEM Racing Regulations API running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    status = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            status["database"] = "✅ Connected & Working"
            status["connection_status"] = "Connected"
            try:
                status["collections"] = db.list_collection_names()[:10]
            except Exception:
                pass
    except Exception as e:
        status["database"] = f"❌ Error: {str(e)[:80]}"
    return status


# Regulations CRUD
@app.post("/api/regulations", response_model=dict)
def add_regulation(req: AddRegulationRequest):
    text = fetch_pdf_text(req.source_url)
    doc = Regulationdoc(title=req.title, source_url=req.source_url, text=text)
    _id = create_document("regulationdoc", doc)
    return {"id": _id, "title": req.title}

@app.get("/api/regulations", response_model=List[dict])
def list_regulations(limit: int = 20):
    docs = get_documents("regulationdoc", {}, limit)
    out = []
    for d in docs:
        out.append({
            "id": str(d.get("_id")),
            "title": d.get("title"),
            "source_url": d.get("source_url"),
            "snippet": (d.get("text", "")[:200] + "...") if d.get("text") else ""
        })
    return out

@app.get("/api/regulations/{doc_id}", response_model=dict)
def get_regulation(doc_id: str):
    try:
        # Avoid importing bson module from external package; use string id only
        d = db["regulationdoc"].find_one({"_id": doc_id}) if db is not None else None
        if not d:
            raise HTTPException(status_code=404, detail="Document not found")
        return {
            "id": str(d.get("_id")),
            "title": d.get("title"),
            "source_url": d.get("source_url"),
            "text": d.get("text", "")
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


# Explain selected text
@app.post("/api/explain", response_model=dict)
def explain_text(req: ExplainRequest):
    return simple_explain(req.text)


# Flashcards
@app.post("/api/flashcards/generate", response_model=List[dict])
def generate_flashcards(req: GenerateFlashcardsRequest):
    base_text = req.text
    if not base_text and req.doc_id:
        try:
            d = db["regulationdoc"].find_one({"_id": req.doc_id}) if db is not None else None
            if not d:
                raise HTTPException(status_code=404, detail="Document not found")
            base_text = d.get("text", "")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid id")
    if not base_text:
        raise HTTPException(status_code=400, detail="Provide text or doc_id")

    cards = generate_flashcards_from_text(base_text, req.count, req.tag)
    # persist
    ids = []
    out = []
    for c in cards:
        fc = Flashcard(doc_id=req.doc_id, question=c["question"], answer=c["answer"], tag=c.get("tag"))
        cid = create_document("flashcard", fc)
        ids.append(cid)
        c.update({"id": cid})
        out.append(c)
    return out

@app.get("/api/flashcards", response_model=List[dict])
def list_flashcards(limit: int = 50, tag: Optional[str] = None):
    filt: dict[str, Any] = {}
    if tag:
        filt["tag"] = tag
    docs = get_documents("flashcard", filt, limit)
    res = []
    for d in docs:
        res.append({
            "id": str(d.get("_id")),
            "question": d.get("question"),
            "answer": d.get("answer"),
            "tag": d.get("tag")
        })
    return res


# Inspiration
@app.post("/api/inspiration", response_model=dict)
def inspiration_lookup(req: InspirationQuery):
    wiki = wiki_search_extract(req.query)
    highlights = analyze_aero(wiki.get("extract", ""))
    insp = Inspiration(query=req.query, car=wiki.get("title", req.query), summary=wiki.get("extract", ""), aero_highlights=highlights)
    _id = create_document("inspiration", insp)
    return {
        "id": _id,
        "car": insp.car,
        "summary": insp.summary,
        "aero_highlights": insp.aero_highlights
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
