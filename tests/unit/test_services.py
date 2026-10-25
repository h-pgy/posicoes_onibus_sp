import pytest

from source.services import MetricasFrota, PosicoesOnibus


def veiculo(p: int, a: bool, ta: str) -> dict:
    return {'p': p, 'a': a, 'ta': ta, 'py': -23.6, 'px': -46.6, 'sv': None, 'is': None}


#mesmo formato do retorno de /Posicao: a linha 5031-10 aparece nos dois sentidos
RAW = {
    'hr': '17:11',
    'l': [
        {'c': '5031-10', 'cl': 1746, 'sl': 1, 'lt0': 'TERM. SACOMÃ', 'lt1': 'VL. ARAPUÁ', 'qv': 2, 'vs': [
            veiculo(55351, True, '2026-10-25T20:11:40Z'),
            veiculo(55505, False, '2026-10-25T20:11:00Z'),
        ]},
        {'c': '5031-10', 'cl': 34514, 'sl': 2, 'lt0': 'TERM. SACOMÃ', 'lt1': 'VL. ARAPUÁ', 'qv': 1, 'vs': [
            veiculo(55400, True, '2026-10-25T20:01:40Z'), #10 min atrasado
        ]},
        {'c': '8010-10', 'cl': 798, 'sl': 1, 'lt0': 'LAPA', 'lt1': 'PERUS', 'qv': 1, 'vs': [
            veiculo(11000, True, '2026-10-25T20:11:40Z'),
        ]},
    ],
}

RAW_VAZIO = {'hr': '03:00', 'l': []}


def test_posicoes_tem_so_as_colunas_de_posicao():
    posicoes = PosicoesOnibus(RAW)

    assert posicoes.hora_referencia == '17:11'
    assert list(posicoes.dados.columns) == ['prefixo', 'letreiro', 'latitude', 'longitude']
    assert posicoes.dados['prefixo'].tolist() == ['55351', '55505', '55400', '11000']
    assert posicoes.dados['letreiro'].tolist() == ['5031-10', '5031-10', '5031-10', '8010-10']


def test_metricas_totais():
    metricas = MetricasFrota(RAW)

    assert metricas.total_veiculos == 4
    assert metricas.total_linhas == 2
    assert metricas.media_veiculos_por_linha == 2.0


def test_veiculos_por_linha_soma_os_dois_sentidos():
    por_linha = MetricasFrota(RAW).veiculos_por_linha

    assert por_linha.to_dict('records') == [
        {'letreiro': '5031-10', 'origem': 'VL. ARAPUÁ', 'destino': 'TERM. SACOMÃ', 'veiculos': 3},
        {'letreiro': '8010-10', 'origem': 'PERUS', 'destino': 'LAPA', 'veiculos': 1},
    ]


def test_acessibilidade():
    metricas = MetricasFrota(RAW)

    assert metricas.veiculos_acessiveis == 3
    assert metricas.percentual_acessiveis == 75.0


def test_atraso_relativo_a_captura_mais_recente():
    metricas = MetricasFrota(RAW)

    assert metricas.atraso_minutos.tolist() == pytest.approx([0, 40 / 60, 10, 0])
    assert metricas.veiculos_desatualizados == 1


def test_metricas_sem_veiculos():
    metricas = MetricasFrota(RAW_VAZIO)

    assert metricas.total_veiculos == 0
    assert metricas.total_linhas == 0
    assert metricas.media_veiculos_por_linha == 0.0
    assert metricas.percentual_acessiveis == 0.0
    assert metricas.veiculos_desatualizados == 0
    assert metricas.veiculos_por_linha.empty
    assert PosicoesOnibus(RAW_VAZIO).dados.empty
