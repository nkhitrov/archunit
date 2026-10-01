from shop.features.core.orders.use_cases import PlaceOrder
from shop.shared.money import Money

router = {"/orders": PlaceOrder, "money": Money}
