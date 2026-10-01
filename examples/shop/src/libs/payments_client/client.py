from decimal import Decimal

from libs.http.client import HttpClient


class PaymentsClient(HttpClient):
    def charge(self, amount: Decimal) -> object:
        return self.post(f"/charge/{amount}")

    def start(self, router: object) -> None:
        print(router)
