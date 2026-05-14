import os

path = r"G:\openclaw\DocMind\backend\app\routers\chat.py"

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find line 148 which is "@router.get("/conversations/{conv_id}"
# Insert new route before it
new_route = """
@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    title = body.get("title", "New conversation")
    chat_type = body.get("chat_type", "general")
    document_id = body.get("document_id")

    conv = Conversation(
        id=str(uuid.uuid4()),
        title=title[:50] if len(title) > 50 else title,
        user_id=current_user.id,
        document_id=document_id,
        chat_type=chat_type
    )
    db.add(conv)
    await db.flush()

    return ConversationResponse(
        id=conv.id, title=conv.title, user_id=conv.user_id,
        chat_type=conv.chat_type, document_id=conv.document_id,
        messages=[],
        created_at=conv.created_at, updated_at=conv.updated_at
    )

"""

# Insert before the @router.get("/conversations/{conv_id}" line
for i, line in enumerate(lines):
    if '@router.get("/conversations/{conv_id}"' in line:
        lines.insert(i, new_route)
        break

with open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.writelines(lines)

print(f"Inserted route before line {i+1}")
