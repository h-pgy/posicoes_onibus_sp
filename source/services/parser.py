import pandas as pd

COLUNAS = [
    'prefixo',
    'letreiro',
    'codigo_linha',
    'sentido',
    'origem',
    'destino',
    'acessivel',
    'atualizado_em',
    'latitude',
    'longitude',
]


def parse_veiculos(raw: dict) -> pd.DataFrame:
    '''Achata o retorno bruto de /Posicao em uma tabela com um registro por veiculo.'''

    registros = [
        {
            #a doc diz que p e int, mas em outros endpoints de posicao ele vem como string
            'prefixo': str(veiculo['p']),
            'letreiro': linha['c'],
            'codigo_linha': linha['cl'],
            'sentido': linha['sl'],
            #lt0/lt1 sao fixos por linha, nao trocam conforme o sentido
            'origem': linha['lt1'],
            'destino': linha['lt0'],
            'acessivel': veiculo['a'],
            'atualizado_em': veiculo['ta'],
            'latitude': veiculo['py'],
            'longitude': veiculo['px'],
        }
        for linha in raw['l']
        for veiculo in linha['vs']
    ]
    df = pd.DataFrame(registros, columns=COLUNAS)
    df['atualizado_em'] = pd.to_datetime(df['atualizado_em'], utc=True)
    return df
