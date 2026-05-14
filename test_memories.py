import sys, json
sys.path.insert(0, r"G:\openclaw\DocMind\backend")

# Try importing the router to see if there's an import error
try:
    from app.routers import memories
    print("memories router imported OK")
    for r in memories.router.routes:
        methods = list(r.methods) if r.methods else ["GET"]
        print(f"  {methods} {r.path}")
except Exception as e:
    import traceback
    traceback.print_exc()
