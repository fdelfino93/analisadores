import mysql.connector
import pandas as pd

try:
    # Completando o código fornecido com o nome correto do banco de dados
    conn = mysql.connector.connect(
        host="ip-45-79-142-173.cloudezapp.io",
        port=3306,
        user="alunosqlharve",
        password="Ed&ktw35j",
        database="modulosql"
    )

    if conn.is_connected():
        print("Conexão direta (mysql.connector) estabelecida com sucesso!")
        
        # Teste de extração
        query = "SELECT * FROM olist_customers_dataset LIMIT 5"
        df = pd.read_sql(query, conn)
        
        # Salvar em Excel
        df.to_excel("olist_customers_dataset.xlsx", index=False)
        print("Sucesso! Arquivo 'olist_customers_dataset.xlsx' gerado.")
        
        conn.close()

except Exception as e:
    print(f"Erro na conexão: {e}")