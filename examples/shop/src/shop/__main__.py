import os

from shop.main import run

os.environ.setdefault("SHOP_ENV", "dev")
run()
