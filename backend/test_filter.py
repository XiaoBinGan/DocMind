"""Test _filter_think_tokens behavior with markdown content."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
from app.services.llm import _filter_think_tokens

# Test 1: Normal markdown chunk
test1 = '### Python\n```python\nprint("Hello")\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |'
result1 = _filter_think_tokens(test1)
print('=== Test 1: Normal markdown ===')
print('INPUT :', repr(test1))
print('OUTPUT:', repr(result1))
print('PRESERVED?', test1 == result1)

# Test 2: Leading/trailing whitespace (CRITICAL: .strip() test)
test2 = '\n\n  hello  \n\n'
result2 = _filter_think_tokens(test2)
print('\n=== Test 2: Leading/trailing whitespace ===')
print('INPUT :', repr(test2))
print('OUTPUT:', repr(result2))
print('STRIPPED?', test2 != result2)

# Test 3: Newline-only chunk (streaming common)
test3 = '\n'
result3 = _filter_think_tokens(test3)
print('\n=== Test 3: Newline-only chunk ===')
print('INPUT :', repr(test3))
print('OUTPUT:', repr(result3))
print('NEWLINE PRESERVED?', test3 == result3)

# Test 4: Chunk with content + trailing newline
test4 = 'print("hello")\n'
result4 = _filter_think_tokens(test4)
print('\n=== Test 4: Code line with trailing newline ===')
print('INPUT :', repr(test4))
print('OUTPUT:', repr(result4))
print('SAME?', test4 == result4)

# Test 5: Think tags (should be removed)
test5 = '<think>reasoning here</think>\n```python\nprint("hi")\n```'
result5 = _filter_think_tokens(test5)
print('\n=== Test 5: With think tags ===')
print('INPUT :', repr(test5))
print('OUTPUT:', repr(result5))

# Test 6: Empty string
test6 = ''
result6 = _filter_think_tokens(test6)
print('\n=== Test 6: Empty string ===')
print('INPUT :', repr(test6))
print('OUTPUT:', repr(result6))
print('EMPTY?', result6 == '')
