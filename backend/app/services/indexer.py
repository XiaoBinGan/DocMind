

import uuid
import json
import asyncio
import logging
from typing import List, Optional
from app.services.parser import document_parser
from app.services.llm import llm_service
from app.core.config import settings

logger = logging.getLogger(__name__)

# 单次 LLM 超时（秒）
LLM_TIMEOUT = 180
# 每页摘要截断字符数（压缩 token）
PAGE_DIGEST_CHARS = 300
# 送入 LLM 的最大总字符数
MAX_PROMPT_CHARS = 10000


class IndexNode:
    def __init__(
        self,
        title: str,
        page_start: int,
        page_end: int,
        level: int,
        content_summary: str = "",
        raw_content: str = ""
    ):
        self.id = str(uuid.uuid4())[:8]
        self.title = title
        self.page_start = page_start
        self.page_end = page_end
        self.level = level
        self.content_summary = content_summary
        self.raw_content = raw_content
        self.children: List["IndexNode"] = []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "level": self.level,
            "content_summary": self.content_summary,
            "raw_content": self.raw_content,
            "children": [child.to_dict() for child in self.children]
        }

    @staticmethod
    def from_dict(data: dict) -> "IndexNode":
        node = IndexNode(
            title=data["title"],
            page_start=data["page_start"],
            page_end=data["page_end"],
            level=data["level"],
            content_summary=data.get("content_summary", ""),
            raw_content=data.get("raw_content", "")
        )
        node.id = data.get("id", str(uuid.uuid4())[:8])
        if "children" in data:
            node.children = [IndexNode.from_dict(child) for child in data["children"]]
        return node

    def get_all_nodes(self) -> List["IndexNode"]:
        """Get all nodes including children recursively."""
        nodes = [self]
        for child in self.children:
            nodes.extend(child.get_all_nodes())
        return nodes


