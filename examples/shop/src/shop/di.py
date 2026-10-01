from libs.payments_client.client import PaymentsClient
from shop.settings.config import Settings

container = PaymentsClient(Settings().payments_url)
