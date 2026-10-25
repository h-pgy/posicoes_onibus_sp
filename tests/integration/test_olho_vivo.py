import os
import re
from datetime import datetime

import pytest
from dotenv import load_dotenv

from source.integrations import APIOlhoVivoClient

load_dotenv()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv(APIOlhoVivoClient.ENV_TOKEN), reason='token da API nao configurado no .env'),
]

CAMPOS_LINHA = {'c': str, 'cl': int, 'sl': int, 'lt0': str, 'lt1': str, 'qv': int, 'vs': list}
CAMPOS_VEICULO = {'p': int, 'a': bool, 'ta': str, 'py': float, 'px': float}


@pytest.fixture(scope='module')
def client():
    return APIOlhoVivoClient()


@pytest.fixture(scope='module')
def posicoes(client):
    #uma unica chamada para todos os testes do modulo
    return client.posicao_atual_onibus()


def test_autentica_na_primeira_chamada(client, posicoes):
    assert client.autenticado


def test_token_invalido_falha():
    with pytest.raises(RuntimeError, match='Falha ao autenticar'):
        APIOlhoVivoClient(token='token-invalido').autenticar()


def test_formato_topo(posicoes):
    assert set(posicoes) == {'hr', 'l'}
    assert re.fullmatch(r'\d{2}:\d{2}', posicoes['hr'])
    assert len(posicoes['l']) > 0


def test_formato_linhas(posicoes):
    for linha in posicoes['l']:
        for campo, tipo in CAMPOS_LINHA.items():
            assert isinstance(linha[campo], tipo), (campo, linha)
        assert linha['sl'] in (1, 2)
        assert linha['qv'] == len(linha['vs'])


def test_formato_veiculos(posicoes):
    veiculos = [v for linha in posicoes['l'] for v in linha['vs']]
    assert len(veiculos) > 0
    for veiculo in veiculos:
        for campo, tipo in CAMPOS_VEICULO.items():
            assert isinstance(veiculo[campo], tipo), (campo, veiculo)
        datetime.fromisoformat(veiculo['ta'])