class PageIndexer:
    """
    PageIndex 索引构建器（方案B：单次 LLM 调用）

    核心思路：
    1. 解析文档页面
    2. 每页取前 PAGE_DIGEST_CHARS 字符拼成摘要
    3. 单次 LLM 调用，直接输出目录树 JSON
    4. 解析失败时降级为启发式简单树
    """

    def __init__(self):
        self.max_depth = settings.MAX_TREE_DEPTH
        self.max_leaves = settings.MAX_LEAF_NODES

    async def build_index(self, file_path: str) -> dict:
        """Build a PageIndex tree from a document."""
        parsed = await document_parser.parse(file_path)
        if not parsed.get("success"):
            return {"success": False, "error": parsed.get("error")}

        pages = parsed["pages"]
        title = parsed.get("title", "Untitled")

        logger.info(f"[INDEXER] Building index for '{title}', {len(pages)} pages")

        index_tree = await self._build_tree_direct(title, pages)

        return {
            "success": True,
            "page_count": len(pages),
            "index_tree": index_tree.to_dict() if index_tree else None,
            "title": title
        }

    # ------------------------------------------------------------------
    # 核心：单次 LLM 调用构建目录树
    # ------------------------------------------------------------------

    async def _build_tree_direct(self, title: str, pages: List[dict]) -> "IndexNode":
        """
        将所有页面内容压缩后，单次调用 LLM 生成层级目录树。
        失败时自动降级为启发式树。
        """
        pages_digest = self._build_pages_digest(pages)

        if not pages_digest.strip():
            logger.warning("[INDEXER] No valid page content, using simple fallback")
            return self._simple_fallback(title, pages)

        prompt = f"""Build a hierarchical table of contents for the following document.

TITLE: {title}
TOTAL PAGES: {len(pages)}

PAGE CONTENT DIGEST (each page truncated):
{pages_digest}

Instructions:
- Identify main sections (level 1) and optional subsections (level 2)
- Each section must have an accurate page_start and page_end
- Write a brief summary (1-2 sentences) for each section

Return ONLY valid JSON, no explanation, no markdown:
{{
  "sections": [
    {{
      "title": "Section Name",
      "level": 1,
      "page_start": 1,
      "page_end": 5,
      "summary": "Brief description of this section.",
      "subsections": [
        {{
          "title": "Subsection Name",
          "level": 2,
          "page_start": 1,
          "page_end": 3,
          "summary": "Brief description."
        }}
      ]
    }}
  ]
}}"""

        try:
            logger.info("[INDEXER] Calling LLM for tree structure (single call)")
            result = await asyncio.wait_for(
                llm_service.generate_structure(prompt),
                timeout=LLM_TIMEOUT
            )
            return self._parse_llm_tree(result, title, pages)

        except asyncio.TimeoutError:
            logger.warning(f"[INDEXER] LLM timed out after {LLM_TIMEOUT}s, using heuristic fallback")
            return self._heuristic_fallback(title, pages)

        except Exception as e:
            logger.warning(f"[INDEXER] LLM call failed: {e}, using heuristic fallback")
            return self._heuristic_fallback(title, pages)

    # ------------------------------------------------------------------
    # 辅助：构建页面摘要文本
    # ------------------------------------------------------------------

    def _build_pages_digest(self, pages: List[dict]) -> str:
        """
        每页取前 PAGE_DIGEST_CHARS 字符，拼成一个文本块。
        总长度超过 MAX_PROMPT_CHARS 时截断，避免 prompt 过大。
        """
        lines = []
        total = 0
        for p in pages:
            content = (p.get("content") or "").strip()
            if not content:
                continue
            snippet = content[:PAGE_DIGEST_CHARS].replace("\n", " ")
            line = f"P{p['page_number']}: {snippet}"
            total += len(line)
            if total > MAX_PROMPT_CHARS:
                lines.append(f"... (remaining pages omitted, total {len(pages)} pages)")
                break
            lines.append(line)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 辅助：解析 LLM 返回的 JSON
    # ------------------------------------------------------------------

    def _parse_llm_tree(self, result: str, title: str, pages: List[dict]) -> "IndexNode":
        """Parse LLM JSON output into an IndexNode tree."""
        import re

        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if not json_match:
            logger.warning("[INDEXER] No JSON found in LLM response")
            return self._heuristic_fallback(title, pages)

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"[INDEXER] JSON parse error: {e}")
            return self._heuristic_fallback(title, pages)

        sections = data.get("sections", [])
        if not sections:
            logger.warning("[INDEXER] LLM returned empty sections")
            return self._heuristic_fallback(title, pages)

        root = IndexNode(
            title=title,
            page_start=1,
            page_end=len(pages),
            level=0
        )

        for section in sections:
            section_node = IndexNode(
                title=section.get("title", "Untitled Section"),
                page_start=section.get("page_start", 1),
                page_end=section.get("page_end", len(pages)),
                level=section.get("level", 1),
                content_summary=section.get("summary", "")
            )

            for sub in section.get("subsections", []):
                sub_node = IndexNode(
                    title=sub.get("title", "Untitled Subsection"),
                    page_start=sub.get("page_start", section_node.page_start),
                    page_end=sub.get("page_end", section_node.page_end),
                    level=sub.get("level", 2),
                    content_summary=sub.get("summary", "")
                )
                section_node.children.append(sub_node)

            root.children.append(section_node)

        logger.info(
            f"[INDEXER] Tree built: {len(root.children)} sections, "
            f"{sum(len(s.children) for s in root.children)} subsections"
        )
        return root

    # ------------------------------------------------------------------
    # 降级策略
    # ------------------------------------------------------------------

    def _heuristic_fallback(self, title: str, pages: List[dict]) -> "IndexNode":
        """
        启发式降级：取每页第一个有意义的短行作为节点标题。
        无需 LLM，速度极快。
        """
        logger.info("[INDEXER] Using heuristic fallback")
        root = IndexNode(title=title, page_start=1, page_end=len(pages), level=0)

        for page in pages:
            content = (page.get("content") or "").strip()
            if not content:
                continue

            heading = self._extract_heading(content, page["page_number"])
            node = IndexNode(
                title=heading,
                page_start=page["page_number"],
                page_end=page["page_number"],
                level=1,
                raw_content=content[:500]
            )
            root.children.append(node)

        return root

    def _simple_fallback(self, title: str, pages: List[dict]) -> "IndexNode":
        """最简降级：所有页平铺，无标题提取。"""
        root = IndexNode(title=title, page_start=1, page_end=len(pages), level=0)
        for page in pages:
            if (page.get("content") or "").strip():
                root.children.append(IndexNode(
                    title=f"Page {page['page_number']}",
                    page_start=page["page_number"],
                    page_end=page["page_number"],
                    level=1,
                    raw_content=(page["content"] or "")[:500]
                ))
        return root

    @staticmethod
    def _extract_heading(content: str, page_number: int) -> str:
        """从页面内容中提取最可能是标题的行。"""
        for line in content.split("\n"):
            line = line.strip()
            if 5 < len(line) < 80 and not line.endswith(","):
                return line
        return f"Page {page_number}"


