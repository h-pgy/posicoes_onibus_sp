import time
from collections import deque
from pathlib import Path

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

from source.integrations import APIOlhoVivoClient
from source.services import MetricasFrota, MonitorMovimento, MovimentoFrota, PosicoesOnibus, RegistroCSV

FUSO = 'America/Sao_Paulo'
#o timer do run_every nao e exato; sem essa folga uma coleta poderia ficar para o tick seguinte
FOLGA_COLETA_S = 2
MAX_HISTORICO = 240
#relativa a pasta de onde o app e rodado; cada sessao grava o proprio arquivo
PASTA_DADOS = Path('dados')
#onibus que aparecem so na leitura atual nao entram em MovimentoFrota
SEM_COMPARACAO = 'sem comparacao'

ROTULOS = {
    MovimentoFrota.PARADO: 'Parado',
    MovimentoFrota.EM_MOVIMENTO: 'Em movimento',
    MovimentoFrota.SEM_ATUALIZACAO: 'Sem posição nova',
    SEM_COMPARACAO: 'Sem leitura anterior',
}
#parado e o foco (laranja), em movimento e contexto (azul) e o resto fica cinza; validado para daltonismo
CORES = {
    'light': {'parado': '#eb6834', 'em_movimento': '#2a78d6', 'sem_info': '#898781', 'superficie': '#fcfcfb'},
    'dark': {'parado': '#d95926', 'em_movimento': '#3987e5', 'sem_info': '#898781', 'superficie': '#1a1a19'},
}
GRUPO_COR = {
    MovimentoFrota.PARADO: 'parado',
    MovimentoFrota.EM_MOVIMENTO: 'em_movimento',
    MovimentoFrota.SEM_ATUALIZACAO: 'sem_info',
    SEM_COMPARACAO: 'sem_info',
}
#ordem de desenho: o que vem depois fica por cima, entao os parados ficam visiveis
ORDEM_DESENHO = {SEM_COMPARACAO: 0, MovimentoFrota.SEM_ATUALIZACAO: 0, MovimentoFrota.EM_MOVIMENTO: 1, MovimentoFrota.PARADO: 2}
#mantida fixa entre reruns para o mapa nao perder o zoom do usuario
VISAO_INICIAL = pdk.ViewState(latitude=-23.56, longitude=-46.64, zoom=10)


def inteiro(valor: int) -> str:

    return f'{valor:,}'.replace(',', '.')


def decimal(valor: float, casas: int = 1) -> str:

    return f'{valor:.{casas}f}'.replace('.', ',')


def com_sinal(valor: float, formatar=inteiro) -> str:

    return ('+' if valor >= 0 else '-') + formatar(abs(valor))


def hora_local(instante: pd.Timestamp) -> pd.Timestamp:

    return instante.tz_convert(FUSO).tz_localize(None)


def rgb(hexa: str) -> list[int]:

    return [int(hexa[i:i + 2], 16) for i in (1, 3, 5)]


def cores_do_tema() -> dict[str, str]:

    return CORES['dark' if st.context.theme.type == 'dark' else 'light']


def iniciar_sessao() -> None:
    '''Busca a primeira leitura, que vira o t0 do monitor.'''

    estado = st.session_state
    client = APIOlhoVivoClient()
    estado.monitor = MonitorMovimento(client, client.posicao_atual_onibus())
    estado.posicoes = PosicoesOnibus(estado.monitor.ultimo_raw)
    estado.frota = MetricasFrota(estado.monitor.ultimo_raw)
    estado.movimento = None
    estado.historico = deque(maxlen=MAX_HISTORICO)
    estado.erro = None
    estado.ultima_coleta = time.monotonic()
    estado.registro = RegistroCSV(PASTA_DADOS / f'movimento_{pd.Timestamp.now(tz=FUSO):%Y%m%d_%H%M%S}.csv')


