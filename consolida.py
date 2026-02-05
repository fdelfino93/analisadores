import os
import math
import pandas as pd

# ===== CONFIG =====
INPUT_DIR = "exports_xlsx"                 # pasta onde estão os .xlsx
OUTPUT_XLSX = "olist_consolidado_flat.xlsx"

# Se você também tiver o customers, o script usa automaticamente (opcional)
OPTIONAL_CUSTOMERS_FILE = "olist_customers_dataset.xlsx"

# Excel tem limite de linhas por aba:
EXCEL_MAX_ROWS = 1_048_576
SAFE_MAX_ROWS = 1_040_000   # margem para header

def read_xlsx(table_name):
    """Lê o arquivo Excel exportado e retorna o DataFrame."""
    path = os.path.join(INPUT_DIR, f"{table_name}.xlsx")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    xls = pd.ExcelFile(path, engine="openpyxl")
    sheet = "dados" if "dados" in xls.sheet_names else xls.sheet_names[0]
    return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")

# ===== 1) Carregar tabelas =====
orders   = read_xlsx("olist_orders_dataset")
items    = read_xlsx("olist_order_items_dataset")
payments = read_xlsx("olist_order_payments_dataset")
reviews  = read_xlsx("olist_order_reviews_dataset")
products = read_xlsx("olist_products_dataset")
sellers  = read_xlsx("olist_sellers_dataset")
geo      = read_xlsx("olist_geolocation_dataset")

# Customers é opcional (caso você tenha exportado também)
customers_path = os.path.join(INPUT_DIR, OPTIONAL_CUSTOMERS_FILE)
customers = None
if os.path.exists(customers_path):
    customers = read_xlsx("olist_customers_dataset")
    print("✅ customers encontrado e será usado no join.")
else:
    print("ℹ️ customers não encontrado. Consolidando sem dados de cliente (CEP/cidade/estado do cliente).")

print("✅ Tabelas carregadas!")
print("orders:", orders.shape, "items:", items.shape, "payments:", payments.shape, "reviews:", reviews.shape)

# ===== 2) Ajustes/Agregações para evitar multiplicação =====

# 2.1 Payments: agrega por order_id (evita duplicar linhas por parcelas)
# Mantém total pago e algumas infos úteis
payments_agg = (payments
    .groupby("order_id", as_index=False)
    .agg(
        payment_value_total=("payment_value", "sum"),
        payment_installments_max=("payment_installments", "max"),
        payment_sequential_max=("payment_sequential", "max"),
        payment_type_first=("payment_type", "first")
    )
)

# 2.2 Reviews: se tiver mais de uma review por pedido, pega a “mais recente” (por timestamp)
# Se não existir timestamp, pega a primeira.
review_time_col = None
for c in ["review_answer_timestamp", "review_creation_date"]:
    if c in reviews.columns:
        review_time_col = c
        break

if review_time_col:
    # Garantir datetime
    reviews[review_time_col] = pd.to_datetime(reviews[review_time_col], errors="coerce")
    reviews_sorted = reviews.sort_values(by=[ "order_id", review_time_col ])
    reviews_agg = reviews_sorted.groupby("order_id", as_index=False).tail(1)
else:
    reviews_agg = reviews.drop_duplicates(subset=["order_id"], keep="first")

# Mantém apenas colunas mais úteis (ajuste se quiser)
keep_review_cols = [c for c in reviews_agg.columns if c in [
    "order_id", "review_id", "review_score", "review_comment_title",
    "review_comment_message", "review_creation_date", "review_answer_timestamp"
]]
reviews_agg = reviews_agg[keep_review_cols]

# 2.3 Geolocation: tem muitas linhas por CEP; agrega para 1 linha por zip_prefix + state
# (evita “explodir” o dataset ao juntar)
geo_cols_needed = ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"]
# Alguns dumps usam "geolocation_lng" ou "geolocation_Ing" (erro comum). Tenta corrigir:
if "geolocation_lng" not in geo.columns and "geolocation_Ing" in geo.columns:
    geo = geo.rename(columns={"geolocation_Ing": "geolocation_lng"})