# ---------------------------------------------------------------------------
# 检索器（与原版保持一致，无改动）
# ---------------------------------------------------------------------------

class PageRetriever:
    """
    PageIndex 检索器

    核心思路：
    1. 接收用户问题
    2. 让 LLM "思考"需要检索什么，遍历索引树
    3. 选择最相关的节点
    4. 返回上下文片段
    """

    def __init__(self, index_tree: Optional[dict] = None, pages: Optional[List[dict]] = None):
        self.index_tree = IndexNode.from_dict(index_tree) if index_tree else None
        self.pages = pages or []
        self._page_map = {p["page_number"]: p for p in self.pages}

    def set_index(self, index_tree: dict, pages: List[dict]):
        self.index_tree = IndexNode.from_dict(index_tree) if index_tree else None
        self.pages = pages
        self._page_map = {p["page_number"]: p for p in pages}

    async def retrieve(self, query: str, top_k: int = 5) -> List[dict]:
        """
        Retrieve relevant content based on query using reasoning-based retrieval.

        Instead of vector similarity, we use LLM to:
        1. Analyze what information is needed
        2. Traverse the index tree to find relevant sections
        3. Extract content from relevant pages
        """
        if not self.index_tree:
            return []

        tree_repr = self._tree_to_text(self.index_tree)

        prompt = f"""You are analyzing a document index to find relevant sections for answering a user question.

USER QUESTION: {query}

DOCUMENT INDEX STRUCTURE:
{tree_repr}

Analyze which sections are most relevant to answer the user's question.
Consider:
1. What information does the user need?
2. Which sections would contain this information?
3. What's the logical order of information?

Return a JSON list of relevant page ranges, ordered by relevance:
[
    {{"page_start": 1, "page_end": 3, "reason": "Contains introduction and overview"}},
    {{"page_start": 5, "page_end": 7, "reason": "Detailed technical specifications"}}
]

Respond with JSON only, no other text."""

        try:
            result = await llm_service.generate_structure(prompt)
            import re
            json_match = re.search(r'\[.*\]', result, re.DOTALL)

            if json_match:
                ranges = json.loads(json_match.group())

                results = []
                for r in ranges[:top_k]:
                    ps = r.get("page_start", 1)
                    pe = r.get("page_end", ps)
                    reason = r.get("reason", "")

                    for pn in range(ps, pe + 1):
                        if pn in self._page_map:
                            page = self._page_map[pn]
                            if page["content"]:
                                results.append({
                                    "page": pn,
                                    "content": page["content"],
                                    "reason": reason,
                                    "char_count": page["char_count"]
                                })

                return results
            else:
                return self._fallback_retrieve(query, top_k)

        except Exception:
            return self._fallback_retrieve(query, top_k)

    def _fallback_retrieve(self, query: str, top_k: int) -> List[dict]:
        """Fallback: return content from all pages."""
        results = []
        for page in self.pages[:top_k]:
            if page["content"]:
                results.append({
                    "page": page["page_number"],
                    "content": page["content"],
                    "reason": "Content page",
                    "char_count": page["char_count"]
                })
        return results

    def _tree_to_text(self, node: IndexNode, indent: int = 0) -> str:
        """Convert tree to readable text representation."""
        prefix = "  " * indent
        text = f"{prefix}[L{node.level}] {node.title} (pages {node.page_start}-{node.page_end})\n"
        for child in node.children:
            text += self._tree_to_text(child, indent + 1)
        return text


