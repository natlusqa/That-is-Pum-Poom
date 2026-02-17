"""
KORGAN AI — Vector Store Operations
Wrapper around ChromaDB for semantic memory.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger("korgan.memory.vectors")


class VectorStore:
    """
    ChromaDB-based vector store for semantic search.
    
    Collections:
    - korgan_memory: General conversation & context embeddings
    - korgan_code: Code snippets and project knowledge
    - korgan_decisions: Decision history for self-analysis
    """

    def __init__(self, host: str = "chromadb", port: int = 8003):
        self._host = host
        self._port = port
        self._client = None
        self._collections: dict[str, Any] = {}

    async def initialize(self) -> None:
        """Initialize ChromaDB client and collections."""
        try:
            import chromadb
            self._client = chromadb.HttpClient(host=self._host, port=self._port)

            # Create standard collections
            for name in ["korgan_memory", "korgan_code", "korgan_decisions"]:
                self._collections[name] = self._client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )
            logger.info("vector_store_initialized", collections=list(self._collections.keys()))
        except Exception as e:
            logger.error("vector_store_init_failed", error=str(e))

    def add(
        self,
        collection_name: str,
        document: str,
        doc_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a document to a collection."""
        collection = self._collections.get(collection_name)
        if not collection:
            logger.warning("collection_not_found", name=collection_name)
            return

        clean_meta = {}
        if metadata:
            clean_meta = {
                k: v for k, v in metadata.items()
                if isinstance(v, (str, int, float, bool))
            }

        collection.add(
            documents=[document],
            metadatas=[clean_meta],
            ids=[doc_id],
        )

    def query(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Query a collection by semantic similarity."""
        collection = self._collections.get(collection_name)
        if not collection:
            return []

        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query_text],
                "n_results": min(n_results, collection.count() or 1),
            }
            if where:
                kwargs["where"] = where

            results = collection.query(**kwargs)

            items = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    items.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0,
                        "id": results["ids"][0][i] if results["ids"] else "",
                    })
            return items

        except Exception as e:
            logger.error("vector_query_failed", collection=collection_name, error=str(e))
            return []

    def count(self, collection_name: str) -> int:
        """Get document count in a collection."""
        collection = self._collections.get(collection_name)
        return collection.count() if collection else 0

    def delete(self, collection_name: str, doc_ids: list[str]) -> None:
        """Delete documents by IDs."""
        collection = self._collections.get(collection_name)
        if collection and doc_ids:
            collection.delete(ids=doc_ids)

    def get_stats(self) -> dict[str, int]:
        """Get stats for all collections."""
        return {name: coll.count() for name, coll in self._collections.items()}
