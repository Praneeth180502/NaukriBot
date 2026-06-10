"""
Skill taxonomy — maps skill names to categories.
Used by resume parser and job analyzer.
"""
from __future__ import annotations

# {skill_name: category}
SKILL_TAXONOMY: dict[str, str] = {
    # ── Languages ─────────────────────────────────────────────────────────
    "Python": "language",
    "JavaScript": "language",
    "TypeScript": "language",
    "Java": "language",
    "Go": "language",
    "Rust": "language",
    "C++": "language",
    "C": "language",
    "C#": "language",
    "Ruby": "language",
    "Swift": "language",
    "Kotlin": "language",
    "Scala": "language",
    "R": "language",
    "MATLAB": "language",
    "Shell": "language",
    "Bash": "language",
    "SQL": "language",

    # ── Backend ───────────────────────────────────────────────────────────
    "FastAPI": "backend",
    "Django": "backend",
    "Flask": "backend",
    "Node.js": "backend",
    "Express.js": "backend",
    "Spring Boot": "backend",
    "Spring": "backend",
    "Hibernate": "backend",
    "GraphQL": "backend",
    "REST API": "backend",
    "gRPC": "backend",
    "WebSockets": "backend",
    "Celery": "backend",
    "Redis": "backend",
    "RabbitMQ": "backend",
    "Kafka": "backend",
    "JWT": "backend",
    "OAuth2": "backend",
    "Microservices": "backend",
    "API Design": "backend",
    "Pydantic": "backend",
    "SQLAlchemy": "backend",

    # ── Frontend ──────────────────────────────────────────────────────────
    "React.js": "frontend",
    "React": "frontend",
    "Next.js": "frontend",
    "Vue.js": "frontend",
    "Angular": "frontend",
    "Svelte": "frontend",
    "HTML": "frontend",
    "CSS": "frontend",
    "Tailwind CSS": "frontend",
    "Bootstrap": "frontend",
    "Material UI": "frontend",
    "Redux": "frontend",
    "Zustand": "frontend",
    "React Query": "frontend",
    "Webpack": "frontend",
    "Vite": "frontend",
    "Three.js": "frontend",

    # ── AI/ML ─────────────────────────────────────────────────────────────
    "LangChain": "ai_ml",
    "LlamaIndex": "ai_ml",
    "Pydantic AI": "ai_ml",
    "Crawl4AI": "ai_ml",
    "RAG": "ai_ml",
    "Agentic AI": "ai_ml",
    "Prompt Engineering": "ai_ml",
    "LLMs": "ai_ml",
    "Semantic Search": "ai_ml",
    "AI Summarization": "ai_ml",
    "Machine Learning": "ai_ml",
    "Deep Learning": "ai_ml",
    "NLP": "ai_ml",
    "Computer Vision": "ai_ml",
    "PyTorch": "ai_ml",
    "TensorFlow": "ai_ml",
    "scikit-learn": "ai_ml",
    "Hugging Face": "ai_ml",
    "Transformers": "ai_ml",
    "OpenAI": "ai_ml",
    "Anthropic": "ai_ml",
    "Ollama": "ai_ml",
    "Sentence Transformers": "ai_ml",
    "FAISS": "ai_ml",
    "Vector Databases": "ai_ml",
    "Embeddings": "ai_ml",
    "Fine-tuning": "ai_ml",
    "RLHF": "ai_ml",
    "MLflow": "ai_ml",
    "Weights & Biases": "ai_ml",
    "Pandas": "ai_ml",
    "NumPy": "ai_ml",
    "Matplotlib": "ai_ml",
    "Seaborn": "ai_ml",

    # ── Databases ─────────────────────────────────────────────────────────
    "PostgreSQL": "database",
    "MySQL": "database",
    "SQLite": "database",
    "MongoDB": "database",
    "Cassandra": "database",
    "DynamoDB": "database",
    "Supabase": "database",
    "Pinecone": "database",
    "Weaviate": "database",
    "Qdrant": "database",
    "Chroma": "database",
    "pgvector": "database",
    "Elasticsearch": "database",
    "Neo4j": "database",
    "InfluxDB": "database",
    "Supabase pgvector": "database",

    # ── DevOps ────────────────────────────────────────────────────────────
    "Docker": "devops",
    "Kubernetes": "devops",
    "Helm": "devops",
    "Terraform": "devops",
    "Ansible": "devops",
    "GitHub Actions": "devops",
    "GitLab CI": "devops",
    "Jenkins": "devops",
    "CircleCI": "devops",
    "CI/CD": "devops",
    "Git": "devops",
    "Linux": "devops",
    "Nginx": "devops",
    "Apache": "devops",
    "Prometheus": "devops",
    "Grafana": "devops",
    "ELK Stack": "devops",

    # ── Cloud ─────────────────────────────────────────────────────────────
    "AWS": "cloud",
    "GCP": "cloud",
    "Azure": "cloud",
    "Heroku": "cloud",
    "Vercel": "cloud",
    "Netlify": "cloud",
    "Firebase": "cloud",
    "Cloudflare": "cloud",
    "Lambda": "cloud",
    "EC2": "cloud",
    "S3": "cloud",
    "RDS": "cloud",
}


def categorize_skill(skill: str) -> str:
    """Return category for a skill, or 'other' if unknown."""
    # Exact match
    if skill in SKILL_TAXONOMY:
        return SKILL_TAXONOMY[skill]
    # Case-insensitive match
    skill_lower = skill.lower()
    for k, v in SKILL_TAXONOMY.items():
        if k.lower() == skill_lower:
            return v
    return "other"


# All skills as lowercase set for fast membership testing
ALL_SKILLS_LOWER: set[str] = {k.lower() for k in SKILL_TAXONOMY.keys()}


def normalize_skill(skill: str) -> str:
    """Return canonical casing from taxonomy, or original if not found."""
    skill_lower = skill.lower()
    for k in SKILL_TAXONOMY:
        if k.lower() == skill_lower:
            return k
    return skill
