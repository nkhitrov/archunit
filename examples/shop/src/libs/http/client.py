import urllib.request


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def post(self, path: str) -> object:
        return urllib.request.Request(self.base_url + path)