def coletar() -> None:
    '''Compara a posicao atual com a anterior e guarda o resultado no historico.'''

    estado = st.session_state
    #marca antes de chamar para que uma falha tambem espere o intervalo antes de tentar de novo
    estado.ultima_coleta = time.monotonic()
    anterior = estado.frota.atualizado_em
    try:
        movimento = estado.monitor.comparar()
    except (RuntimeError, requests.RequestException) as erro:
        estado.erro = str(erro)
        #o cookie de autenticacao expira; assim o client autentica de novo na proxima leitura
        if isinstance(erro, requests.HTTPError) and erro.response is not None and erro.response.status_code == 401:
            estado.monitor.client.autenticado = False
        return

    estado.erro = None
    estado.movimento = movimento
    estado.posicoes = PosicoesOnibus(estado.monitor.ultimo_raw)
    estado.frota = MetricasFrota(estado.monitor.ultimo_raw)
    estado.historico.append({
        'hora': hora_local(estado.frota.atualizado_em),
        'janela_s': (estado.frota.atualizado_em - anterior).total_seconds(),
        'parados': movimento.parados,
        'em_movimento': movimento.em_movimento,
        'sem_atualizacao': movimento.sem_atualizacao,
        'percentual_parados': movimento.percentual_parados,
    })
    try:
        estado.registro.registrar(movimento, estado.frota.atualizado_em)
    except OSError as erro:
        estado.erro = f'não foi possível gravar o CSV: {erro}'


