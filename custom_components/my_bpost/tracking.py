"""Independent manually tracked parcel using the shared HA parcel lifecycle."""

from datetime import timedelta

from homeassistant.util import dt as dt_util

from .coordinator import BpostData, BpostDataUpdateCoordinator, parcel_status
from .pybpost.models import ParcelSummary
from .pybpost.status import ParcelStatus


class PublicTrackingCoordinator(BpostDataUpdateCoordinator):
    async def _async_fetch_data(self) -> BpostData:
        entry = self.config_entry
        code = entry.data["barcode"]
        detail = await self.client.get_parcel(code, entry.options.get("postal_code", entry.data["postal_code"]))
        detail.title = entry.options.get("label", entry.data.get("label"))
        detail.user_type = {"incoming": "RECEIVER", "outgoing": "SENDER"}.get(entry.options.get("direction", entry.data.get("direction","unknown")))
        data = BpostData(summaries={code: ParcelSummary(code, detail.current_status)},
                         details={code: detail}, last_fetch=dt_util.utcnow())
        if parcel_status(code, data) not in (ParcelStatus.DELIVERED, ParcelStatus.RETURNED):
            data.active_codes.add(code)
        result = await self._async_finish_fetch(data)
        # Public tracking doesn't expose a courier round. Avoid aggressive
        # polling per manually added entry; users may track several parcels.
        self.update_interval = timedelta(minutes=15 if data.active_codes else 60)
        return result
