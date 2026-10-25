import pytest
import requests
from streamlit.testing.v1 import AppTest

from source.integrations import APIOlhoVivoClient


def snapshot(hr: str, *veiculos: tuple) -> dict:
    '''Monta um retorno de /Posicao com uma unica linha a partir de (p, ta, py, px).'''
    vs = [{'p': p, 'a': True, 'ta': ta, 'py': py, 'px': px, 'sv': None, 'is': None} for p, ta, py, px in veiculos]
    return {'hr': hr, 'l': [{'c': '5031-10', 'cl': 1746, 'sl': 1, 'lt0': 'TERM. SACOMÃ', 'lt1': 'VL. ARAPUÁ', 'qv': len(vs), 'vs': vs}]}


RAW_T0 = snapshot(
    '17:10',
    (1, '2026-10-25T20:10:00Z', -23.600, -46.600),
    (2, '2026-10-25T20:10:00Z', -23.610, -46.610),
)
RAW_T1 = snapshot(
    '17:10',
    (1, '2026-10-25T20:10:30Z', -23.601, -46.600), #andou ~111 m
    (2, '2026-10-25T20:10:30Z', -23.610, -46.610), #parado
    (3, '2026-10-25T20:10:30Z', -23.620, -46.620), #aparece so em t1
)


@pytest.fixture
def respostas(monkeypatch, tmp_path):
    '''Fila de retornos de /Posicao; um item que e excecao e levantado em vez de retornado.'''
    fila = []
    #o app grava o csv em dados/ relativo a pasta atual
    monkeypatch.chdir(tmp_path)

    def posicao_atual_onibus(self):
        resposta = fila.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setenv(APIOlhoVivoClient.ENV_TOKEN, 'token-fake')
    monkeypatch.setattr(APIOlhoVivoClient, 'autenticar', lambda self: None)
    monkeypatch.setattr(APIOlhoVivoClient, 'posicao_atual_onibus', posicao_atual_onibus)
    return fila


@pytest.fixture
def tokens(monkeypatch):
    '''Tokens com que o client foi criado.'''
    usados = []
    init_original = APIOlhoVivoClient.__init__

    def init(self, token=None):
        init_original(self, token)
        usados.append(self.token)

    monkeypatch.setattr(APIOlhoVivoClient, '__init__', init)
    return usados


@pytest.fixture
def sem_dotenv(monkeypatch):
    '''Simula a ausencia do .env (sem isso o app acharia o .env real do projeto).'''
    monkeypatch.delenv(APIOlhoVivoClient.ENV_TOKEN)
    monkeypatch.setattr('dotenv.load_dotenv', lambda *args, **kwargs: False)


def proxima_leitura(app: AppTest) -> None:
    '''Simula que ja passou o intervalo do loop e reroda.'''
    app.session_state['ultima_coleta'] = float('-inf')
    app.run()


def metricas(app: AppTest) -> dict:
    return {metrica.label: metrica.value for metrica in app.metric}


def test_primeira_carga_mostra_frota_e_aguarda_comparacao(respostas):
    respostas.append(RAW_T0)
    app = AppTest.from_file('../../app.py').run()

    assert not app.exception
    assert metricas(app)['Ônibus circulando'] == '2'
    assert 'Parados' not in metricas(app)
    assert 'primeira comparação' in app.info[0].value


def test_rerun_antes_do_intervalo_nao_chama_a_api(respostas):
    respostas.append(RAW_T0)
    app = AppTest.from_file('../../app.py').run()
    #fila vazia: se o rerun chamasse a api, o pop levantaria IndexError
    app.run()

    assert not app.exception


def test_loop_compara_leituras(respostas):
    respostas.extend([RAW_T0, RAW_T1])
    app = AppTest.from_file('../../app.py').run()
    proxima_leitura(app)

    assert not app.exception
    valores = metricas(app)
    assert valores['Ônibus circulando'] == '3'
    assert (valores['Parados'], valores['Em movimento'], valores['Sem posição nova']) == ('1', '1', '0')
    assert valores['% parados'] == '50,0%'


def test_loop_grava_csv_para_download(respostas, tmp_path):
    respostas.extend([RAW_T0, RAW_T1])
    app = AppTest.from_file('../../app.py').run()
    assert len(app.download_button) == 0

    proxima_leitura(app)

    assert not app.exception
    arquivo, = (tmp_path / 'dados').glob('movimento_*.csv')
    assert len(arquivo.read_text().splitlines()) == 3 #cabecalho + os 2 onibus das duas leituras
    assert app.download_button[0].label == 'Baixar CSV'


def test_explicacao_usa_a_distancia_configurada(respostas):
    respostas.append(RAW_T0)
    app = AppTest.from_file('../../app.py').run()
    app.slider[1].set_value(50).run()

    assert not app.exception
    assert 'Menos de **50 m**' in app.expander[0].markdown[0].value


def test_falha_na_leitura_mantem_os_dados_anteriores(respostas):
    respostas.extend([RAW_T0, RAW_T1, requests.ConnectionError('sem rede')])
    app = AppTest.from_file('../../app.py').run()
    proxima_leitura(app)
    proxima_leitura(app)

    assert not app.exception
    assert 'sem rede' in app.warning[0].value
    assert metricas(app)['Parados'] == '1'


def test_loop_pausado_nao_chama_a_api(respostas):
    respostas.append(RAW_T0)
    app = AppTest.from_file('../../app.py').run()
    app.toggle[0].set_value(False).run()
    proxima_leitura(app)

    assert not app.exception
    assert 'pausada' in app.caption[0].value


def test_token_do_env_tem_prioridade_sobre_os_secrets(respostas, tokens):
    respostas.append(RAW_T0)
    app = AppTest.from_file('../../app.py')
    app.secrets[APIOlhoVivoClient.ENV_TOKEN] = 'token-secrets'
    app.run()

    assert not app.exception
    assert tokens == ['token-fake']


def test_sem_env_usa_o_token_dos_secrets(respostas, tokens, sem_dotenv):
    respostas.append(RAW_T0)
    app = AppTest.from_file('../../app.py')
    app.secrets[APIOlhoVivoClient.ENV_TOKEN] = 'token-secrets'
    app.run()

    assert not app.exception
    assert tokens == ['token-secrets']
    assert metricas(app)['Ônibus circulando'] == '2'


def test_sem_token_mostra_erro(respostas, sem_dotenv):
    app = AppTest.from_file('../../app.py').run()

    assert not app.exception
    assert 'Token não encontrado' in app.error[0].value
