"""Script to replace _normalize_markdown in llm.py"""
import re as _re

filepath = r'G:\openclaw\DocMind\backend\app\services\llm.py'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = 'def _normalize_markdown(text: str) -> str:'
start = content.find(start_marker)
if start == -1:
    print("ERROR: start marker not found")
    exit(1)

rest = content[start:]
lines = rest.split('\n')
end_line_idx = None
for i, line in enumerate(lines):
    if i > 0 and line and line[0] not in (' ', '\t', '#'):
        end_line_idx = i
        break

if end_line_idx is None:
    print("ERROR: end not found")
    exit(1)

end_idx = start + sum(len(l) + 1 for l in lines[:end_line_idx])
old_func = content[start:end_idx]
print(f"Found function at {start}-{end_idx}")

new_func = '''def _normalize_markdown(text: str) -> str:
    """将单行 markdown 恢复为多行格式，使 react-markdown 能正确解析。"""
    if not text or "\\n" in text:
        return text

    import re
    
    # 1. 代码块前后插入换行
    text = re.sub(r'(?<=[^\\n])`{3}|`{3}(?=[^\\n])', lambda m: '\\n```' if m.start() == 0 or text[m.start()-1] != '\\n' else '```\\n', text)
    text = re.sub(r'`{3}', '\\n```\\n', text)
    
    # 2. 标题前后（# ## ###）
    text = re.sub(r'(?<=[^\\n])(#{1,6})\\s', r'\\n\\1 ', text)
    
    # 3. 分割线前后（---、***、___）
    text = re.sub(r'(?<=[^\\n])([-*_])\\1\\1(?=[^\\n])', r'\\n\\1\\1\\1\\n', text)
    
    # 4. 列表项（-、*、+ 开头）
    text = re.sub(r'(?<=[^\\n])\\s*[-*+]\\s', r'\\n- ', text)
    
    # 5. 有序列表（1. 2. 等）
    text = re.sub(r'(?<=[^\\n])\\s*\\d+\\.\\s', r'\\n1. ', text)
    
    # 6. 加粗/斜体前后（**text** 或 *text*）
    text = re.sub(r'(?<=[^\\n])\\*\\*', r'\\n**', text)
    
    # 7. 引用（> text）
    text = re.sub(r'(?<=[^\\n])\\s>', r'\\n>', text)
    
    # 8. 清理多余空行
    text = re.sub(r'\\n{3,}', '\\n\\n', text)
    
    return text.strip()
'''

if old_func == new_func:
    print("No changes needed")
    exit(0)

content = content[:start] + new_func + content[end_idx:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("File updated successfully")

# Verify
with open(filepath, 'r', encoding='utf-8') as f:
    verify = f.read()
start2 = verify.find('def _normalize_markdown')
rest2 = verify[start2:]
lines2 = rest2.split('\n')
for i, l2 in enumerate(lines2):
    if i > 0 and l2 and l2[0] not in (' ', '\t', '#'):
        print(f"End at line {i}: {repr(l2[:40])}")
        break
