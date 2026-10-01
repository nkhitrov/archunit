from shop.api.routes import router
from shop.di import container


def run() -> None:
    container.start(router)
