import httpx
from synapse.api.auth import create_access_token

token = create_access_token({"sub": "123", "role": "admin"})
res = httpx.get("http://localhost:8000/api/admin/rules/taxonomy", headers={"Authorization": f"Bearer {token}"})
print(res.status_code)
print(res.json())
