# tests/verify_phase1.py
import asyncio
import os
import shutil
from news_aggregator.db.repository import NewsRepository
from news_aggregator.db.vector_store import VectorStore


async def verify():
    print("--- Phase 1 Verification ---")

    # Cleanup any previous test data
    if os.path.exists("data/test_news.db"):
        os.remove("data/test_news.db")
    if os.path.exists("data/test_chroma"):
        shutil.rmtree("data/test_chroma")

    # 1. Initialize Components
    repo = NewsRepository(db_path="data/test_news.db")
    await repo.initialize()
    print("[OK] SQLite Initialized")

    vstore = VectorStore(
        persist_directory="data/test_chroma", collection_name="test_subjects"
    )
    print("[OK] Vector Store Initialized")

    # 2. Test SQLite CRUD
    subject_id = await repo.get_or_create_subject(
        "Federal Reserve Policy", "macroeconomics"
    )
    print(f"[OK] Subject Created (ID: {subject_id})")

    article_id = await repo.add_article(
        subject_id,
        {
            "title": "Fed Signals Rate Hold",
            "source_url": "https://example.com/fed-news",
            "summary_snippet": "The Fed decided to keep rates unchanged at 5.25%.",
        },
    )
    print(f"[OK] Article Added (ID: {article_id})")

    await repo.update_subject_status(
        subject_id, "Rates held at 5.25%", "HIGH", ["USD", "SPY"]
    )
    print("[OK] Subject Status Updated")

    # 3. Test Vector Store
    await vstore.add_subject(
        subject_id, "Federal Reserve Policy", "Rates held at 5.25% by the FOMC."
    )
    print("[OK] Subject Added to Vector Store")

    # 4. Test Similarity Search
    # We search for something semantically similar but not identical
    query = "Will the central bank change interest rates soon?"
    results = await vstore.find_similar_subjects(query, n_results=1)

    if results and results[0]["id"] == subject_id:
        print(
            f"[PASS] Vector Search Found Match: '{results[0]['name']}' (Distance: {results[0]['distance']:.4f})"
        )
    else:
        print("[FAIL] Vector Search could not find the relevant subject.")
        print(f"Results: {results}")

    # 5. Database Content Verification
    subjects = await repo.get_active_subjects()
    if len(subjects) > 0 and subjects[0]["name"] == "Federal Reserve Policy":
        print(f"[PASS] SQLite Persistence Verified: {subjects[0]['latest_status']}")
    else:
        print("[FAIL] SQLite data retrieval failed.")


if __name__ == "__main__":
    asyncio.run(verify())
