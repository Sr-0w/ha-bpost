# pybpost (WIP)

Async Python client for the My bpost account API (unofficial,
reverse-engineered from the official Android app 3.45.1).

```python
import asyncio
from pybpost import BpostClient

async def main():
    client = BpostClient(app_lang="fr", api_key="<X_API_KEY>",
                         email="you@example.com", password="...")
    try:
        await client.login()
        for parcel in await client.get_parcels_list():
            print(parcel.item_code, parcel.status)
        active, history = await client.get_parcels_details(await client.get_parcels_list())
        print(len(active), "active,", len(history), "history")
    finally:
        await client.close()

asyncio.run(main())
```

See the parent README for the `x-api-key` situation and the full report.
