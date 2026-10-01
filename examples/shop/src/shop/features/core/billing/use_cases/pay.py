from dataclasses import dataclass

from shop.features.core.billing.domain.invoice import Invoice
from shop.features.core.payments.gateway.charge import charge


@dataclass
class PayInvoice:
    invoice: Invoice

    def __call__(self) -> None:
        charge(self.invoice.total)
