from typing import TYPE_CHECKING

from shop.features.core.billing.events import InvoicePaid
from shop.features.core.catalog.products import PRICES

if TYPE_CHECKING:
    from shop.features.support.notifications.sender import notify


class PlaceOrder:
    def __call__(self) -> object:
        from shop.features.generic.users.models import User

        return InvoicePaid, PRICES, User
