from datetime import timedelta

import pandas as pd

from .parser import parse_veiculos


class MetricasFrota:
    '''Metricas agregadas da frota, a partir do retorno bruto de /Posicao.'''

    def __init__(self, raw: dict, limite_atraso: timedelta = timedelta(minutes=5)):

        self.hora_referencia: str = raw['hr']
        self.limite_atraso = limite_atraso
        self.veiculos = parse_veiculos(raw)
        #a referencia e a captura mais recente, para nao depender do relogio de quem roda
        self.atualizado_em = self.veiculos['atualizado_em'].max()
        self.veiculos['atraso'] = self.atualizado_em - self.veiculos['atualizado_em']

    @property
    def total_veiculos(self) -> int:

        return len(self.veiculos)

    @property
    def total_linhas(self) -> int:

        #cada sentido vem como uma entrada separada na api, entao contamos letreiros distintos
        return self.veiculos['letreiro'].nunique()

    @property
    def media_veiculos_por_linha(self) -> float:

        if not self.total_linhas:
            return 0.0
        return self.total_veiculos / self.total_linhas

    @property
    def veiculos_por_linha(self) -> pd.DataFrame:
        '''Quantidade de veiculos por letreiro (somando os dois sentidos), do maior para o menor.'''

        return (
            self.veiculos
            .groupby('letreiro', as_index=False)
            .agg(origem=('origem', 'first'), destino=('destino', 'first'), veiculos=('prefixo', 'count'))
            .sort_values(['veiculos', 'letreiro'], ascending=[False, True], ignore_index=True)
        )

    @property
    def veiculos_acessiveis(self) -> int:

        return int(self.veiculos['acessivel'].sum())

    @property
    def percentual_acessiveis(self) -> float:

        if not self.total_veiculos:
            return 0.0
        return 100 * self.veiculos_acessiveis / self.total_veiculos

    @property
    def atraso_minutos(self) -> pd.Series:
        '''Ha quantos minutos cada posicao foi capturada, em relacao a captura mais recente.'''

        return self.veiculos['atraso'].dt.total_seconds() / 60

    @property
    def veiculos_desatualizados(self) -> int:
        '''Veiculos cuja ultima posicao tem atraso maior que o limite.'''

        return int((self.veiculos['atraso'] > self.limite_atraso).sum())
