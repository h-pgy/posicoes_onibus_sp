import pytest

from source.integrations import APIOlhoVivoClient


class RequestFake:

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = 0

    def get(self, endpoint, params=None, as_json=True):
        self.chamadas += 1
        return self.respostas.pop(0)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(APIOlhoVivoClient, 'ESPERA_ENTRE_TENTATIVAS', 0)
    client = APIOlhoVivoClient(token='token-fake')
    client.autenticado = True
    return client


def test_tenta_de_novo_quando_api_retorna_null(client):
    client.request = RequestFake(None, {'hr': '17:11', 'l': []})

    assert client.posicao_atual_onibus() == {'hr': '17:11', 'l': []}
    assert client.request.chamadas == 2


def test_desiste_depois_de_todas_as_tentativas(client):
    client.request = RequestFake(None, None, None)

    with pytest.raises(RuntimeError, match='3 tentativas'):
        client.posicao_atual_onibus()
