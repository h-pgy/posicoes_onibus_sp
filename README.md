# Posições dos ônibus de São Paulo

Painel em Streamlit com a posição em tempo real dos ônibus da SPTrans, métricas da frota e quantos ônibus
estão parados a cada momento. Os dados vêm da API Olho Vivo. O painel também grava um CSV com a situação de
cada ônibus, que dá para baixar pelo próprio app.

## Como rodar

Requer Python 3.13 e [uv](https://docs.astral.sh/uv/).

1. Gere um token da API Olho Vivo em <https://www.sptrans.com.br/desenvolvedores/> (precisa de cadastro).
2. Copie `.env.example` para `.env` e preencha `OLHO_VIVO_TOKEN`.
3. Instale as dependências e suba o app:

```bash
uv sync
uv run streamlit run app.py   # abre em http://localhost:8501
```

Testes:

```bash
uv run pytest -m "not integration"   # unidade: services, client e app com a API simulada, sem rede
uv run pytest -m integration         # chamam a API real; são pulados se não houver token no .env
```

## De onde vêm os dados

Tudo vem da [API Olho Vivo](https://www.sptrans.com.br/desenvolvedores/) da SPTrans, versão 2.1 (`https://api.olhovivo.sptrans.com.br/v2.1`). O código usa duas chamadas:

| Chamada | Para quê |
|---|---|
| `POST /Login/Autenticar?token=...` | Autentica. A resposta é o texto `true` ou `false` (não é um JSON válido) e a autenticação fica num cookie, então todas as requisições usam a mesma `requests.Session`. |
| `GET /Posicao` | Posição de todos os ônibus em circulação, agrupados por linha e sentido. |

Formato do `/Posicao`, só com os campos usados:

```jsonc
{
  "hr": "17:11",               // hora em que a API gerou o retorno (horário de Brasília, HH:MM)
  "l": [                       // uma entrada por linha *e sentido*
    {
      "c": "5031-10",          // letreiro da linha
      "cl": 1746,              // código interno da linha (muda conforme o sentido)
      "sl": 1,                 // sentido: 1 ou 2
      "lt0": "TERM. SACOMÃ",   // letreiro de destino
      "lt1": "VL. ARAPUÁ",     // letreiro de origem
      "qv": 2,                 // quantidade de veículos
      "vs": [
        {
          "p": 55351,                    // prefixo do veículo
          "a": true,                     // acessível para pessoas com deficiência
          "ta": "2026-10-25T20:11:40Z",  // quando o veículo enviou essa posição (UTC)
          "py": -23.6,                   // latitude
          "px": -46.6                    // longitude
        }
      ]
    }
  ]
}
```

Comportamentos da API que o código trata:

- O `/Posicao` às vezes responde `null` (mais ou menos 1 a cada 15 chamadas). O client tenta até 3 vezes,
  esperando 1 s entre as tentativas.
- A documentação diz que `p` é inteiro, mas em outros endpoints de posição ele vem como string. O parser
  converte tudo para string.
- `lt0` e `lt1` são fixos por linha e não trocam com o sentido. O parser usa `lt1` como origem e `lt0` como
  destino.
- A mesma linha aparece duas vezes, uma por sentido e cada uma com seu `cl`. As contagens por linha usam o
  letreiro (`c`) para juntar os dois sentidos.
- Se uma leitura receber 401 (autenticação expirada), o app marca o client como não autenticado e ele
  autentica de novo na leitura seguinte.

## Estrutura do código

```
source/
  integrations/
    url_builder.py   RequestMaker: monta as URLs e faz as requisições numa sessão HTTP única (timeout de 10 s)
    olho_vivo.py     APIOlhoVivoClient: lê o token do .env, autentica na primeira chamada e repete quando vem null
  services/
    parser.py        parse_veiculos: achata o /Posicao em um DataFrame com um registro por ônibus
    posicoes.py      PosicoesOnibus: prefixo, letreiro e coordenadas (alimenta o mapa)
    metricas.py      MetricasFrota: métricas agregadas de uma leitura
    movimento.py     MovimentoFrota e MonitorMovimento: comparam leituras para saber quem está parado
    registro.py      RegistroCSV: acumula as comparações num CSV
app.py               painel Streamlit
tests/
  unit/              services, client e app (com a API simulada)
  integration/       formato real do /Posicao
```

O fluxo é sempre o mesmo: `APIOlhoVivoClient.posicao_atual_onibus()` devolve o JSON bruto, e cada service
recebe esse dict, passa por `parse_veiculos` e expõe só o que precisa. Os services não acessam a rede (o
`MonitorMovimento` recebe o client de fora), por isso os testes usam dicts montados à mão.

`parse_veiculos` gera as colunas `prefixo`, `letreiro`, `codigo_linha`, `sentido`, `origem`, `destino`,
`acessivel`, `atualizado_em` (o `ta`, em UTC), `latitude` e `longitude`.

## Métricas

### Frota (`MetricasFrota`)

Calculadas sobre uma única leitura do `/Posicao`.

| Métrica | Como é calculada |
|---|---|
| Ônibus circulando | Número de veículos no retorno. |
| Linhas | Letreiros distintos. Os dois sentidos contam como uma linha só. |
| Ônibus por linha | Ônibus ÷ linhas. |
| Tabela de ônibus por linha | Veículos por letreiro somando os dois sentidos, do maior para o menor. |
| Acessíveis | Percentual de veículos com `a = true`. |
| Posição com mais de 5 min | Veículos cujo `ta` está mais de 5 min atrás do `ta` mais recente da mesma leitura. |

O atraso é medido em relação à captura mais recente da própria leitura, e não ao relógio de quem roda o
código. Assim a métrica não depende do relógio nem do fuso da máquina, e um atraso geral da API não faz a frota
inteira parecer desatualizada.

### Ônibus parados (`MovimentoFrota` e `MonitorMovimento`)

Uma única leitura não diz se um ônibus está parado, então o código compara duas leituras seguidas, t0 e t1:

1. **Só entram ônibus presentes nas duas leituras.** O ônibus é identificado pelo prefixo. Quem aparece só em
   t1 (entrou em circulação) ou só em t0 (saiu) fica de fora.
2. **Sem atualização.** Se o `ta` de t1 não é mais novo que o de t0, o ônibus não mandou posição nova. A
   posição repetida não quer dizer que ele está parado, então ele vira `sem atualizacao`.
3. **Distância.** Para os demais, calcula-se a distância em linha reta entre as duas posições pela fórmula de
   haversine (raio da Terra de 6.371 km).
4. **Classificação.** Menos de 25 m é `parado`; 25 m ou mais é `em movimento`. O limite é configurável
   (`distancia_parado`) e pode ser mudado na sidebar do app.
5. **Percentual de parados** = parados ÷ (parados + em movimento) × 100. Os sem atualização ficam fora da
   conta, e sem nenhum ônibus comparável o percentual é 0.

O `MonitorMovimento` guarda a última leitura. Cada `comparar()` busca uma leitura nova, compara com a anterior,
e a nova vira o t0 da próxima. Então cada comparação cobre só a janela entre duas leituras seguidas (mais ou
menos o intervalo do loop do app), e não o tempo desde que o app abriu.

Cuidados ao interpretar:

- Parado não é só congestionamento: inclui ônibus em ponto, semáforo e terminal.
- O resultado depende da janela entre as leituras. Com janelas curtas, mais ônibus ficam abaixo do limite de
  distância e mais ficam sem posição nova.
- O GPS tem erro de alguns metros. O limite de 25 m existe para esse ruído não contar como movimento.
- É distância em linha reta: um ônibus que sai e volta ao mesmo ponto dentro da janela conta como parado.

Para ter uma ordem de grandeza: numa leitura de teste num domingo por volta das 17h30, com 36 s entre as
leituras, a API trouxe 7.118 ônibus, com 2.192 parados, 3.610 em movimento e 1.295 sem posição nova
(37,8% parados).

### CSV gravado (`RegistroCSV`)

A cada comparação o app acrescenta ao CSV uma linha por ônibus comparado:

| Coluna | Conteúdo |
|---|---|
| `leitura` | Instante da leitura que gerou a comparação (o `ta` mais recente de t1). Agrupando por ela dá para refazer a série de parados. |
| `prefixo` | Prefixo do ônibus. |
| `letreiro` | Linha. |
| `latitude`, `longitude` | Posição em t1. |
| `atualizado_em` | Quando o ônibus enviou essa posição (`ta`). |
| `distancia_m` | Distância percorrida desde a leitura anterior, em metros. |
| `situacao` | `parado`, `em movimento` ou `sem atualizacao`. |

- Os horários são de Brasília, com o offset (`2026-10-25 17:31:33-03:00`).
- Nas linhas `sem atualizacao`, a posição e o `atualizado_em` repetem os da leitura anterior.
- Cada sessão do app (cada aba aberta) grava o próprio arquivo em `dados/movimento_AAAAMMDD_HHMMSS.csv`, na
  pasta de onde o app foi rodado. Recarregar a página começa um arquivo novo, e os antigos ficam em `dados/`,
  que está no `.gitignore`.
- O arquivo cresce rápido: cerca de 0,8 MB por comparação, ou uns 100 MB por hora no intervalo padrão de 30 s.

## O app

- **Sessão.** Ao abrir, o app autentica e faz a primeira leitura, que vira o t0. Cada aba do navegador tem o
  próprio monitor, histórico, CSV e chamadas à API.
- **Loop.** O painel fica dentro de um `@st.fragment(run_every=intervalo)`. O Streamlit reroda só esse trecho
  a cada intervalo, sem rerodar o script inteiro nem travar a sidebar. Mexer na sidebar reroda o app todo (e o
  fragment junto), mas a API só é chamada se o intervalo já passou. Há uma folga de 2 s, porque o timer do
  Streamlit não é exato.
- **Falhas.** Se uma leitura falhar, aparece um aviso e os dados anteriores continuam na tela. O t0 não muda,
  então a próxima comparação é contra a última leitura boa. Uma falha também espera o intervalo inteiro antes
  de tentar de novo.
- **Histórico.** Os cartões e o gráfico usam as últimas 240 comparações (2 h no intervalo padrão), só em
  memória. O histórico completo fica no CSV.
- **Mapa.** Feito com pydeck. Laranja é parado, azul é em movimento e cinza é sem informação (sem posição nova
  ou sem leitura anterior). Os parados são desenhados por cima. A visão inicial é fixa para o mapa manter o
  zoom de quem está olhando quando os dados atualizam. As cores foram validadas para daltonismo.
- **Explicação.** O accordion "Como é calculado o número de ônibus parados?" explica a conta com o intervalo
  e o limite de distância configurados no momento.

Controles da sidebar:

| Controle | Padrão | Efeito |
|---|---|---|
| Atualização automática | ligada | Liga ou pausa o loop. |
| Intervalo entre leituras | 30 s (15 a 300) | Tempo entre as chamadas ao `/Posicao`. |
| Parado se andou menos de | 25 m (5 a 200) | Limite de distância. Vale a partir da próxima comparação. |
| Linhas no mapa | todas | Filtra só o mapa; as métricas continuam sendo da frota inteira. |
