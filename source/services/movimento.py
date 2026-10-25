import numpy as np
import pandas as pd

from ..integrations import APIOlhoVivoClient
from .parser import parse_veiculos

RAIO_TERRA_M = 6_371_000


def distancia_metros(lat1, lon1, lat2, lon2):
    '''Distancia em metros entre pares de pontos (formula de haversine), vetorizada.'''

    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * RAIO_TERRA_M * np.arcsin(np.sqrt(h))


class MovimentoFrota:
    '''Compara dois retornos brutos de /Posicao (t0 e t1) para saber quais onibus andaram.'''

    PARADO = 'parado'
    EM_MOVIMENTO = 'em movimento'
    SEM_ATUALIZACAO = 'sem atualizacao'

    def __init__(self, raw_t0: dict, raw_t1: dict, distancia_parado: float = 25):

        self.distancia_parado = distancia_parado
        t0 = parse_veiculos(raw_t0)[['prefixo', 'atualizado_em', 'latitude', 'longitude']]
        t1 = parse_veiculos(raw_t1)[['prefixo', 'letreiro', 'atualizado_em', 'latitude', 'longitude']]

        #so da pra comparar os onibus que aparecem nos dois instantes
        veiculos = t1.merge(t0, on='prefixo', suffixes=('', '_t0'))
        veiculos['distancia_m'] = distancia_metros(
            veiculos['latitude_t0'], veiculos['longitude_t0'], veiculos['latitude'], veiculos['longitude'],
        )
        #se o onibus nao mandou posicao nova, a posicao repetida nao quer dizer que ele esta parado
        veiculos['situacao'] = np.select(
            [veiculos['atualizado_em'] <= veiculos['atualizado_em_t0'], veiculos['distancia_m'] < distancia_parado],
            [self.SEM_ATUALIZACAO, self.PARADO],
            default=self.EM_MOVIMENTO,
        )
        self.veiculos: pd.DataFrame = veiculos[
            ['prefixo', 'letreiro', 'latitude', 'longitude', 'atualizado_em', 'distancia_m', 'situacao']
        ]

    def _contar(self, situacao: str) -> int:

        return int((self.veiculos['situacao'] == situacao).sum())

    @property
    def parados(self) -> int:

        return self._contar(self.PARADO)

    @property
    def em_movimento(self) -> int:

        return self._contar(self.EM_MOVIMENTO)

    @property
    def sem_atualizacao(self) -> int:

        return self._contar(self.SEM_ATUALIZACAO)

    @property
    def percentual_parados(self) -> float:
        '''Percentual de parados entre os onibus que mandaram posicao nova.'''

        comparados = self.parados + self.em_movimento
        if not comparados:
            return 0.0
        return 100 * self.parados / comparados


class MonitorMovimento:
    '''Busca a posicao atual na api e compara com a anterior. Cada comparacao vira o t0 da proxima.'''

    def __init__(self, client: APIOlhoVivoClient, raw_t0: dict, distancia_parado: float = 25):

        self.client = client
        self.distancia_parado = distancia_parado
        #ultimo retorno da api: e o t0 da proxima comparacao e pode alimentar os outros services
        self.ultimo_raw = raw_t0

    def comparar(self) -> MovimentoFrota:

        raw_t1 = self.client.posicao_atual_onibus()
        movimento = MovimentoFrota(self.ultimo_raw, raw_t1, self.distancia_parado)
        self.ultimo_raw = raw_t1
        return movimento
