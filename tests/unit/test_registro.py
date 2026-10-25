import pandas as pd

from source.services import MovimentoFrota, RegistroCSV
from tests.unit.test_movimento import RAW_T0, RAW_T1, RAW_T2, snapshot

LEITURA_T1 = pd.Timestamp('2026-10-25T20:10:30Z')
LEITURA_T2 = pd.Timestamp('2026-10-25T20:11:00Z')


def test_grava_uma_linha_por_onibus_comparado(tmp_path):
    registro = RegistroCSV(tmp_path / 'movimento.csv')
    registro.registrar(MovimentoFrota(RAW_T0, RAW_T1), LEITURA_T1)

    dados = pd.read_csv(registro.caminho, dtype={'prefixo': str})
    assert list(dados.columns) == RegistroCSV.COLUNAS
    assert dict(zip(dados['prefixo'], dados['situacao'])) == {'1': 'em movimento', '2': 'parado', '3': 'sem atualizacao'}
    assert dados.loc[0, 'distancia_m'] == 111.2
    #horario de brasilia com offset
    assert dados.loc[0, 'leitura'] == '2026-10-25 17:10:30-03:00'
    assert dados['atualizado_em'].tolist() == [
        '2026-10-25 17:10:30-03:00', '2026-10-25 17:10:30-03:00', '2026-10-25 17:10:00-03:00',
    ]


def test_acumula_comparacoes_com_um_unico_cabecalho(tmp_path):
    registro = RegistroCSV(tmp_path / 'dados' / 'movimento.csv')
    registro.registrar(MovimentoFrota(RAW_T0, RAW_T1), LEITURA_T1)
    registro.registrar(MovimentoFrota(RAW_T1, RAW_T2), LEITURA_T2)

    dados = pd.read_csv(registro.caminho)
    assert len(dados) == 4
    assert dados['leitura'].value_counts().to_dict() == {'2026-10-25 17:10:30-03:00': 3, '2026-10-25 17:11:00-03:00': 1}
    assert (registro.leituras, registro.linhas) == (2, 4)
    assert registro.ler().count(b'leitura,') == 1


def test_comparacao_vazia_nao_cria_arquivo(tmp_path):
    registro = RegistroCSV(tmp_path / 'movimento.csv')
    registro.registrar(MovimentoFrota(RAW_T0, snapshot('17:11')), LEITURA_T1)

    assert not registro.caminho.exists()
    assert registro.leituras == 0
