import requests


class RequestMaker:

    def __init__(self, method: str, host: str, version: str, timeout: float = 10):

        self.base_url = f'{method}://{host}/v{version}'
        self.timeout = timeout
        #a api guarda a autenticacao num cookie, entao todas as requisicoes precisam usar a mesma sessao
        self.session = requests.Session()

    def build_url(self, endpoint: str) -> str:

        return f'{self.base_url}/{endpoint}'

    def _request(self, verb: str, endpoint: str, params: dict | None = None, as_json: bool = True):

        resp = self.session.request(verb, self.build_url(endpoint), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json() if as_json else resp.text

    def get(self, endpoint: str, params: dict | None = None, as_json: bool = True):

        return self._request('GET', endpoint, params, as_json)

    def post(self, endpoint: str, params: dict | None = None, as_json: bool = True):

        return self._request('POST', endpoint, params, as_json)