page_indexer = PageIndexer()










# 
# 
















# import uuid
# import json
# import asyncio
# import logging
# from typing import List, Optional
# from app.services.parser import document_parser
# from app.services.llm import llm_service
# from app.core.config import settings

# logger = logging.getLogger(__name__)

# # 批量摘要配置：每批处理页数
# BATCH_SIZE = 5
# # 并发批次数
# MAX_CONCURRENT_BATCHES = 2
# # 单次 LLM 超时（秒）
# LLM_TIMEOUT = 180

# class IndexNode:
#     def __init__(
#         self, 
#         title: str, 
#         page_start: int, 
#         page_end: int, 
#         level: int,
#         content_summary: str = "",
#         raw_content: str = ""
#     ):
#         self.id = str(uuid.uuid4())[:8]
#         self.title = title
#         self.page_start = page_start
#         self.page_end = page_end
#         self.level = level
#         self.content_summary = content_summary
#         self.raw_content = raw_content
#         self.children: List[IndexNode] = []
    
#     def to_dict(self) -> dict:
#         return {
#             "id": self.id,
#             "title": self.title,
#             "page_start": self.page_start,
#             "page_end": self.page_end,
#             "level": self.level,
#             "content_summary": self.content_summary,
#             "raw_content": self.raw_content,
#             "children": [child.to_dict() for child in self.children]
#         }
    
#     @staticmethod
#     def from_dict(data: dict) -> "IndexNode":
#         node = IndexNode(
#             title=data["title"],
#             page_start=data["page_start"],
#             page_end=data["page_end"],
#             level=data["level"],
#             content_summary=data.get("content_summary", ""),
#             raw_content=data.get("raw_content", "")
#         )
#         node.id = data.get("id", str(uuid.uuid4())[:8])
#         if "children" in data:
#             node.children = [IndexNode.from_dict(child) for child in data["children"]]
#         return node
    
#     def get_all_nodes(self) -> List["IndexNode"]:
#         """Get all nodes including children recursively."""
#         nodes = [self]
#         for child in self.children:
#             nodes.extend(child.get_all_nodes())
#         return nodes


# class PageIndexer:
#     """
#     PageIndex 索引构建器
    
#     核心思路：
#     1. 解析文档页面
#     2. 对每页/每个内容块生成摘要
#     3. 使用 LLM 分析内容结构，构建 ToC 树
#     4. 存储树结构供后续检索使用
#     """
    
#     def __init__(self):
#         self.max_depth = settings.MAX_TREE_DEPTH
#         self.max_leaves = settings.MAX_LEAF_NODES
    
#     async def build_index(self, file_path: str) -> dict:
#         """Build a PageIndex tree from a document."""
#         # Step 1: Parse the document
#         parsed = await document_parser.parse(file_path)
#         if not parsed.get("success"):
#             return {"success": False, "error": parsed.get("error")}
        
#         pages = parsed["pages"]
#         title = parsed.get("title", "Untitled")
        
#         # Step 2: Generate page summaries
#         page_summaries = await self._generate_page_summaries(pages)
        
#         # Step 3: Build the index tree
#         index_tree = await self._build_tree(title, pages, page_summaries)
        
