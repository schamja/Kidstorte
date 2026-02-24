"""Dokumente in ChromaDB laden."""

import json
from pathlib import Path
import chromadb
from openai import OpenAI
from config import OPENAI_API_KEY, EMBEDDING_MODEL, CHROMA_DB_PATH, COLLECTION_NAME, DOCS_DIR

openai_client = OpenAI(api_key=OPENAI_API_KEY)
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)


def chunk_by_sections(text):
    chunks = []
    for section in text.split("\n## "):
        section = section.strip()
        if section:
            if not section.startswith("## "):
                section = "## " + section
            chunks.append(section)
    return chunks if chunks else [text]


def ingest():
    docs_path = Path(DOCS_DIR)
    total = 0

    for md_file in sorted(docs_path.glob("*.md")):
        print(f"\nVerarbeite: {md_file.name}")
        text = md_file.read_text(encoding="utf-8")
        chunks = chunk_by_sections(text)

        for idx, chunk in enumerate(chunks, 1):
            chunk_id = f"{md_file.stem}_{idx:03d}"

            existing = collection.get(ids=[chunk_id])
            if existing and existing["ids"]:
                print(f"  Überspringe: {chunk_id}")
                continue

            embedding = openai_client.embeddings.create(
                model=EMBEDDING_MODEL, input=chunk
            ).data[0].embedding

            collection.add(
                ids=[chunk_id],
                metadatas=[{"source": md_file.name, "type": md_file.stem}],
                embeddings=[embedding],
                documents=[chunk]
            )
            print(f"  ✅ {chunk_id}")
            total += 1

    print(f"\nFertig! {total} neue Chunks. Gesamt: {collection.count()}")


if __name__ == "__main__":
    ingest()
