import pandas as pd

from .parser import parse_veiculos


class PosicoesOnibus:
    '''Posicao atual de cada onibus, a partir do retorno bruto de /Posicao.'''

    COLUNAS = ['prefixo', 'letreiro', 'latitude', 'longitude']

    def __init__(self, raw: dict):

        self.hora_referencia: str = raw['hr']
        self.dados: pd.DataFrame = parse_veiculos(raw)[self.COLUNAS]