#         return {
#             "success": True,
#             "page_count": len(pages),
#             "index_tree": index_tree.to_dict() if index_tree else None,
#             "title": title
#         }
    
#     async def _generate_page_summaries(self, pages: List[dict]) -> List[dict]:
#         """Generate summaries for pages using LLM with batching and concurrency."""
        
#         # 过滤出有内容的页面
#         valid_pages = [
#             p for p in pages
#             if p.get("content") and len(p["content"].strip()) >= 50
#         ]
        
#         if not valid_pages:
#             # 全部返回空摘要
#             return [
#                 {"page_number": p["page_number"], "summary": "", "key_topics": []}
#                 for p in pages
#             ]
        
#         # 分批
#         batches = [
#             valid_pages[i:i + BATCH_SIZE]
#             for i in range(0, len(valid_pages), BATCH_SIZE)
#         ]
        
#         logger.info(f"Generating summaries for {len(valid_pages)} pages in {len(batches)} batches")
#         print(f"[INDEXER] Generating summaries for {len(valid_pages)} pages in {len(batches)} batches")
        
#         # 并发处理批次
#         semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
        
#         async def process_batch(batch: List[dict]) -> List[dict]:
#             async with semaphore:
#                 return await self._summarize_batch(batch)
        
#         tasks = [process_batch(b) for b in batches]
#         batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
#         # 合并结果
#         summary_map = {}
#         for i, result in enumerate(batch_results):
#             if isinstance(result, Exception):
#                 logger.warning(f"Batch {i} failed: {result}")
#                 # 失败批次用空摘要
#                 for p in batches[i]:
#                     summary_map[p["page_number"]] = {
#                         "page_number": p["page_number"],
#                         "summary": p["content"][:200] + "...",
#                         "key_topics": []
#                     }
#             else:
#                 for s in result:
#                     summary_map[s["page_number"]] = s
        
#         # 按原页面顺序返回
#         summaries = []
#         for p in pages:
#             pn = p["page_number"]
#             if pn in summary_map:
#                 summaries.append(summary_map[pn])
#             else:
#                 summaries.append({"page_number": pn, "summary": "", "key_topics": []})
        
#         return summaries
    
#     async def _summarize_batch(self, batch: List[dict]) -> List[dict]:
#         """Summarize a batch of pages in one LLM call."""
#         # 构建批量内容
#         pages_text = "\n\n---\n\n".join([
#             f"[PAGE {p['page_number']}]\n{p['content'][:1500]}"  # 减小单页截断
#             for p in batch
#         ])
        
#         batch_pages = [p['page_number'] for p in batch]
#         print(f"[INDEXER] Summarizing batch: pages {batch_pages}")
        
#         prompt = f"""Analyze these document pages and provide brief summaries. Focus on tables, classifications, and key topics.

# {pages_text}

# Return a JSON array with one entry per page above (in order):
# [
#   {{"page": 1, "summary": "2-3 sentence summary", "topics": ["topic1", "topic2"]}},
#   ...
# ]

# JSON only, no other text."""
        
#         try:
#             # 带超时调用
#             result = await asyncio.wait_for(
#                 llm_service.generate_structure(prompt),
#                 timeout=LLM_TIMEOUT
#             )
            
#             import re
#             json_match = re.search(r'\[.*\]', result, re.DOTALL)
#             if json_match:
#                 data = json.loads(json_match.group())
#                 summaries = []
#                 for item in data:
#                     summaries.append({
#                         "page_number": item.get("page", batch[0]["page_number"]),
#                         "summary": item.get("summary", ""),
#                         "key_topics": item.get("topics", [])
#                     })
#                 # 确保数量匹配
#                 while len(summaries) < len(batch):
#                     p = batch[len(summaries)]
#                     summaries.append({
#                         "page_number": p["page_number"],
#                         "summary": p["content"][:200] + "...",
#                         "key_topics": []
#                     })
#                 return summaries
#         except asyncio.TimeoutError:
#             logger.warning(f"Batch timeout after {LLM_TIMEOUT}s")
#         except Exception as e:
#             logger.warning(f"Batch summarize error: {e}")
        
