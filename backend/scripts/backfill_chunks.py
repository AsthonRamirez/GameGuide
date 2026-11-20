"""Fragmenta y vectoriza los documentos ya guardados en `knowledge_documents` -> `knowledge_chunks`.

Ejecútalo UNA vez después de aplicar database/supabase_schema.sql (y cuando quieras reindexar):

    cd backend
    python -m scripts.backfill_chunks            # solo documentos sin fragmentos
    python -m scripts.backfill_chunks --all      # reindexa todo
"""
import argparse
import logging

from app.core import config as cfg
from app.services import embeddings
from app.services.persistence import require_supabase
from app.services.retrieval import doc_to_chunks

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("backfill")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="reindexar también documentos que ya tienen fragmentos")
    args = ap.parse_args()
    db = require_supabase()

    done = set()
    if not args.all:
        start = 0
        while True:
            rows = db.table("knowledge_chunks").select("source_id").range(start, start + 999).execute().data or []
            done.update(r["source_id"] for r in rows)
            if len(rows) < 1000:
                break
            start += 1000

    start, docs_ok, chunks_ok = 0, 0, 0
    while True:
        docs = (db.table("knowledge_documents")
                .select("source_id,source_name,source_type,title,content,url,category,game_version,retrieved_at")
                .range(start, start + 49).execute().data or [])
        if not docs:
            break
        for doc in docs:
            if doc["source_id"] in done:
                continue
            chunks = doc_to_chunks(doc)
            vectors = []
            for i in range(0, len(chunks), 32):
                vectors += embeddings.embed_texts([f'{c["title"]}. {c["content"]}' for c in chunks[i:i + 32]])
            rows = [{
                "source_id": c["source_id"], "chunk_index": c["chunk_index"], "content": c["content"],
                "title": c["title"], "url": c["url"], "source_name": c["source_name"],
                "source_type": c["source_type"], "category": c["category"],
                "game_version": c["game_version"], "retrieved_at": c["retrieved_at"], "embedding": v,
            } for c, v in zip(chunks, vectors)]
            if rows:
                db.table("knowledge_chunks").upsert(rows, on_conflict="source_id,chunk_index").execute()
                docs_ok += 1
                chunks_ok += len(rows)
                log.info("✔ %s (%d fragmentos)", doc["title"][:60], len(rows))
        start += 50
    log.info("Listo: %d documentos -> %d fragmentos (tamaño %d, traslape %d).",
             docs_ok, chunks_ok, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP)


if __name__ == "__main__":
    main()
