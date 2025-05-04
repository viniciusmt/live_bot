import os
import time
import threading
import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class KeepAliveService:
    """
    Serviço para manter o aplicativo Render ativo, evitando que entre em modo de espera.
    No plano gratuito do Render, o aplicativo entra em modo de espera após 15 minutos de inatividade.
    """
    
    def __init__(self, interval_minutes=10):
        """
        Inicializa o serviço de keep-alive.
        
        Args:
            interval_minutes: Intervalo em minutos entre os pings
        """
        self.interval = interval_minutes * 60  # Converter para segundos
        self.running = False
        self.thread = None
        
        # Determinar a URL do serviço
        self.service_url = os.getenv("SERVER_URL")
        if not self.service_url:
            render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
            if render_hostname:
                self.service_url = f"https://{render_hostname}"
            else:
                self.service_url = "http://localhost:5000"
        
        logger.info(f"Serviço de keep-alive configurado para ping a cada {interval_minutes} minutos")
        logger.info(f"URL do serviço: {self.service_url}")
    
    def _ping_service(self):
        """Envia um ping para o serviço para mantê-lo ativo."""
        try:
            response = requests.get(f"{self.service_url}/")
            status_code = response.status_code
            
            if status_code == 200:
                logger.debug(f"Keep-alive ping bem-sucedido: {datetime.now().isoformat()}")
                return True
            else:
                logger.warning(f"Keep-alive ping falhou com status code {status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao enviar ping de keep-alive: {e}")
            return False
    
    def _keep_alive_loop(self):
        """Loop principal do serviço de keep-alive."""
        while self.running:
            self._ping_service()
            time.sleep(self.interval)
    
    def start(self):
        """Inicia o serviço de keep-alive em uma thread separada."""
        if self.running:
            logger.warning("Serviço de keep-alive já está em execução")
            return
        
        logger.info("Iniciando serviço de keep-alive")
        self.running = True
        self.thread = threading.Thread(target=self._keep_alive_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """Para o serviço de keep-alive."""
        if not self.running:
            logger.warning("Serviço de keep-alive não está em execução")
            return
        
        logger.info("Parando serviço de keep-alive")
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None

# Exemplo de uso
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Iniciar o serviço com ping a cada 10 minutos
    keep_alive = KeepAliveService(interval_minutes=10)
    keep_alive.start()
    
    try:
        # Manter o script em execução
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        # Parar o serviço quando Ctrl+C for pressionado
        keep_alive.stop()