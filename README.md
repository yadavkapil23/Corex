# Corex

A retrieval-augmented generation (RAG) assistant built with FastAPI and LangChain. Answers are grounded in your documents first, with Wikipedia and general LLM knowledge as fallbacks when retrieval finds nothing relevant.

## Features

- **Retrieval-first RAG** — every query searches a FAISS vector store before falling back to Wikipedia or a raw LLM answer, with citations (source file + page number) returned alongside each response.
- **Document upload ("My Document" mode)** — upload a PDF, TXT, or image (PNG/JPG) and ask questions scoped to just that file.
- **OCR** — image uploads (and one-shot image attachments in general chat) are read via a hosted vision model; extracted text is chunked, embedded, and made queryable like any other document.
- **Voice input** — a mic button transcribes speech to text using the browser's native Speech Recognition API (no backend involved).
- **Read-aloud** — assistant responses can be read back using the browser's native Speech Synthesis API.
- **Installable as a PWA** — includes a web manifest and service worker so the app can be added to a phone or desktop home screen.
- **NVIDIA-hosted inference** — chat generation and vision/OCR both run through NVIDIA's NIM API; only the embeddings model runs locally, so no GPU is required.

## Architecture

| Layer | Technology |
|---|---|
| API | FastAPI ([main.py](main.py), [endpoints.py](endpoints.py)) |
| Retrieval | FAISS + `all-MiniLM-L6-v2` embeddings (local, CPU) |
| Generation | NVIDIA NIM API (default: `openai/gpt-oss-20b`) |
| Vision / OCR | NVIDIA NIM API (default: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`) |
| Frontend | Vanilla HTML/CSS/JS ([templates/](templates/), [static/](static/)) |

## Setup

### Prerequisites

- Python 3.10+
- An NVIDIA API key — free at [build.nvidia.com](https://build.nvidia.com)

### Install and run

```bash
git clone https://github.com/yadavkapil23/RAG_Project.git
cd RAG_Project

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
NVIDIA_API_KEY=your-key-here
NVIDIA_MODEL=openai/gpt-oss-20b
NVIDIA_VISION_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
```

`NVIDIA_MODEL`/`NVIDIA_VISION_MODEL` can be swapped for any model on build.nvidia.com's catalog that has a "Free Endpoint" badge.

Run the server:

```bash
uvicorn main:app --reload
```

The app will be running at `http://127.0.0.1:8000`.

## API

| Endpoint | Description |
|---|---|
| `POST /query/` | Ask a question in general chat mode (RAG-first, with Wikipedia/LLM fallback) |
| `POST /documents/upload` | Upload a PDF, TXT, or image to create a scoped document store |
| `POST /documents/query` | Ask a question scoped to an uploaded document |
| `DELETE /documents/{document_id}` | Remove an uploaded document |
| `POST /ocr/extract` | One-shot OCR: extract text from an image without creating a document store |

## Deployment

The included [Dockerfile](Dockerfile) reads the `PORT` environment variable, so it works on most container platforms without changes.

**Render / Fly.io / Railway** — connect the repo, set `NVIDIA_API_KEY` as a secret/environment variable, deploy. No GPU needed.

**Hugging Face Spaces (Docker SDK)**
1. Push this repo to GitHub (or connect it directly).
2. Create a new Space → choose the "Docker" SDK.
3. Set `NVIDIA_API_KEY` as a Space secret.
4. Ensure `data/sample.pdf` exists (or replace it) — it seeds the built-in document store used in general chat mode.

**Local Docker**

```bash
docker build -t corex .
docker run -p 8000:8000 --env-file .env corex
```

### Known limitations

- Uploaded documents are held in server memory only — they do not survive a restart, and are not shared across multiple worker processes/replicas.
- Uploads are capped at 10MB per file.

## License

MIT
