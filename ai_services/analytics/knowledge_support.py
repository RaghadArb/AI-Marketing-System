"""Classify Knowledge Base support from Chroma retrieval evidence."""

# Existing company_documents collection uses HNSW space "l2" (Chroma default).
# For all-MiniLM-L6-v2 unit-normalized embeddings, Chroma L2 is squared Euclidean:
# distance ≈ 2 * (1 - cosine_similarity). Lower is closer.
L2_SUPPORTED_MAX = 0.85  # ~ cosine similarity 0.575
L2_WEAK_MAX = 1.35  # ~ cosine similarity 0.325

# Cosine space in Chroma is 1 - cosine_similarity. Lower is closer.
COSINE_SUPPORTED_MAX = 0.42
COSINE_WEAK_MAX = 0.68

# Inner product: higher is closer (not the current collection space).
IP_SUPPORTED_MIN = 0.55
IP_WEAK_MIN = 0.30


def collection_space(vector_store):
    collection = getattr(vector_store, "collection", None)
    config = getattr(collection, "configuration", None) or {}
    hnsw = config.get("hnsw") if isinstance(config, dict) else None
    if isinstance(hnsw, dict) and hnsw.get("space"):
        return str(hnsw["space"]).lower()
    metadata = getattr(collection, "metadata", None) or {}
    if isinstance(metadata, dict):
        return str(metadata.get("hnsw:space") or metadata.get("space") or "l2").lower()
    return "l2"


def parse_query_results(results):
    results = results or {}
    documents = results.get("documents") or [[]]
    metadatas = results.get("metadatas") or [[]]
    distances = results.get("distances")
    docs = documents[0] if documents else []
    metas = metadatas[0] if metadatas else []
    dists = None
    if isinstance(distances, list) and distances:
        first = distances[0]
        if isinstance(first, list):
            dists = first
    hits = []
    for index, doc in enumerate(docs):
        text = str(doc).strip() if doc else ""
        if not text:
            continue
        meta = metas[index] if index < len(metas) and isinstance(metas[index], dict) else {}
        distance = None
        if dists is not None and index < len(dists):
            try:
                distance = float(dists[index])
            except (TypeError, ValueError):
                distance = None
        hits.append(
            {
                "text": text,
                "metadata": meta,
                "distance": distance,
            }
        )
    has_distances = bool(hits) and all(hit["distance"] is not None for hit in hits)
    return hits, has_distances


def source_label(metadata):
    if not isinstance(metadata, dict):
        return None
    for key in ("source", "filename", "title"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return None


def _band_for_distance(distance, space):
    space = (space or "l2").lower()
    if distance is None:
        return None
    if space == "ip":
        if distance >= IP_SUPPORTED_MIN:
            return "strong"
        if distance >= IP_WEAK_MIN:
            return "moderate"
        return "poor"
    strong_max = COSINE_SUPPORTED_MAX if space == "cosine" else L2_SUPPORTED_MAX
    weak_max = COSINE_WEAK_MAX if space == "cosine" else L2_WEAK_MAX
    if distance <= strong_max:
        return "strong"
    if distance <= weak_max:
        return "moderate"
    return "poor"


def classify_hits(hits, has_distances, space="l2"):
    if not hits:
        return {
            "knowledge_support": "No Knowledge Found",
            "relevance_label": None,
            "retrieved_chunks": 0,
            "retrieved_documents": [],
            "classification_basis": "chroma_distance" if has_distances else "retrieval_availability",
        }

    sources = []
    for hit in hits:
        label = source_label(hit.get("metadata"))
        if label and label not in sources:
            sources.append(label)

    if not has_distances:
        chunk_count = len(hits)
        if chunk_count == 0:
            status = "No Knowledge Found"
        elif chunk_count == 1:
            status = "Weak Support"
        else:
            status = "Supported"
        return {
            "knowledge_support": status,
            "relevance_label": None,
            "retrieved_chunks": chunk_count,
            "retrieved_documents": sources,
            "classification_basis": "retrieval_availability",
        }

    bands = [_band_for_distance(hit.get("distance"), space) for hit in hits]
    if "strong" in bands:
        status = "Supported"
        relevance = "High relevance"
    elif "moderate" in bands:
        status = "Weak Support"
        relevance = "Moderate relevance"
    else:
        status = "No Knowledge Found"
        relevance = "Low relevance"

    return {
        "knowledge_support": status,
        "relevance_label": relevance,
        "retrieved_chunks": len(hits),
        "retrieved_documents": sources,
        "classification_basis": "chroma_distance",
    }