def mostrar_frota(frota: MetricasFrota) -> None:

    colunas = st.columns(5)
    colunas[0].metric('Ônibus circulando', inteiro(frota.total_veiculos), border=True)
    colunas[1].metric('Linhas', inteiro(frota.total_linhas), border=True)
    colunas[2].metric('Ônibus por linha', decimal(frota.media_veiculos_por_linha), help='Média, somando os dois sentidos', border=True)
    colunas[3].metric(
        'Acessíveis', f'{decimal(frota.percentual_acessiveis)}%',
        help=f'{inteiro(frota.veiculos_acessiveis)} ônibus', border=True,
    )
    minutos = int(frota.limite_atraso.total_seconds() // 60)
    colunas[4].metric(
        f'Posição com mais de {minutos} min', inteiro(frota.veiculos_desatualizados),
        help='Em relação à captura mais recente da API', border=True,
    )


def mostrar_movimento(historico: deque, intervalo: int) -> None:

    if not historico:
        st.info(f'A primeira comparação de movimento sai em até {intervalo} s: é preciso duas leituras da API.')
        return

    atual = historico[-1]
    anterior = historico[-2] if len(historico) > 1 else None
    serie = pd.DataFrame(historico)

    def delta(campo: str, formatar=inteiro) -> str | None:
        return com_sinal(atual[campo] - anterior[campo], formatar) if anterior else None

    colunas = st.columns(4)
    colunas[0].metric(
        'Parados', inteiro(atual['parados']), delta('parados'), delta_color='off',
        chart_data=serie['parados'], border=True,
    )
    colunas[1].metric(
        'Em movimento', inteiro(atual['em_movimento']), delta('em_movimento'), delta_color='off',
        chart_data=serie['em_movimento'], border=True,
    )
    colunas[2].metric(
        'Sem posição nova', inteiro(atual['sem_atualizacao']), delta('sem_atualizacao'), delta_color='off',
        chart_data=serie['sem_atualizacao'], border=True,
        help='Não mandaram posição desde a leitura anterior; ficam fora do percentual',
    )
    colunas[3].metric(
        '% parados', f'{decimal(atual["percentual_parados"])}%', delta('percentual_parados', decimal),
        delta_color='off', chart_data=serie['percentual_parados'], border=True,
        help='Entre os ônibus que mandaram posição nova',
    )
    st.caption(
        f'Comparação entre as duas últimas leituras ({decimal(atual["janela_s"], 0)} s entre elas). '
        f'Parado = andou menos de {decimal(st.session_state.monitor.distancia_parado, 0)} m.'
    )


def explicar_parados(intervalo: int, distancia: float) -> None:

    #com key o expander continua aberto quando o fragment reroda
    with st.expander('Como é calculado o número de ônibus parados?', key='explicacao_parados'):
        st.markdown(f'''
**1. Duas leituras seguidas.** A cada {intervalo} s o app pede ao endpoint `/Posicao` da API Olho Vivo a
posição de todos os ônibus em circulação e compara com a leitura anterior. Cada leitura vira a referência
da seguinte, então os números são sempre da janela mais recente.

**2. Só ônibus presentes nas duas leituras.** O ônibus é identificado pelo prefixo. Quem aparece só na
leitura atual (acabou de entrar em circulação) fica de fora da conta e aparece em cinza no mapa.

**3. Mandou posição nova?** Cada posição vem com o horário em que o ônibus a enviou. Se esse horário não
avançou desde a leitura anterior, o ônibus conta como **sem posição nova**: a posição repetida não quer dizer
que ele está parado, só que ainda não atualizou.

**4. Distância percorrida.** Para os demais, calcula-se a distância em linha reta entre as duas posições
(fórmula de haversine). Menos de **{decimal(distancia, 0)} m** é **parado**; a partir disso, **em movimento**.

**5. Percentual.** % parados = parados ÷ (parados + em movimento). Os sem posição nova ficam fora da conta.

**Cuidados na leitura**
- Parado não é só congestionamento: inclui ônibus em ponto, semáforo e terminal.
- O resultado depende da janela entre as leituras: com janelas curtas, mais ônibus ficam abaixo do limite
  de distância e mais ficam sem posição nova.
- O GPS tem erro de alguns metros; o limite de {decimal(distancia, 0)} m evita que esse ruído conte como movimento.
- É distância em linha reta: um ônibus que sai e volta ao mesmo ponto dentro da janela conta como parado.
''')


def mostrar_mapa(posicoes: PosicoesOnibus, movimento: MovimentoFrota | None, linhas: list[str]) -> None:

    cores = cores_do_tema()
    dados = posicoes.dados
    if movimento is not None:
        dados = dados.merge(movimento.veiculos[['prefixo', 'situacao']], on='prefixo', how='left')
    else:
        dados = dados.assign(situacao=None)
    dados['situacao'] = dados['situacao'].fillna(SEM_COMPARACAO)
    if linhas:
        dados = dados[dados['letreiro'].isin(linhas)]

    contagem = dados['situacao'].map(GRUPO_COR).value_counts()
    legenda = [
        f'<span style="color:{cores[grupo]}">●</span> {rotulo} **{inteiro(contagem.get(grupo, 0))}**'
        for grupo, rotulo in [('parado', 'Parado'), ('em_movimento', 'Em movimento'), ('sem_info', 'Sem informação de movimento')]
    ]
    st.markdown(' &nbsp;&nbsp; '.join(legenda), unsafe_allow_html=True)

    dados = dados.assign(
        rotulo=dados['situacao'].map(ROTULOS),
        cor=dados['situacao'].map(lambda situacao: rgb(cores[GRUPO_COR[situacao]])),
        ordem=dados['situacao'].map(ORDEM_DESENHO),
    ).sort_values('ordem')
    camada = pdk.Layer(
        'ScatterplotLayer',
        data=dados[['prefixo', 'letreiro', 'rotulo', 'latitude', 'longitude', 'cor']],
        get_position=['longitude', 'latitude'],
        get_fill_color='cor',
        get_radius=40,
        radius_min_pixels=3,
        radius_max_pixels=9,
        stroked=True,
        get_line_color=rgb(cores['superficie']),
        line_width_min_pixels=1,
        pickable=True,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=[camada],
            initial_view_state=VISAO_INICIAL,
            tooltip={'html': '<b>Ônibus {prefixo}</b> · linha {letreiro}<br/>{rotulo}'},
        ),
        height=560,
        key='mapa',
    )


def mostrar_historico(historico: deque) -> None:

    st.subheader('Parados × em movimento')
    if len(historico) < 2:
        st.caption('O gráfico aparece a partir da segunda comparação.')
        return
    cores = cores_do_tema()
    serie = pd.DataFrame(historico).rename(columns={'parados': 'Parados', 'em_movimento': 'Em movimento'})
    st.line_chart(
        serie, x='hora', y=['Parados', 'Em movimento'], color=[cores['parado'], cores['em_movimento']],
        x_label='Horário (Brasília)', y_label='Ônibus',
    )


