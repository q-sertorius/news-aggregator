# src/news_aggregator/db/vector_store.py

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import os
from typing import List, Dict, Optional, Any


class VectorStore:
    def __init__(
        self,
        persist_directory: str = "data/chromadb",
        collection_name: str = "news_subjects",
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=persist_directory)

        # Load embedding model (MiniLM is perfect for CPU/laptop)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

        # Create or get collection
        self.collection = self.client.get_or_create_collection(name=collection_name)

    async def add_subject(
        self,
        subject_id: int,
        name: str,
        latest_status: str,
        metadata: Dict[str, Any] = {},
    ):
        """Add or update a subject's embedding in the vector store."""
        # Combine name and status for a richer semantic representation
        text_content = f"Subject: {name}. Status: {latest_status}"
        embedding = self.model.encode(text_content).tolist()

        self.collection.upsert(
            ids=[str(subject_id)],
            embeddings=[embedding],
            metadatas=[{**metadata, "name": name}],
            documents=[text_content],
        )

    async def find_similar_subjects(
        self, fact_summary: str, n_results: int = 5
    ) -> List[Dict]:
        """Find the top K subjects most similar to the given fact summary."""
        query_embedding = self.model.encode(fact_summary).tolist()

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["metadatas", "distances", "documents"],
        )

        formatted_results = []
        if (
            results.get("ids")
            and len(results["ids"]) > 0
            and len(results["ids"][0]) > 0
        ):
            for i in range(len(results["ids"][0])):
                metadata = {}
                if (
                    results.get("metadatas")
                    and results["metadatas"][0]
                    and results["metadatas"][0][i]
                ):
                    metadata = results["metadatas"][0][i]

                doc = ""
                if (
                    results.get("documents")
                    and results["documents"][0]
                    and results["documents"][0][i]
                ):
                    doc = results["documents"][0][i]

                formatted_results.append(
                    {
                        "id": int(results["ids"][0][i]),
                        "name": metadata.get("name", "Unknown"),
                        "distance": results["distances"][0][i]
                        if results.get("distances")
                        else 0,
                        "content": doc,
                    }
                )

        return formatted_results

    async def delete_subject(self, subject_id: int):
        """Remove a subject from the vector store."""
        self.collection.delete(ids=[str(subject_id)])
