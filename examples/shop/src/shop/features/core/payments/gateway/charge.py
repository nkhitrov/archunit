from decimal import Decimal

from libs.payments_client.client import PaymentsClient


def charge(amount: Decimal) -> None:
    PaymentsClient("http://payments").charge(amount)