geo_present = all(col in geo.columns for col in ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"])
if geo_present:
    geo_agg = (geo
        .groupby(["geolocation_zip_code_prefix", "geolocation_state"], as_index=False)
        .agg(
            geo_lat_mean=("geolocation_lat", "mean"),
            geo_lng_mean=("geolocation_lng", "mean"),
            geo_city_first=("geolocation_city", "first")
        )
    )
else:
    geo_agg = None
    print("⚠️ Não foi possível agregar geolocation (colunas lat/lng não encontradas).")

# ===== 3) Construir dataset consolidado =====
# Base: orders + items (granularidade: item por pedido)
df = orders.merge(items, on="order_id", how="left")

# Join com customers (se existir)
if customers is not None and "customer_id" in df.columns and "customer_id" in customers.columns:
    df = df.merge(customers, on="customer_id", how="left")

# Join com products
if "product_id" in df.columns and "product_id" in products.columns:
    df = df.merge(products, on="product_id", how="left", suffixes=("", "_product"))

# Join com sellers
if "seller_id" in df.columns and "seller_id" in sellers.columns:
    df = df.merge(sellers, on="seller_id", how="left", suffixes=("", "_seller"))

# Join com payments agregados
df = df.merge(payments_agg, on="order_id", how="left")

# Join com reviews agregados
df = df.merge(reviews_agg, on="order_id", how="left")

# Join com geolocation (cliente e seller) usando zip_prefix + state (se disponível)
if geo_agg is not None:
    # Geoloc do cliente (se existir)
    if customers is not None and "customer_zip_code_prefix" in df.columns and "customer_state" in df.columns:
        df = df.merge(
            geo_agg,
            left_on=["customer_zip_code_prefix", "customer_state"],
            right_on=["geolocation_zip_code_prefix", "geolocation_state"],
            how="left"
        )
        df = df.rename(columns={
            "geo_lat_mean": "customer_geo_lat_mean",
            "geo_lng_mean": "customer_geo_lng_mean",
            "geo_city_first": "customer_geo_city_ref"
        })
        # remove colunas técnicas do merge
        df = df.drop(columns=[c for c in ["geolocation_zip_code_prefix", "geolocation_state"] if c in df.columns], errors="ignore")

    # Geoloc do seller (se existir)
    if "seller_zip_code_prefix" in df.columns and "seller_state" in df.columns:
        df = df.merge(
            geo_agg,
            left_on=["seller_zip_code_prefix", "seller_state"],
            right_on=["geolocation_zip_code_prefix", "geolocation_state"],
            how="left"
        )
        df = df.rename(columns={
            "geo_lat_mean": "seller_geo_lat_mean",
            "geo_lng_mean": "seller_geo_lng_mean",
            "geo_city_first": "seller_geo_city_ref"
        })
        df = df.drop(columns=[c for c in ["geolocation_zip_code_prefix", "geolocation_state"] if c in df.columns], errors="ignore")

print(f"✅ Consolidado pronto: {df.shape[0]:,} linhas x {df.shape[1]:,} colunas")

# ===== 4) Salvar para Excel =====
print(f"Salvando {df.shape[0]:,} linhas em '{OUTPUT_XLSX}'...")

# Se o número de linhas for maior que o limite seguro do Excel, divide em várias abas
if df.shape[0] > SAFE_MAX_ROWS:
    print(f"O dataset é muito grande para uma única aba. Dividindo em várias abas...")
    num_sheets = math.ceil(df.shape[0] / SAFE_MAX_ROWS)
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        for i in range(num_sheets):
            start_row = i * SAFE_MAX_ROWS
            end_row = start_row + SAFE_MAX_ROWS
            sheet_name = f"dados_pt_{i+1}"
            print(f"  - Gravando aba '{sheet_name}' ({start_row+1} a {min(end_row, df.shape[0])})...")
            df.iloc[start_row:end_row].to_excel(writer, sheet_name=sheet_name, index=False)
else:
    # Se couber, salva em uma única aba "dados"
    df.to_excel(OUTPUT_XLSX, sheet_name="dados", index=False)

print("✅ Arquivo Excel gerado com sucesso!")