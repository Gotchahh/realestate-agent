# 🏠 CasaAgent

> Assistente documentale AI per agenzie immobiliari italiane.
> Classifica documenti di una pratica di compravendita (visure, APE, planimetrie, documenti d'identità…), ne estrae i dati chiave, valida l'output e tiene traccia di completamento e scadenze.

---

## ✨ Cosa fa

- **Estrazione testo** da PDF digitali (pdfplumber) o scansionati (OCR Tesseract con lingua italiana).
- **Classificazione automatica** del tipo di documento via LLM (Groq · `llama-3.3-70b-versatile`) tra 10 categorie tipiche di una pratica immobiliare italiana.
- **Doppio strato di validazione** — Input Validator pre-LLM e Output Validator post-LLM — per bloccare spazzatura e allucinazioni.
- **Pratica come oggetto** — ogni documento viene associato a una pratica con checklist, percentuale di completamento, alert su documenti in scadenza (APE, carta d'identità, …).

---

## 🏗️ Architettura

```
┌──────────┐   ┌─────────────────┐   ┌─────────────┐   ┌──────────────────┐   ┌───────────────────┐
│  Upload  │ → │   Ingestion     │ → │  Input Val. │ → │   Classifier     │ → │  Output Val.       │
│   PDF    │   │ pdfplumber/OCR  │   │  (Layer 1)  │   │  Groq llama-3.3  │   │  (Layer 2)         │
└──────────┘   └─────────────────┘   └─────────────┘   └──────────────────┘   └────────┬──────────┘
                                                                                       │
                                                                                       ▼
                                                                              ┌──────────────────┐
                                                                              │ Practice Tracker │
                                                                              │  (Pydantic +     │
                                                                              │   session_state) │
                                                                              └──────────────────┘
```

| Modulo | Responsabilità |
|---|---|
| `agents/ingestion.py` | Estrazione testo PDF (digital + OCR fallback). |
| `validators/input_validator.py` | Layer 1: scarta input illeggibili / duplicati / fuori contesto **prima** di chiamare l'LLM. |
| `agents/classifier.py` | Classificazione e data extraction strutturata via Groq + LangChain. |
| `validators/output_validator.py` | Layer 2: controlla CF, classe APE, scadenze, coerenza fra documenti della stessa pratica. |
| `agents/practice_tracker.py` | Aggrega documenti in pratiche, calcola completamento, identifica scadenze. |
| `models/schemas.py` | Modelli Pydantic per `Visura`, `APE`, `DocumentoIdentita`, `Pratica`, … |
| `app.py` | UI Streamlit. |

---

## 🛠️ Stack tecnico

- **Python 3.11**
- **Streamlit** — UI
- **LangChain** + **Groq** (`llama-3.3-70b-versatile`) — classificazione e data extraction
- **pdfplumber** + **pytesseract** + **pdf2image** — ingestion
- **Pydantic v2** — data contracts e validazione strutturale
- **Docker** — containerizzazione (Tesseract + Poppler inclusi)

---

## 🚀 Setup locale

### 1. Prerequisiti di sistema

CasaAgent ha bisogno di **Tesseract** e **Poppler** installati a livello OS per l'OCR.

**Windows:**
```powershell
winget install --id=UB-Mannheim.TesseractOCR
winget install --id=oschwartz10612.Poppler
```

**macOS:**
```bash
brew install tesseract tesseract-lang poppler
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-ita poppler-utils
```

### 2. Clone e dipendenze Python

```bash
git clone https://github.com/Gotchahh/casa-agent.git
cd casa-agent
python -m venv venv
# Windows:  venv\Scripts\activate
# Unix:     source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurazione Groq API

Crea `.streamlit/secrets.toml`:
```toml
GROQ_API_KEY = "gsk_..."
```
Ottieni una chiave gratuita su [console.groq.com](https://console.groq.com).

### 4. Avvio

```bash
streamlit run app.py
```
L'app si apre su `http://localhost:8501`.

---

## 🐳 Docker

```bash
docker build -t casa-agent .
docker run -p 8501:8501 -e GROQ_API_KEY=gsk_... casa-agent
```

> Il `Dockerfile` include già Tesseract con lingua italiana e Poppler. La API key viene passata come variabile d'ambiente — `secrets.toml` **non** viene bake-ata nell'immagine.

---

## 🧠 Decisioni di design

**Perché due validation layer e non quattro?**
La letteratura sui sistemi LLM-driven spinge spesso verso 4 layer (input syntactic, input semantic, output syntactic, output semantic). Per questo dominio l'overhead non si giustifica: il 90% dei problemi reali è coperto da (a) qualità input + duplicati pre-LLM e (b) coerenza dati post-LLM. Layer extra avrebbero aggiunto codice senza aggiungere garanzie.

**Perché Groq + llama-3.3-70b?**
Inference latency molto bassa (~secondi per documento), tier gratuito generoso per un progetto portfolio, qualità sufficiente per estrazione strutturata da documenti italiani con prompt in italiano.

**Perché persistenza in-memory?**
Per un MVP da portfolio, focalizzare il valore tecnico sulla pipeline LLM e sui validator. SQLite è elencato in *Future work* — la migrazione è isolata al solo `PracticeTracker` grazie all'astrazione dei modelli Pydantic.

**Perché Pydantic come contract layer fra LLM e tracker?**
Il classifier produce JSON libero — i modelli `Visura`/`APE`/`DocumentoIdentita` impongono i constraint (16 caratteri per il CF, lista chiusa di classi energetiche, ecc.) prima che i dati entrino nella pratica. Se la validazione fallisce, l'app degrada in modo grazioso a `DocumentoBase` senza perdere il documento.

---

## ⚠️ Limiti noti

- **Persistenza in memoria** — le pratiche vivono nella sessione Streamlit, si perdono al riavvio.
- **Single-tenant** — nessun sistema di autenticazione / multi-utente.
- **OCR su scansioni di bassa qualità** — `tesseract` non riesce sempre a estrarre tabelle catastali complesse; il validator segnala correttamente la bassa confidence ma il dato resta da rivedere a mano.
- **Lingua** — prompt e parole chiave sono ottimizzati per documenti italiani.

## 🗺️ Roadmap

- [ ] Persistenza SQLite con repository pattern
- [ ] Autenticazione multi-utente / multi-agenzia
- [ ] Export PDF del report di pratica
- [ ] Allarme email/Slack per scadenze imminenti
- [ ] Confronto cross-documento più aggressivo (es. matching CF venditore ↔ visura ↔ atto)

---

## 👤 Autore

**Alberto D'Odorico** — studente ITS AI Developing, lavoro presso [Brainyware](https://brainyware.ai).
GitHub: [@Gotchahh](https://github.com/Gotchahh)

### Altri progetti portfolio

- [`chatbot-rag`](https://github.com/Gotchahh/chatbot-rag) — chatbot RAG su PDF (Streamlit + LangChain + ChromaDB + Groq)
- [`research-agent`](https://github.com/Gotchahh/research-agent) — sistema multi-agente con orchestratore (Planner/Researcher/Analyst/Writer)
- [`fuel-finder`](https://github.com/Gotchahh/fuel-finder) — analizzatore prezzi benzina con mappa interattiva
