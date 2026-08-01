"""Keyword-based retrieval over the Part 107 knowledge base in docs/."""

import glob
import logging
import os
import re

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".md"}

# Resolved relative to this file, not the caller's cwd, so `python main.py`
# (or importing this module from anywhere) finds docs/ reliably.
DEFAULT_DOCS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")

TOPIC_QUERIES = {
    "airspace": "airspace classification controlled uncontrolled LAANC authorization class",
    "weather": "weather visibility cloud clearance minimums wind",
    "operations": "altitude visual line of sight daylight groundspeed operations over people right of way",
    "certification": "remote pilot certificate registration weight limit accident reporting preflight",
}


def load_documents(docs_folder):
    """Return a list of (filename, text) for every markdown doc in docs_folder."""
    paths = glob.glob(os.path.join(docs_folder, "**", "*"), recursive=True)
    documents = []
    for path in paths:
        if os.path.isfile(path) and os.path.splitext(path)[1] in ALLOWED_EXTENSIONS:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            documents.append((os.path.basename(path), text))
    return documents


def chunk_document(filename, text, min_words=10):
    """Split a markdown document into chunks at header boundaries."""
    raw_chunks = re.split(r"\n(?=#{1,3}\s)", text)
    chunks = []
    for chunk in raw_chunks:
        chunk = chunk.strip()
        if len(chunk.split()) >= min_words:
            chunks.append((filename, chunk))
    return chunks


def _tokenize(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _score(query_words, chunk_text):
    return len(query_words & _tokenize(chunk_text))


class KnowledgeBase:
    """Loads and indexes the Part 107 reference docs for keyword retrieval."""

    def __init__(self, docs_folder=None):
        self.docs_folder = docs_folder or DEFAULT_DOCS_FOLDER
        self.chunks = []
        self.build_index()

    def build_index(self):
        self.chunks = []
        documents = load_documents(self.docs_folder)
        if not documents:
            logger.warning("No reference documents found in %s", self.docs_folder)
        for filename, text in documents:
            self.chunks.extend(chunk_document(filename, text))
        logger.info(
            "Indexed %d chunks from %d documents in %s",
            len(self.chunks), len(documents), self.docs_folder,
        )

    def retrieve(self, query, top_k=3):
        """Return up to top_k (filename, chunk_text) tuples ranked by keyword overlap."""
        query_words = _tokenize(query)
        scored = [
            (_score(query_words, chunk_text), filename, chunk_text)
            for filename, chunk_text in self.chunks
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] <= 0:
            logger.debug("No chunks matched query: %r", query)
            return []
        return [(filename, chunk_text) for score, filename, chunk_text in scored[:top_k]]

    def retrieve_by_topic(self, topic, top_k=3):
        """Retrieve context for a known topic key (see TOPIC_QUERIES), or fall back
        to treating the topic string itself as the query."""
        query = TOPIC_QUERIES.get(topic.lower(), topic)
        return self.retrieve(query, top_k=top_k)
