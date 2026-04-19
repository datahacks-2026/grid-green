"""Build/refresh the RAG index in either local SQLite or Snowflake Cortex.

Usage:

    python -m scripts.build_rag_index --target local      # default
    python -m scripts.build_rag_index --target snowflake  # Cortex VECTOR

Local target verifies the corpus loads, prints stats, and pre-warms the
TF-IDF matrix so the first request after a server restart is fast. The
Snowflake target uploads (id, doc_text, embedding) rows into a Cortex
table — requires `SNOWFLAKE_*` and a Cortex-enabled warehouse.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services import rag  # noqa: E402

logger = logging.getLogger("build_rag_index")


def build_local() -> None:
    index = rag.get_index()
    index._ensure_loaded()  # noqa: SLF001
    logger.info("Loaded %d entries.", len(index._entries))  # noqa: SLF001
    logger.info("Embedding backend: %s", "sentence-transformers" if index._st_model else "tf-idf")  # noqa: SLF001
    logger.info("Sanity: top match for 'flan-t5-xxl' →")
    ranked = index._rank("google/flan-t5-xxl")[:3]  # noqa: SLF001
    for entry, score in ranked:
        logger.info("  %.3f  %s -> %s", score, entry.from_model, entry.to_model)


def build_snowflake() -> None:
    from app.config import get_settings

    settings = get_settings()
    if not settings.use_snowflake:
        logger.error("SNOWFLAKE_* not configured. Set them in backend/.env first.")
        sys.exit(1)

    try:
        import snowflake.connector  # type: ignore
    except Exception:
        logger.error(
            "snowflake-connector-python missing. pip install -r requirements-extras.txt"
        )
        sys.exit(1)

    index = rag.get_index()
    index._ensure_loaded()  # noqa: SLF001

    if index._st_matrix is None:  # noqa: SLF001
        logger.error(
            "sentence-transformers not available — install requirements-extras.txt or "
            "run scripts/brev_embed.py first."
        )
        sys.exit(1)

    ctx = snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        password=settings.snowflake_password,
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        schema=settings.snowflake_schema,
        role=settings.snowflake_role,
    )
    try:
        cs = ctx.cursor()
        cs.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_hf_corpus (
                id        STRING,
                from_model STRING,
                to_model   STRING,
                doc_text   STRING,
                embedding  VECTOR(FLOAT, 384)
            )
            """
        )
        cs.execute("TRUNCATE TABLE rag_hf_corpus")
        # VECTOR columns: server-side binding is not supported; binding a Python list
        # fails (252001 with executemany, or FIXED type errors with execute). Pass a
        # JSON array string and cast via PARSE_JSON.
        insert_sql = """
            INSERT INTO rag_hf_corpus (id, from_model, to_model, doc_text, embedding)
            SELECT %s, %s, %s, %s, PARSE_JSON(%s)::VECTOR(FLOAT, 384)
            """
        uploaded = 0
        for entry, vec in zip(index._entries, index._st_matrix):  # noqa: SLF001
            emb_json = json.dumps([float(x) for x in vec])
            cs.execute(
                insert_sql,
                (
                    f"{entry.from_model}->{entry.to_model}",
                    entry.from_model,
                    entry.to_model,
                    entry.doc_text,
                    emb_json,
                ),
            )
            uploaded += 1
        ctx.commit()
        logger.info("Uploaded %d corpus entries to Snowflake Cortex.", uploaded)
    finally:
        ctx.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=["local", "snowflake"], default="local")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.target == "local":
        build_local()
    else:
        build_snowflake()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
