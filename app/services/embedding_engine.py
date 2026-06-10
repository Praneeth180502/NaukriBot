"""
Embedding Engine
Loads sentence-transformers/all-MiniLM-L6-v2 locally.
Manages FAISS index for fast similarity search.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging import logger


class EmbeddingEngine:
    _instance: Optional["EmbeddingEngine"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._model: Optional[SentenceTransformer] = None
        self._index: Optional[faiss.Index] = None
        self._index_ids: List[int] = []   # job_id at position i in FAISS
        self._dim = 384                    # all-MiniLM-L6-v2 output dim
        self._initialized = True
        self._resume_embedding: Optional[np.ndarray] = None
        self._index_path = Path(settings.models.faiss_index_path)

    # ── Model loading ─────────────────────────────────────────────────────

    def load(self):
        if self._model is not None:
            return
        logger.info(f"Loading embedding model: {settings.models.embedding_model}")
        cache_dir = Path(settings.models.models_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = SentenceTransformer(
            settings.models.embedding_model,
            cache_folder=str(cache_dir),
        )
        logger.success("Embedding model loaded")
        self._load_index()

    def _load_index(self):
        idx_file = self._index_path.with_suffix(".faiss")
        ids_file = self._index_path.with_suffix(".ids")
        if idx_file.exists() and ids_file.exists():
            self._index = faiss.read_index(str(idx_file))
            with open(ids_file, "rb") as f:
                self._index_ids = pickle.load(f)
            logger.info(f"FAISS index loaded: {self._index.ntotal} vectors")
        else:
            self._index = faiss.IndexFlatIP(self._dim)   # Inner product = cosine after normalisation
            self._index_ids = []
            logger.info("FAISS index initialised (empty)")

    def save_index(self):
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._index_path.with_suffix(".faiss")))
        with open(self._index_path.with_suffix(".ids"), "wb") as f:
            pickle.dump(self._index_ids, f)
        logger.debug(f"FAISS index saved ({self._index.ntotal} vectors)")

    # ── Encoding ──────────────────────────────────────────────────────────

    def encode(self, texts: List[str]) -> np.ndarray:
        self.load()
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        # L2 normalise for cosine similarity via inner product
        faiss.normalize_L2(vectors)
        return vectors.astype(np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    # ── Resume embedding ──────────────────────────────────────────────────

    def set_resume_embedding(self, resume_text: str):
        self._resume_embedding = self.encode_one(resume_text)
        logger.info("Resume embedding set")

    def get_resume_embedding(self) -> Optional[np.ndarray]:
        return self._resume_embedding

    # ── FAISS index management ────────────────────────────────────────────

    def add_job(self, job_id: int, job_text: str) -> int:
        """Add a job to the FAISS index. Returns index position."""
        self.load()
        vec = self.encode([job_text]).astype(np.float32)
        position = self._index.ntotal
        self._index.add(vec)
        self._index_ids.append(job_id)
        return position

    def job_in_index(self, job_id: int) -> bool:
        return job_id in self._index_ids

    # ── Similarity ────────────────────────────────────────────────────────

    def compute_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Cosine similarity → [0, 100]."""
        # Both are L2-normalised so inner product = cosine similarity
        sim = float(np.dot(vec_a, vec_b))
        return round(max(0.0, min(100.0, sim * 100)), 2)

    def score_job_against_resume(self, job_text: str) -> float:
        """Returns match score 0–100."""
        if self._resume_embedding is None:
            return 0.0
        job_vec = self.encode_one(job_text)
        return self.compute_similarity(self._resume_embedding, job_vec)

    def find_similar_jobs(self, job_text: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """Returns [(job_id, score), ...]"""
        self.load()
        if self._index.ntotal == 0:
            return []
        vec = self.encode([job_text]).astype(np.float32)
        scores, indices = self._index.search(vec, min(top_k, self._index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self._index_ids):
                results.append((self._index_ids[idx], float(score) * 100))
        return results


# Singleton accessor
_engine: Optional[EmbeddingEngine] = None


def get_embedding_engine() -> EmbeddingEngine:
    global _engine
    if _engine is None:
        _engine = EmbeddingEngine()
    return _engine
