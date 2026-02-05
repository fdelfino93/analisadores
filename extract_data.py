import os
from dotenv import load_dotenv
import pandas as pd
import mysql.connector


# Carregar variáveis de ambiente do arquivo .env
env_path = r'c:\Users\HARVE\Documents\projeto\.env'
load_dotenv(env_path)

# Obter credenciais do .env
db_host = os.getenv("DB_HOST")
print(f"DEBUG: DB_HOST from os.getenv is: {db_host}")
db_user = os.getenv("DB_USER")
db_pass = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_port = os.getenv("DB_PORT", "3306")

try:
    print(f"Conectando ao banco de dados {db_name} em {db_host}...")
    conn = mysql.connector.connect(
        host=db_host,
        user=db_user,
        password=db_pass,
        database=db_name,
        port=db_port,
        connection_timeout=30
    )
    print("Conexão com o banco de dados estabelecida com sucesso.")

    # Ler a lista de tabelas do arquivo tabelas.md
    tables_file = r'c:\Users\HARVE\Documents\projeto\tabelas.md'
    with open(tables_file, 'r') as f:
        # Lê cada linha, remove espaços em branco e ignora linhas vazias
        tables = [line.strip() for line in f if line.strip()]

    # Criar a pasta de saída se não existir
    output_dir = "exports_xlsx"
    os.makedirs(output_dir, exist_ok=True)
    print(f"Diretório de saída '{output_dir}' pronto.")

    # Iterar sobre cada tabela e baixar os dados
    for table_name in tables:
        print(f"Extraindo dados da tabela '{table_name}'...")
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql(query, conn)

        # Salvar em um arquivo .xlsx separado para cada tabela
        output_file = os.path.join(output_dir, f"{table_name}.xlsx")
        df.to_excel(output_file, sheet_name="dados", index=False)
        print(f"Sucesso! {len(df)} registros da tabela '{table_name}' salvos em '{output_file}'.")

    print(f"Todas as tabelas foram baixadas e salvas na pasta '{output_dir}' com sucesso.")

except Exception as e:
    print(f"Erro ao extrair dados: {e}")

finally:
    if 'conn' in locals() and conn.is_connected():
        conn.close()
        print("Conexão com o banco de dados fechada.")