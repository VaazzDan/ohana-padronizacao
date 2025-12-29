# Usa uma imagem Python leve
FROM python:3.9-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia o arquivo de requisitos e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação e a pasta de configuração (.streamlit)
COPY app.py .
COPY .streamlit/ .streamlit/

# Expõe a porta padrão do Streamlit
EXPOSE 8501

# Comando para iniciar a aplicação e permitir acesso externo
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]