#         # 失败时返回简单摘要
#         return [
#             {"page_number": p["page_number"], "summary": p["content"][:200] + "...", "key_topics": []}
#             for p in batch
#         ]
    
#     async def _build_tree(self, title: str, pages: List[dict], summaries: List[dict]) -> IndexNode:
#         """Build the hierarchical index tree using LLM analysis."""
        
#         # Create a summary of all summaries for LLM analysis
#         summary_text = "\n".join([
#             f"Page {s['page_number']}: {s['summary']} (Topics: {', '.join(s['key_topics'])})"
#             for s in summaries if s["summary"]
#         ])
        
#         if not summary_text:
#             # Fallback: create a simple single-level tree
#             root = IndexNode(title=title, page_start=1, page_end=len(pages), level=0)
#             for i, page in enumerate(pages):
#                 if page["content"]:
#                     child = IndexNode(
#                         title=f"Page {page['page_number']}",
#                         page_start=page["page_number"],
#                         page_end=page["page_number"],
#                         level=1,
#                         raw_content=page["content"][:500]
#                     )
#                     root.children.append(child)
#             return root
        
#         # Use LLM to analyze structure and build ToC
#         prompt = f"""Analyze this document and build a hierarchical table of contents structure.

# DOCUMENT TITLE: {title}
# TOTAL PAGES: {len(pages)}

# PAGE SUMMARIES:
# {summary_text[:8000]}

# Based on the page summaries, create a logical document structure. Identify:
# 1. Main sections (top level, level 1)
# 2. Subsections (level 2)
# 3. The page range each section covers

# Return a JSON tree structure. Each node should have:
# - title: section name
# - level: 0 for root, 1 for main sections, 2 for subsections
# - page_start: first page number
# - page_end: last page number

# Respond with JSON only:
# {{
#     "sections": [
#         {{
#             "title": "Section Name",
#             "level": 1,
#             "page_start": 1,
#             "page_end": 5,
#             "subsections": [
#                 {{"title": "Subsection", "level": 2, "page_start": 1, "page_end": 3}}
#             ]
#         }}
#     ]
# }}"""
        
#         try:
#             result = await asyncio.wait_for(
#                 llm_service.generate_structure(prompt),
#                 timeout=LLM_TIMEOUT
#             )
#             import re
#             json_match = re.search(r'\{.*\}', result, re.DOTALL)
            
#             if json_match:
#                 data = json.loads(json_match.group())
                
#                 # Build the tree from LLM output
#                 root = IndexNode(title=title, page_start=1, page_end=len(pages), level=0)
                
#                 for section in data.get("sections", []):
#                     section_node = IndexNode(
#                         title=section["title"],
#                         page_start=section.get("page_start", 1),
#                         page_end=section.get("page_end", len(pages)),
#                         level=section.get("level", 1)
#                     )
                    
#                     for subsection in section.get("subsections", []):
#                         sub_node = IndexNode(
#                             title=subsection["title"],
#                             page_start=subsection.get("page_start", section["page_start"]),
#                             page_end=subsection.get("page_end", section["page_end"]),
#                             level=subsection.get("level", 2)
#                         )
#                         section_node.children.append(sub_node)
                    
#                     root.children.append(section_node)
                
#                 return root
#             else:
#                 raise ValueError("Failed to parse LLM response")
                
#         except Exception as e:
#             # Fallback: create simple structure
#             root = IndexNode(title=title, page_start=1, page_end=len(pages), level=0)
#             for i, page in enumerate(pages):
#                 if page["content"]:
#                     child = IndexNode(
#                         title=f"Page {page['page_number']}",
#                         page_start=page["page_number"],
#                         page_end=page["page_number"],
#                         level=1,
#                         raw_content=page["content"][:1000]
#                     )
#                     root.children.append(child)
#             return root


