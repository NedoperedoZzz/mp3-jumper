import os
import uuid

import httpx

tok = httpx.post(
    "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
    headers={
        "Authorization": f"Basic {os.environ['GIGACHAT_AUTH_KEY']}",
        "RqUID": str(uuid.uuid4()),
    },
    data={"scope": "GIGACHAT_API_PERS"},
    verify=False,
    timeout=30,
).json()["access_token"]
models = httpx.get(
    "https://gigachat.devices.sberbank.ru/api/v1/models",
    headers={"Authorization": f"Bearer {tok}"},
    verify=False,
    timeout=30,
).json()["data"]
print("\n".join(m["id"] for m in models))
