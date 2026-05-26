"""Entity-Aware Indexer — NER-based entity extraction + entity-prioritized retrieval.

P1 升级：解决文档匹配弱的问题。
- 实体感知分块：建索引时用 jieba NER 提取实体名，给每个 chunk 打实体标签
- 实体优先召回：检索时先按实体匹配召回，再用 embedding 补充
- 知识图谱路由：将 kg_nodes/kg_edges 作为检索路由层
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Any

from app.services.llm import llm_service
from app.services.knowledge_graph import knowledge_graph_service

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# NER Entity Extractor (jieba-based)
# ──────────────────────────────────────────────────────────────


class EntityExtractor:
    """Extract named entities from text using jieba POS tagging + regex patterns."""

    # Regex patterns for common entity types in Chinese documents
    _PERSON_PATTERN = re.compile(
        r"(?:(?:[A-Z][a-z]+\s){1,}[A-Z][a-z]+)|[^\x00-\x7F]{2,4}(?:先生|女士|教授|博士|老师|经理|主管)"
    )
    _ORG_PATTERN = re.compile(
        r"[^\x00-\x7F]{2,20}(?:公司|集团|大学|学院|研究院|研究所|协会|部门|团队|中心|实验室|委员会|办事处)"
    )
    _DATE_PATTERN = re.compile(
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    )
    _NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:%|万|亿|元|美金|美元|人民币)")
    _PRODUCT_PATTERN = re.compile(
        r"[^\x00-\x7F]{1,10}(?:系统|平台|产品|方案|工具|框架|模型|算法|接口|服务|引擎|组件)"
    )

    # jieba POS tags that indicate named entities
    _ENTITY_POS_TAGS = {"nr", "ns", "nt", "nz", "eng"}  # person, place, org, proper noun, English

    @classmethod
    def extract(
        cls, text: str, use_jieba: bool = True
    ) -> Dict[str, List[str]]:
        """Extract entities from text, categorized by type.

        Returns:
            Dict with keys: "persons", "organizations", "dates", "numbers",
            "products", "locations", "proper_nouns"
        """
        result: Dict[str, Set[str]] = {
            "persons": set(),
            "organizations": set(),
            "dates": set(),
            "numbers": set(),
            "products": set(),
            "locations": set(),
            "proper_nouns": set(),
        }

        # Regex-based extraction
        for match in cls._PERSON_PATTERN.finditer(text):
            result["persons"].add(match.group().strip())
        for match in cls._ORG_PATTERN.finditer(text):
            result["organizations"].add(match.group().strip())
        for match in cls._DATE_PATTERN.finditer(text):
            result["dates"].add(match.group().strip())
        for match in cls._NUMBER_PATTERN.finditer(text):
            result["numbers"].add(match.group().strip())
        for match in cls._PRODUCT_PATTERN.finditer(text):
            result["products"].add(match.group().strip())

        # jieba POS-based extraction
        if use_jieba:
            try:
                import jieba.posseg as pseg
                import jieba
                jieba.setLogLevel(logging.WARNING)
                words = pseg.cut(text)
                for word, flag in words:
                    if flag in cls._ENTITY_POS_TAGS and len(word) >= 2:
                        if flag == "ns":
                            result["locations"].add(word)
                        elif flag == "nr":
                            result["persons"].add(word)
                        elif flag == "nt":
                            result["organizations"].add(word)
                        else:
                            result["proper_nouns"].add(word)
            except ImportError:
                pass

        # Convert sets to sorted lists
        return {k: sorted(v) for k, v in result.items() if v}

    @classmethod
    def extract_flat(cls, text: str) -> List[str]:
        """Extract all entity names as a flat list, deduplicated."""
        entities = cls.extract(text)
        flat: List[str] = []
        for cat_entities in entities.values():
            flat.extend(cat_entities)
        # Deduplicate while preserving order
        seen: Set[str] = set()
        result: List[str] = []
        for e in flat:
            if e.lower() not in seen:
                seen.add(e.lower())
                result.append(e)
        return result


# ──────────────────────────────────────────────────────────────
# Entity-Aware Chunk
# ──────────────────────────────────────────────────────────────

@dataclass
class EntityChunk:
    """A text chunk annotated with entity information."""
    chunk_id: str
    content: str
    page_num: int
    entities: Dict[str, List[str]]  # entity_type -> [entity names]
    entity_tags: List[str]  # flattened list for filtering
    char_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.char_count = len(self.content)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "page_num": self.page_num,
            "entities": self.entities,
            "entity_tags": self.entity_tags,
            "char_count": self.char_count,
            "metadata": self.metadata,
        }


class EntityChunker:
    """Split document content into entity-annotated chunks.

    Splits by sentence/paragraph boundaries, extracts entities per chunk,
    and assigns entity tags for downstream filtering.
    """

    # Sentence boundary regex (Chinese + English)
    _SENTENCE_BREAK = re.compile(r"(?<=[。！？；\n])\s*|(?<=[.!?;])\s+")

    def __init__(self, max_chunk_chars: int = 500, overlap_chars: int = 50):
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars

    def chunk_page(self, content: str, page_num: int) -> List[EntityChunk]:
        """Chunk a single page's content into entity-annotated chunks.

        Args:
            content: Raw text content of the page
            page_num: Page number (1-based)

        Returns:
            List of EntityChunk objects with entity annotations.
        """
        if not content.strip():
            return []

        # Split into sentences
        sentences = [s.strip() for s in self._SENTENCE_BREAK.split(content) if s.strip()]
        if not sentences:
            return []

        chunks: List[EntityChunk] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) > self.max_chunk_chars and current:
                chunk = self._make_chunk(current, page_num, len(chunks))
                chunks.append(chunk)
                # Overlap: keep last overlap_chars
                current = current[-self.overlap_chars:] + sentence if self.overlap_chars > 0 else sentence
            else:
                current += sentence
        if current.strip():
            chunk = self._make_chunk(current, page_num, len(chunks))
            chunks.append(chunk)

        return chunks

    def _make_chunk(self, content: str, page_num: int, index: int) -> EntityChunk:
        """Create an entity-annotated chunk."""
        entities = EntityExtractor.extract(content)
        entity_tags = EntityExtractor.extract_flat(content)
        chunk_id = f"p{page_num}_c{index}"
        return EntityChunk(
            chunk_id=chunk_id,
            content=content.strip(),
            page_num=page_num,
            entities=entities,
            entity_tags=entity_tags,
        )


# ──────────────────────────────────────────────────────────────
# Entity-Aware Index
# ──────────────────────────────────────────────────────────────

@dataclass
class EntityIndex:
    """Entity-first inverted index for fast entity-based retrieval."""
    # entity_name -> set of chunk_ids
    entity_to_chunks: Dict[str, Set[str]] = field(default_factory=dict)
    # chunk_id -> EntityChunk
    chunks: Dict[str, EntityChunk] = field(default_factory=dict)


class EntityAwareIndexer:
    """Build and query an entity-aware index.

    Builds an inverted index mapping entity names to chunks, enabling
    entity-first retrieval: when a query contains known entities,
    directly recall chunks containing those entities, then supplement
    with embedding-based recall.
    """

    def __init__(self):
        self._index = EntityIndex()

    def build_index(self, pages: List[Dict[str, Any]]) -> None:
        """Build entity index from document pages.

        Args:
            pages: List of page dicts with keys: page_number, content
        """
        chunker = EntityChunker()
        self._index = EntityIndex()

        for page in pages:
            page_num = page.get("page_number", 0)
            content = page.get("content", "")
            if not content:
                continue

            chunks = chunker.chunk_page(content, page_num)
            for chunk in chunks:
                self._index.chunks[chunk.chunk_id] = chunk
                for tag in chunk.entity_tags:
                    tag_lower = tag.lower()
                    if tag_lower not in self._index.entity_to_chunks:
                        self._index.entity_to_chunks[tag_lower] = set()
                    self._index.entity_to_chunks[tag_lower].add(chunk.chunk_id)

        logger.info(
            "Entity index built: %d chunks, %d unique entities, %d pages",
            len(self._index.chunks),
            len(self._index.entity_to_chunks),
            len(pages),
        )

    def query_entities(
        self, query_text: str, top_k: int = 10
    ) -> List[EntityChunk]:
        """Entity-first retrieval: find chunks by matching query entities.

        Args:
            query_text: Raw query text
            top_k: Maximum number of chunks to return

        Returns:
            List of EntityChunk objects matching query entities, ranked
            by number of entity matches.
        """
        # Extract entities from query
        query_entities = EntityExtractor.extract_flat(query_text)
        if not query_entities:
            return []

        # Score chunks by entity overlap count
        chunk_scores: Dict[str, int] = {}
        for entity in query_entities:
            entity_lower = entity.lower()
            if entity_lower in self._index.entity_to_chunks:
                for chunk_id in self._index.entity_to_chunks[entity_lower]:
                    chunk_scores[chunk_id] = chunk_scores.get(chunk_id, 0) + 1

        # Sort by score descending
        sorted_chunk_ids = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for chunk_id, score in sorted_chunk_ids[:top_k]:
            chunk = self._index.chunks.get(chunk_id)
            if chunk:
                chunk.metadata["entity_score"] = score
                results.append(chunk)

        return results

    def get_chunk_by_id(self, chunk_id: str) -> Optional[EntityChunk]:
        """Get a specific chunk by ID."""
        return self._index.chunks.get(chunk_id)

    def get_all_chunks(self) -> List[EntityChunk]:
        """Get all indexed chunks."""
        return list(self._index.chunks.values())

    def get_statistics(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "total_chunks": len(self._index.chunks),
            "total_entities": len(self._index.entity_to_chunks),
            "entity_distribution": {
                entity: len(chunk_set)
                for entity, chunk_set in sorted(
                    self._index.entity_to_chunks.items(),
                    key=lambda x: len(x[1]),
                    reverse=True,
                )[:20]
            },
        }


# ──────────────────────────────────────────────────────────────
# Knowledge Graph Router (kg_nodes/kg_edges as retrieval layer)
# ──────────────────────────────────────────────────────────────

@dataclass
class KGRouteResult:
    """Result from KG-based routing."""
    matched_nodes: List[Dict[str, Any]]
    matched_edges: List[Dict[str, Any]]
    related_entity_names: List[str]
    suggested_page_ranges: List[Dict[str, Any]]


class KnowledgeGraphRouter:
    """Route queries through the knowledge graph for entity-aware retrieval.

    Uses kg_nodes/kg_edges tables to:
    1. Match query entities against KG nodes
    2. Traverse edges to find related concepts
    3. Map back to document pages
    """

    def __init__(self):
        self.kg = knowledge_graph_service

    async def route_query(
        self,
        query: str,
        user_id: Optional[str] = None,
        db_session=None,
    ) -> KGRouteResult:
        """Route a query through the knowledge graph.

        1. Extract entities from query
        2. Match against kg_nodes
        3. Traverse kg_edges to expand context
        4. Return matched nodes + suggested page ranges

        Args:
            query: User query text
            user_id: Optional user identifier
            db_session: Optional database session

        Returns:
            KGRouteResult with matched nodes, edges, and suggested page ranges.
        """
        query_entities = EntityExtractor.extract_flat(query)

        matched_nodes: List[Dict[str, Any]] = []
        matched_edges: List[Dict[str, Any]] = []
        related_entities: Set[str] = set()
        suggested_pages: List[Dict[str, Any]] = []

        try:
            # Step 1: Enhance intent with KG (existing functionality)
            kg_result = await self.kg.enhance_intent_with_kg(
                query, query_entities, user_id, db_session
            )

            if kg_result:
                matched_nodes = kg_result.get("matched_nodes", [])
                matched_edges = kg_result.get("matched_edges", [])
                related_entities = set(kg_result.get("related_entities", []))

            # Step 2: Extract page references from matched nodes
            for node in matched_nodes:
                metadata = node.get("metadata", {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {}
                page_refs = metadata.get("page_refs", [])
                for ref in page_refs:
                    if isinstance(ref, dict) and "page" in ref:
                        suggested_pages.append({
                            "page": ref["page"],
                            "chunk_id": ref.get("chunk_id", ""),
                            "entity": node.get("name", ""),
                            "source": "kg_node",
                        })

        except Exception as exc:
            logger.warning("KG routing failed for query: %s", exc)

        return KGRouteResult(
            matched_nodes=matched_nodes,
            matched_edges=matched_edges,
            related_entity_names=list(related_entities),
            suggested_page_ranges=suggested_pages,
        )


# ──────────────────────────────────────────────────────────────
# Hybrid Entity-First Retriever
# ──────────────────────────────────────────────────────────────

class HybridEntityRetriever:
    """Hybrid retriever: entity-first recall + KG routing + embedding fallback.

    Retrieval priority:
    1. Entity exact match recall (entity_indexer)
    2. KG graph traversal routing (kg_router)
    3. Embedding similarity fallback (delegated to existing PageRetriever)
    """

    def __init__(self):
        self.entity_indexer = EntityAwareIndexer()
        self.kg_router = KnowledgeGraphRouter()

    def build(self, pages: List[Dict[str, Any]]) -> None:
        """Build the entity index from document pages."""
        self.entity_indexer.build_index(pages)

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        user_id: Optional[str] = None,
        db_session=None,
    ) -> Dict[str, Any]:
        """Hybrid entity-first retrieval.

        Returns:
            Dict with keys:
            - "entity_chunks": List[EntityChunk] from entity index
            - "kg_routes": KGRouteResult from KG routing
            - "combined_page_nums": List[int] union of all page suggestions
            - "entity_names": List[str] entities found in query
        """
        # Step 1: Entity-first recall
        entity_chunks = self.entity_indexer.query_entities(query, top_k=top_k)

        # Step 2: KG routing
        kg_result = await self.kg_router.route_query(query, user_id, db_session)

        # Step 3: Combine page suggestions
        page_nums: Set[int] = set()
        for chunk in entity_chunks:
            page_nums.add(chunk.page_num)
        for ref in kg_result.suggested_page_ranges:
            if "page" in ref:
                page_nums.add(ref["page"])

        return {
            "entity_chunks": [chunk.to_dict() for chunk in entity_chunks],
            "kg_routes": {
                "matched_nodes": kg_result.matched_nodes,
                "matched_edges": kg_result.matched_edges,
                "related_entity_names": kg_result.related_entity_names,
                "suggested_page_ranges": kg_result.suggested_page_ranges,
            },
            "combined_page_nums": sorted(page_nums),
            "entity_names": EntityExtractor.extract_flat(query),
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get combined retrieval statistics."""
        return {
            "entity_index": self.entity_indexer.get_statistics(),
        }


# ──────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────

hybrid_entity_retriever = HybridEntityRetriever()