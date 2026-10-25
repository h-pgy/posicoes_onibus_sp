import logging
import os
import time
from functools import wraps

from dotenv import load_dotenv

from .url_builder import RequestMaker

logger = logging.getLogger(__name__)


def requer_autenticacao(func):
    '''Autentica o cliente antes de chamar o endpoint, caso ainda nao esteja autenticado.'''

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.autenticado:
            self.autenticar() #lazy evaluation
        return func(self, *args, **kwargs)

    return wrapper


class APIOlhoVivoClient:

    HOST = 'api.olhovivo.sptrans.com.br'
    METHOD = 'https'
    VERSION = '2.1'
    ENV_TOKEN = 'OLHO_VIVO_TOKEN'
    TENTATIVAS = 3
    ESPERA_ENTRE_TENTATIVAS = 1

    def __init__(self, token: str | None = None):

        self.request = RequestMaker(self.METHOD, self.HOST, self.VERSION)
        self.token = token or self._token_do_env()
        self.autenticado = False

    @classmethod
    def _token_do_env(cls) -> str:

        load_dotenv()
        token = os.getenv(cls.ENV_TOKEN)
        if not token:
            raise RuntimeError(f'Token nao encontrado: preencha {cls.ENV_TOKEN} no arquivo .env')
        return token

    def autenticar(self) -> None:

        endpoint = 'Login/Autenticar'
        params = {'token': self.token}

        #a api nao retorna um json valido
        resp = self.request.post(endpoint, params, as_json=False)
        if resp != 'true':
            raise RuntimeError(f'Falha ao autenticar: {resp}')
        self.autenticado = True
        logger.info('Autenticado com sucesso.')

    @requer_autenticacao
    def posicao_atual_onibus(self) -> dict:

        endpoint = 'Posicao'
        #de vez em quando a api responde null (~1 a cada 15 chamadas); tentar de novo resolve
        for _ in range(self.TENTATIVAS):
            resp = self.request.get(endpoint)
            if resp is not None:
                return resp
            logger.warning('Api retornou null em %s, tentando de novo.', endpoint)
            time.sleep(self.ESPERA_ENTRE_TENTATIVAS)
        raise RuntimeError(f'Api retornou null em {endpoint} apos {self.TENTATIVAS} tentativas')
