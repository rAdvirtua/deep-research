import os
import gc
import fitz
import numpy as np

BACKEND = os.getenv("RAG_BACKEND", "faiss")
MODEL_NAME = 'all-MiniLM-L6-v2'

_engine = None
_faiss_index = None
_faiss_encoder = None
_faiss_chunks = []

def init_engine():
    global _engine, _faiss_encoder
    if BACKEND == "locvec":
        from locvec import LocalVec
        _engine = LocalVec(model_name=MODEL_NAME)
    else:
        from sentence_transformers import SentenceTransformer
        import torch
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        _faiss_encoder = SentenceTransformer(MODEL_NAME, device=device)

def extract_and_chunk_pdf(file_path, chunk_size=300):
    text = ""
    try:
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    except Exception:
        return []

def build_full_index(chunks):
    global _faiss_index, _faiss_chunks
    if not chunks:
        return
    if BACKEND == "locvec":
        _engine.build_full_index(chunks)
    else:
        import faiss
        _faiss_chunks.extend(chunks)
        embeddings = _faiss_encoder.encode(chunks, convert_to_numpy=True)
        if _faiss_index is None:
            _faiss_index = faiss.IndexFlatL2(embeddings.shape[1])
        _faiss_index.add(embeddings)

def search_context(query: str) -> str:
    try:
        if BACKEND == "locvec":
            idx, context = _engine.search(query)
            if not context or len(context.strip()) == 0 or idx < 0:
                return "LOCAL_FAILURE: No relevant context found."
            return f"Context: {context}"
        else:
            if _faiss_index is None or not _faiss_chunks:
                return "LOCAL_FAILURE: No index built."
            q_emb = _faiss_encoder.encode([query], convert_to_numpy=True)
            D, I = _faiss_index.search(q_emb, 1)
            idx = I[0][0]
            if idx < 0 or idx >= len(_faiss_chunks):
                return "LOCAL_FAILURE: No relevant context found."
            return f"Context: {_faiss_chunks[idx]}"
    except Exception as e:
        return f"LOCAL_FAILURE: Execution error: {str(e)}"

def offload_encoder():
    if BACKEND == "locvec":
        _engine.offload_encoder()
    else:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()
        gc.collect()