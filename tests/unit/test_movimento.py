import pytest

from source.services import MonitorMovimento, MovimentoFrota


def snapshot(hr: str, *veiculos: tuple) -> dict:
    '''Monta um retorno de /Posicao com uma unica linha a partir de (p, ta, py, px).'''
    vs = [{'p': p, 'a': True, 'ta': ta, 'py': py, 'px': px, 'sv': None, 'is': None} for p, ta, py, px in veiculos]
    return {'hr': hr, 'l': [{'c': '5031-10', 'cl': 1746, 'sl': 1, 'lt0': 'TERM. SACOMÃ', 'lt1': 'VL. ARAPUÁ', 'qv': len(vs), 'vs': vs}]}


#0.001 grau de latitude ~ 111 m
RAW_T0 = snapshot(
    '17:10',
    (1, '2026-10-25T20:10:00Z', -23.600, -46.600),
    (2, '2026-10-25T20:10:00Z', -23.610, -46.610),
    (3, '2026-10-25T20:10:00Z', -23.620, -46.620),
    (4, '2026-10-25T20:10:00Z', -23.630, -46.630), #some em t1
)
RAW_T1 = snapshot(
    '17:11',
    (1, '2026-10-25T20:10:30Z', -23.601, -46.600), #andou ~111 m
    (2, '2026-10-25T20:10:30Z', -23.610, -46.610), #posicao nova, mesmo lugar
    (3, '2026-10-25T20:10:00Z', -23.620, -46.620), #nao mandou posicao nova
    (5, '2026-10-25T20:10:30Z', -23.640, -46.640), #aparece so em t1
)
RAW_T2 = snapshot(
    '17:12',
    (1, '2026-10-25T20:11:00Z', -23.601, -46.600), #agora parou
)


class ClientFake:

    def __init__(self, *respostas: dict):
        self.respostas = list(respostas)

    def posicao_atual_onibus(self) -> dict:
        return self.respostas.pop(0)


def test_situacao_de_cada_veiculo():
    movimento = MovimentoFrota(RAW_T0, RAW_T1)

    situacoes = dict(zip(movimento.veiculos['prefixo'], movimento.veiculos['situacao']))
    assert situacoes == {'1': 'em movimento', '2': 'parado', '3': 'sem atualizacao'}
    assert movimento.veiculos.set_index('prefixo').loc['1', 'distancia_m'] == pytest.approx(111, abs=1)


def test_contagens_e_percentual_ignoram_sem_atualizacao():
    movimento = MovimentoFrota(RAW_T0, RAW_T1)

    assert (movimento.parados, movimento.em_movimento, movimento.sem_atualizacao) == (1, 1, 1)
    assert movimento.percentual_parados == 50.0


def test_distancia_parado_configuravel():
    movimento = MovimentoFrota(RAW_T0, RAW_T1, distancia_parado=200)

    assert movimento.parados == 2
    assert movimento.em_movimento == 0


def test_sem_veiculos_em_comum():
    movimento = MovimentoFrota(RAW_T0, snapshot('17:11'))

    assert movimento.veiculos.empty
    assert movimento.percentual_parados == 0.0


def test_monitor_avanca_o_t0_a_cada_comparacao():
    monitor = MonitorMovimento(ClientFake(RAW_T1, RAW_T2), RAW_T0)

    primeira = monitor.comparar()
    assert primeira.em_movimento == 1
    assert monitor.ultimo_raw is RAW_T1

    #a segunda comparacao e entre t1 e t2, nao entre t0 e t2
    segunda = monitor.comparar()
    assert (segunda.parados, segunda.em_movimento) == (1, 0)
    assert monitor.ultimo_raw is RAW_T2
