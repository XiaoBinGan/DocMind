import sys
sys.path.insert(0, '.')
from app.routers.chat import router
for r in router.routes:
    methods = list(r.methods) if r.methods else ['GET']
    print(str(methods) + ' ' + r.path)