def mostrar_download(registro: RegistroCSV) -> None:

    st.subheader('Dados gravados')
    if not registro.caminho.exists():
        st.caption('O CSV começa a ser gravado na primeira comparação.')
        return
    tamanho_mb = registro.caminho.stat().st_size / 1e6
    st.caption(
        f'{inteiro(registro.linhas)} linhas de {inteiro(registro.leituras)} '
        f'{"comparação" if registro.leituras == 1 else "comparações"} '
        f'({decimal(tamanho_mb)} MB) em `{registro.caminho}`. Uma linha por ônibus comparado, '
        'com posição, linha, horário e situação (parado, em movimento ou sem atualização).'
    )
    #callable: o arquivo so e lido quando clicam, e on_click='ignore' evita rerodar o painel
    st.download_button(
        'Baixar CSV', data=registro.ler, file_name=registro.caminho.name, mime='text/csv',
        on_click='ignore', icon=':material/download:',
    )


def mostrar_linhas(frota: MetricasFrota) -> None:

    st.subheader('Ônibus por linha')
    st.dataframe(
        frota.veiculos_por_linha,
        hide_index=True,
        height=380,
        column_config={
            'letreiro': 'Linha',
            'origem': 'Origem',
            'destino': 'Destino',
            'veiculos': st.column_config.NumberColumn('Ônibus', help='Somando os dois sentidos'),
        },
    )


st.set_page_config(page_title='Ônibus SP ao vivo', page_icon='🚌', layout='wide')
estado = st.session_state

if 'monitor' not in estado:
    try:
        with st.spinner('Buscando as posições na API Olho Vivo...'):
            iniciar_sessao()
    except (RuntimeError, requests.RequestException) as erro:
        st.error(f'Não foi possível buscar as posições: {erro}')
        st.stop()

with st.sidebar:
    st.header('Configurações')
    loop_ativo = st.toggle('Atualização automática', value=True)
    intervalo = st.slider('Intervalo entre leituras (s)', 15, 300, 30, step=15, disabled=not loop_ativo)
    estado.monitor.distancia_parado = st.slider(
        'Parado se andou menos de (m)', 5, 200, 25, step=5, help='Vale a partir da próxima comparação',
    )
    #inclui as ja escolhidas para a selecao nao quebrar se a linha sair de circulacao
    opcoes = sorted(set(estado.frota.veiculos['letreiro']) | set(estado.get('linhas', [])))
    linhas = st.multiselect('Linhas no mapa', opcoes, key='linhas', placeholder='Todas as linhas')

st.title('Ônibus de São Paulo ao vivo')


@st.fragment(run_every=intervalo if loop_ativo else None)
def painel_ao_vivo() -> None:
    '''Reroda sozinho a cada intervalo, sem rerodar o resto do app.'''

    #reruns do app inteiro (mexer na sidebar) tambem passam por aqui; so chama a api quando deu o intervalo
    if loop_ativo and time.monotonic() - estado.ultima_coleta >= intervalo - FOLGA_COLETA_S:
        coletar()

    atualizado_em = estado.frota.atualizado_em
    captura = hora_local(atualizado_em).strftime('%H:%M:%S') if pd.notna(atualizado_em) else '—'
    ritmo = f'nova leitura a cada {intervalo} s' if loop_ativo else 'atualização automática pausada'
    st.caption(f'Dados da API Olho Vivo (SPTrans) · captura mais recente às {captura} · {ritmo}')
    #containers fixos mantem a posicao do mapa estavel entre reruns, senao ele perde o zoom
    with st.container():
        if estado.erro:
            st.warning(f'A última leitura falhou ({estado.erro}). Mostrando os dados anteriores.')

    mostrar_frota(estado.frota)
    st.subheader('Movimento')
    with st.container():
        mostrar_movimento(estado.historico, intervalo)
    explicar_parados(intervalo, estado.monitor.distancia_parado)
    mostrar_mapa(estado.posicoes, estado.movimento, linhas)

    esquerda, direita = st.columns(2, gap='large')
    with esquerda:
        mostrar_historico(estado.historico)
    with direita:
        mostrar_linhas(estado.frota)
    mostrar_download(estado.registro)


painel_ao_vivo()