# class PageRetriever:
#     """
#     PageIndex 检索器
    
#     核心思路：
#     1. 接收用户问题
#     2. 让 LLM "思考"需要检索什么，遍历索引树
#     3. 选择最相关的节点
#     4. 返回上下文片段
#     """
    
#     def __init__(self, index_tree: Optional[dict] = None, pages: Optional[List[dict]] = None):
#         self.index_tree = IndexNode.from_dict(index_tree) if index_tree else None
#         self.pages = pages or []
#         self._page_map = {p["page_number"]: p for p in self.pages}
    
#     def set_index(self, index_tree: dict, pages: List[dict]):
#         self.index_tree = IndexNode.from_dict(index_tree) if index_tree else None
#         self.pages = pages
#         self._page_map = {p["page_number"]: p for p in pages}
    
#     async def retrieve(self, query: str, top_k: int = 5) -> List[dict]:
#         """
#         Retrieve relevant content based on query using reasoning-based retrieval.
        
#         Instead of vector similarity, we use LLM to:
#         1. Analyze what information is needed
#         2. Traverse the index tree to find relevant sections
#         3. Extract content from relevant pages
#         """
#         if not self.index_tree:
#             return []
        
#         # Build context for LLM to reason about
#         tree_repr = self._tree_to_text(self.index_tree)
        
#         prompt = f"""You are analyzing a document index to find relevant sections for answering a user question.

# USER QUESTION: {query}

# DOCUMENT INDEX STRUCTURE:
# {tree_repr}

# Analyze which sections are most relevant to answer the user's question.
# Consider:
# 1. What information does the user need?
# 2. Which sections would contain this information?
# 3. What's the logical order of information?

# Return a JSON list of relevant page ranges, ordered by relevance:
# [
#     {{"page_start": 1, "page_end": 3, "reason": "Contains introduction and overview"}},
#     {{"page_start": 5, "page_end": 7, "reason": "Detailed technical specifications"}}
# ]

# Respond with JSON only, no other text."""

#         try:
#             result = await llm_service.generate_structure(prompt)
#             import re
#             json_match = re.search(r'\[.*\]', result, re.DOTALL)
            
#             if json_match:
#                 ranges = json.loads(json_match.group())
                
#                 results = []
#                 for r in ranges[:top_k]:
#                     ps = r.get("page_start", 1)
#                     pe = r.get("page_end", ps)
#                     reason = r.get("reason", "")
                    
#                     for pn in range(ps, pe + 1):
#                         if pn in self._page_map:
#                             page = self._page_map[pn]
#                             if page["content"]:
#                                 results.append({
#                                     "page": pn,
#                                     "content": page["content"],
#                                     "reason": reason,
#                                     "char_count": page["char_count"]
#                                 })
                
#                 return results
#             else:
#                 return self._fallback_retrieve(query, top_k)
                
#         except Exception:
#             return self._fallback_retrieve(query, top_k)
    
#     def _fallback_retrieve(self, query: str, top_k: int) -> List[dict]:
#         """Fallback: return content from all pages."""
#         results = []
#         for page in self.pages[:top_k]:
#             if page["content"]:
#                 results.append({
#                     "page": page["page_number"],
#                     "content": page["content"],
#                     "reason": "Content page",
#                     "char_count": page["char_count"]
#                 })
#         return results
    
#     def _tree_to_text(self, node: IndexNode, indent: int = 0) -> str:
#         """Convert tree to readable text representation."""
#         prefix = "  " * indent
#         text = f"{prefix}[L{node.level}] {node.title} (pages {node.page_start}-{node.page_end})\n"
#         for child in node.children:
#             text += self._tree_to_text(child, indent + 1)
#         return text


# page_indexer = PageIndexer()
