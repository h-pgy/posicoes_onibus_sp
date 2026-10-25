import threading
from pathlib import Path

import pandas as pd

from .movimento import MovimentoFrota


class RegistroCSV:
    '''Acumula num csv a situacao de cada onibus a cada comparacao, uma linha por onibus comparado.'''

    COLUNAS = ['leitura', 'prefixo', 'letreiro', 'latitude', 'longitude', 'atualizado_em', 'distancia_m', 'situacao']
    FUSO = 'America/Sao_Paulo'

    def __init__(self, caminho: str | Path):

        self.caminho = Path(caminho)
        self.leituras = 0
        self.linhas = 0
        #o download le o arquivo em outra thread; a trava evita ler uma linha pela metade
        self._trava = threading.Lock()

    def registrar(self, movimento: MovimentoFrota, leitura: pd.Timestamp) -> None:
        '''Acrescenta a comparacao ao csv; leitura e o instante da leitura mais recente (t1).'''

        if movimento.veiculos.empty:
            return
        #7 casas nas coordenadas ja e precisao de centimetros e tira o ruido de float do csv
        dados = movimento.veiculos.assign(leitura=leitura).round({'latitude': 7, 'longitude': 7, 'distancia_m': 1})
        #horario de brasilia com o offset, para ficar legivel sem perder a referencia
        for coluna in ['leitura', 'atualizado_em']:
            dados[coluna] = dados[coluna].dt.tz_convert(self.FUSO)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._trava:
            #cabecalho so na primeira escrita, para o arquivo continuar sendo um csv valido
            dados[self.COLUNAS].to_csv(self.caminho, mode='a', header=not self.caminho.exists(), index=False)
        self.leituras += 1
        self.linhas += len(dados)

    def ler(self) -> bytes:

        with self._trava:
            return self.caminho.read_bytes()
