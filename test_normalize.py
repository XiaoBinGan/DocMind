"""Test script for DocMind chat_stream full_content changes."""
import re

def _normalize_markdown(text: str) -> str:
    """修复压缩/无换行的 markdown 文本，使其可被 react-markdown 正确解析。"""
    if not text:
        return text

    code_blocks: list[str] = []

    def _save_code_block(m: re.Match) -> str:
        idx = len(code_blocks)
        code_blocks.append(m.group(0))
        return f"\n\n__CODE_BLOCK_{idx}__\n\n"

    text = re.sub(r'`{3}(\w*)\n([\s\S]*?)```', _save_code_block, text)

    def _fix_inline_code_block(m: re.Match) -> str:
        lang = m.group(1) or ""
        code = m.group(2).strip()
        formatted = f"```{lang}\n{code}\n```"
        idx = len(code_blocks)
        code_blocks.append(formatted)
        return f"\n\n__CODE_BLOCK_{idx}__\n\n"

    text = re.sub(r'`{3}(\w*)\s((?:(?!```).)+?)```', _fix_inline_code_block, text)

    text = re.sub(r'(?<=[^\n#])(#{1,6})\s+', r'\n\n\1 ', text)

    if '||' in text:
        text = re.sub(r'\|\|', '|\n|', text)

    text = re.sub(r'(?<=[^\n\-\*\+\s])\s*([-*+])\s', r'\n\n\1 ', text)
    text = re.sub(r'(?<=\S)\s+([-*+])\s+', r'\n\1 ', text)
    text = re.sub(r'(?<=[^\n\d\s])\s*(\d+)\.\s', r'\n\n\1. ', text)

    text = re.sub(r'\*\*\s+', '**', text)
    text = re.sub(r'\s+\*\*', '**', text)

    paragraph_starters = r'(?:这|所|以|其|如|但|然|因|第|最|另|同|为|在|从|对|该|每|任|全|总|现|目|接|下面|上面|综|整|需|请|注|提|具|包|根|通|使|可|不|已|未|将|应|若|除|当|此|由|于|于|关|于)'
    text = re.sub(r'。\s*(' + paragraph_starters + r')', r'。\n\n\1', text)

    for i, block in enumerate(code_blocks):
        text = text.replace(f'__CODE_BLOCK_{i}__', block)

    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ====== 测试用例 ======

tests = [
    ("无换行：标题+段落",
     "# 测试文档这是一段文字段落这是第一段第二段。这也是一个段落。"),

    ("无换行：含代码块",
     "# 代码示例```python\ndef hello():\n  print('world')\n```\n这是一段代码后面的文字。"),

    ("无换行：含表格",
     "# 表格数据| 列A | 列B || --- | --- || 1 | 2 || 3 | 4 |"),

    ("无换行：含列表",
     "# 列表项- 第一项- 第二项- 第三项1. 有序第一项2. 有序第二项"),

    ("有换行：轻量修复",
     "# 标题\n\n这是一段有换行的文字。\n- 列表项\n```python\nprint('hello')\n```"),
]

print("=" * 60)
print("  _normalize_markdown 修复演示")
print("=" * 60)

for name, input_text in tests:
    print(f"\n--- {name} ---")
    print(f"输入 (repr):\n{repr(input_text)}")
    result = _normalize_markdown(input_text)
    print(f"\n输出:\n{result}")
    print(f"\n包含换行数: {result.count(chr(10))}")

print("\n" + "=" * 60)
