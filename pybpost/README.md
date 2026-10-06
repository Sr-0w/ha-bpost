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

After login, persist `client.tokens` in your application's secure credential
storage. Restore it with `BpostClient(tokens=saved_tokens,
on_tokens_updated=save_tokens)`, where `save_tokens` is an async callback that
persists every rotated token pair. Credentials passed to the constructor are
consumed by the first login and are not retained for automatic re-login.
Handle `BpostAuthError` by asking the user to sign in again; handle other
`BpostError` subclasses as service or protocol failures. Never log tokens.

See the [client-key documentation](../docs/development.md#about-the-client-key)
and [validation report](../docs/distribution-validation.md).

Mail Ahead: inspect `mail_capability(await client.get_mail_summary())` before
calling `get_letters(from_date, to_date)` with `datetime.date` values (at most
31 inclusive days). Returned `MailItem` models expose an opaque stable `key`.
Their image URLs are private signed links: never log, publish or persist them.
`get_mail_image(url)` returns `(bytes, content_type)` using a separate session
without account headers/cookies, with HTTPS host/type/size constraints and no
redirects. Call `close()` even when using a caller-owned account session so that
the client's image session is also closed. The caller-owned session remains open.
# Public tracking

`pybpost.tracking.PublicTrackingClient` tracks a parcel without an account using
`await client.get_parcel(barcode, delivery_postal_code)`. Close it with
`await client.close()` when finished. It owns a cookie-free session and sends no
account credentials or client key. Enable `trust_env=True` only when using the
environment's normal proxy configuration.

`BpostTrackingNotFound` means a successful lookup returned no items; transport,
protocol and rate-limit failures remain separate errors. Responses are bounded,
redirects are refused and `Retry-After` delays gate subsequent calls. The returned
`ParcelDetail` includes conservative canonical status and supplied public fields,
without retaining the raw response or receiver data.
