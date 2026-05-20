import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from app.main import app
routes = [(r.path, r.methods) for r in app.routes]
api_cat = [r for r in routes if '/api-catalog' in r[0]]
for path, methods in sorted(api_cat, key=lambda x: x[0]):
    print(f'{methods} {path}')
