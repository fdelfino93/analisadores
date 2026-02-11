# app_full.py
# Dashboard Olist - 9 desafios
# Conecta ao MySQL (modulosql), consolida as 8 tabelas e calcula tudo on-the-fly.

import os
import json
import datetime as dt
import numpy as np
import pandas as pd
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine
from urllib.parse import quote_plus

# ============================================================
# Page Config + CSS
# ============================================================
st.set_page_config(page_title="Dashboard Olist", page_icon="📊", layout="wide")

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #0d3b66 0%, #1d7874 50%, #2ecc71 100%);
        padding: 2rem 2.5rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
    }
    .main-header h1 { margin: 0; font-size: 2rem; font-weight: 700; }
    .main-header p  { margin: 0.3rem 0 0 0; opacity: 0.85; font-size: 0.95rem; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #14524a 0%, #1d7874 100%);
        border-radius: 8px;
        padding: 1rem;
        border-left: 4px solid #2ecc71;
    }
    [data-testid="stMetric"] label,
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: white !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        background: linear-gradient(180deg, #0d3b66 0%, #14524a 100%);
        color: white;
    }
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown h3,
    section[data-testid="stSidebar"] span {
        color: white !important;
    }
</style>
<div class="main-header">
    <h1>📊 DASHBOARD OLIST</h1>
    <p>Dados em Tempo Real</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# Utilidades
# ============================================================
REQ_COLS = [
    'order_id','customer_unique_id','order_status',
    'order_purchase_timestamp','order_approved_at',
    'order_delivered_carrier_date','order_delivered_customer_date','order_estimated_delivery_date',
    'payment_value_total','payment_type_first','payment_installments_max',
    'review_score','review_comment_title','review_comment_message','review_creation_date',
    'product_category_name','product_photos_qty','price','freight_value',
    'product_weight_g','product_length_cm','product_height_cm','product_width_cm',
    'customer_state','customer_city','seller_state','seller_city',
    'customer_geo_lat_mean','customer_geo_lng_mean','seller_geo_lat_mean','seller_geo_lng_mean',
    'order_item_id'
]

TEAL = ['#0d3b66','#14524a','#1d7874','#2ecc71','#a8e6cf']
PAIR = ['#1d7874','#2ecc71']

# Formatacao padrao brasileiro: ponto para milhar, virgula para decimal
def fmt_br(v, decimals=0):
    if pd.isna(v):
        return '-'
    s = f"{float(v):,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_brl(v, decimals=2):
    return f"R$ {fmt_br(v, decimals)}"

def has_text(x) -> bool:
    if x is None:
        return False
    try:
        return len(str(x).strip()) > 0
    except Exception:
        return False

def styled_bar(dataframe, x, y, title, text=None, orientation='v'):
    """Bar chart com degrade baseado nos valores."""
    fig = px.bar(
        dataframe, x=x, y=y, title=title, text=text,
        color=y, color_continuous_scale='Teal', orientation=orientation,
    )
    fig.update_layout(
        coloraxis_showscale=False,
        title_font_size=16,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=50, b=30),
        separators=",.",
    )
    if text:
        fig.update_traces(textposition='outside')
    return fig

# ============================================================
# Conexao MySQL
# ============================================================
load_dotenv()
DB_HOST     = os.getenv('DB_HOST')
DB_PORT     = os.getenv('DB_PORT', '3306')
DB_USER     = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME     = os.getenv('DB_NAME')

def get_engine():
    url = (
        f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    return create_engine(url)

# ============================================================
# Carga e consolidacao
# ============================================================
@st.cache_data(show_spinner="Carregando dados do banco...", ttl=300)
def load_data():
    engine = get_engine()
    orders    = pd.read_sql("SELECT * FROM olist_orders_dataset", engine)
    customers = pd.read_sql("SELECT * FROM olist_customers_dataset", engine)
    items     = pd.read_sql("SELECT * FROM olist_order_items_dataset", engine)
    products  = pd.read_sql("SELECT * FROM olist_products_dataset", engine)
    payments  = pd.read_sql("SELECT * FROM olist_order_payments_dataset", engine)
    reviews   = pd.read_sql("SELECT * FROM olist_order_reviews_dataset", engine)
    sellers   = pd.read_sql("SELECT * FROM olist_sellers_dataset", engine)
    geo       = pd.read_sql("SELECT * FROM olist_geolocation_dataset", engine)

    pay_agg = payments.groupby('order_id').agg(
        payment_value_total=('payment_value', 'sum'),
        payment_installments_max=('payment_installments', 'max')
    ).reset_index()
    pay_first = (
        payments.sort_values('payment_sequential')
        .drop_duplicates('order_id')[['order_id', 'payment_type']]
        .rename(columns={'payment_type': 'payment_type_first'})
    )
    pay_agg = pay_agg.merge(pay_first, on='order_id', how='left')

    geo_agg = geo.groupby('geolocation_zip_code_prefix').agg(
        geo_lat_mean=('geolocation_lat', 'mean'),
        geo_lng_mean=('geolocation_lng', 'mean')
    ).reset_index()

    reviews = (reviews.sort_values('review_creation_date')
               .drop_duplicates('order_id', keep='last'))

    df = items.merge(orders, on='order_id', how='left')
    df = df.merge(customers, on='customer_id', how='left')
    df = df.merge(products, on='product_id', how='left')
    df = df.merge(sellers, on='seller_id', how='left')
    df = df.merge(pay_agg, on='order_id', how='left')
    df = df.merge(reviews, on='order_id', how='left')

    df = df.merge(
        geo_agg.rename(columns={
            'geolocation_zip_code_prefix': 'customer_zip_code_prefix',
            'geo_lat_mean': 'customer_geo_lat_mean',
            'geo_lng_mean': 'customer_geo_lng_mean',
        }), on='customer_zip_code_prefix', how='left'
    )
    df = df.merge(
        geo_agg.rename(columns={
            'geolocation_zip_code_prefix': 'seller_zip_code_prefix',
            'geo_lat_mean': 'seller_geo_lat_mean',
            'geo_lng_mean': 'seller_geo_lng_mean',
        }), on='seller_zip_code_prefix', how='left'
    )

    for c in ['order_purchase_timestamp','order_approved_at','order_delivered_carrier_date',
              'order_delivered_customer_date','order_estimated_delivery_date','review_creation_date']:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce')

    return df

@st.cache_data(show_spinner=False)
def load_brazil_geo():
    url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson"
    gdf = gpd.read_file(url)
    gdf = gdf[['sigla', 'geometry']]
    return gdf

@st.cache_data(show_spinner=False)
def dedup_reviews(b: pd.DataFrame) -> pd.DataFrame:
    cols = ['order_id','order_status','review_score','review_comment_title',
            'review_comment_message','review_creation_date','order_purchase_timestamp']
    r = b[cols].copy()
    r.sort_values(['order_id','review_creation_date'], inplace=True)
    r = r.drop_duplicates('order_id', keep='last')
    return r

# Meses em portugues
MESES_PT = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
            7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}

def fmt_mes_ano(ts):
    return f"{MESES_PT[ts.month]}/{ts.year}"

# ============================================================
# Sidebar - Filtros + Navegacao
# ============================================================
st.sidebar.markdown("### Filtros")

df = load_data()
missing = [c for c in REQ_COLS if c not in df.columns]
if missing:
    st.error(f"Colunas ausentes: {missing}")
    st.stop()

min_d = df['order_purchase_timestamp'].min()
max_d = df['order_purchase_timestamp'].max()
default_start = dt.date(min_d.year, min_d.month, 1) if pd.notna(min_d) else dt.date(2016, 1, 1)
default_end   = max_d.date() if pd.notna(max_d) else dt.date.today()

col_s, col_e = st.sidebar.columns(2)
start_date = col_s.date_input("Data inicial", value=default_start,
                               min_value=dt.date(2016,1,1), max_value=dt.date.today(),
                               format="DD/MM/YYYY")
end_date   = col_e.date_input("Data final", value=default_end,
                               min_value=dt.date(2016,1,1), max_value=dt.date.today(),
                               format="DD/MM/YYYY")
start_ts = pd.to_datetime(start_date)
end_ts   = pd.to_datetime(end_date) + pd.offsets.Day(1) - pd.offsets.Second(1)

only_delivered = st.sidebar.toggle("Somente pedidos entregues", value=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### Analises")
PAGES = [
    "1) Tempo de Entrega",
    "2) Vendas e Pagamentos",
    "3) Satisfacao do Cliente",
    "4) Prazo x Satisfacao",
    "5) Categorias de Produtos",
    "6) Frete",
    "7) Geografia",
    "8) Atrasos x Estados",
    "9) Recompra",
]
page = st.sidebar.radio("Selecione", PAGES, label_visibility="collapsed")

# Filtros globais
base = df.copy()
base = base[(base['order_purchase_timestamp'] >= start_ts) & (base['order_purchase_timestamp'] <= end_ts)]
if only_delivered:
    base = base[base['order_status'] == 'delivered']

# ============================================================
# 1) Tempo de entrega
# ============================================================
if page == PAGES[0]:
    st.subheader("1) Qual e o tempo medio/mediano desde a aprovacao do pedido ate a entrega?")
    b = base.copy()
    m = b['order_approved_at'].notna() & b['order_delivered_customer_date'].notna()
    lead = b.loc[m, ['order_id','order_approved_at','order_delivered_customer_date']].drop_duplicates('order_id')
    lead['dias'] = (lead['order_delivered_customer_date'] - lead['order_approved_at']).dt.total_seconds() / 86400
    lead = lead[lead['dias'] >= 0]

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Pedidos", fmt_br(lead['order_id'].nunique()))
    if not lead.empty:
        k2.metric("Media (dias)", fmt_br(lead['dias'].mean(), 1))
        k3.metric("Mediana (dias)", fmt_br(lead['dias'].median(), 1))
        k4.metric("P90 (dias)", fmt_br(lead['dias'].quantile(.90), 1))
        k5.metric("P95 (dias)", fmt_br(lead['dias'].quantile(.95), 1))

        bins = [0, 5, 10, 15, 20, 25, 30, 40, 50, float('inf')]
        labels = ['0-5','6-10','11-15','16-20','21-25','26-30','31-40','41-50','50+']
        lead['faixa_dias'] = pd.cut(lead['dias'], bins=bins, labels=labels, right=True)
        faixa_df = lead['faixa_dias'].value_counts().sort_index().reset_index()
        faixa_df.columns = ['Faixa (dias)', 'Quantidade de pedidos']
        fig = styled_bar(faixa_df, 'Faixa (dias)', 'Quantidade de pedidos',
                         'Distribuicao do tempo de entrega por faixa de dias',
                         text='Quantidade de pedidos')
        fig.update_traces(texttemplate="%{text:,}", textposition='outside')
        fig.update_layout(xaxis_title='Faixa de dias', yaxis_title='Quantidade de pedidos')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados suficientes no filtro atual.")

# ============================================================
# 2) Vendas & Pagamentos
# ============================================================
elif page == PAGES[1]:
    st.subheader("2) Mes com maior quantidade de vendas e maiores pagamentos")
    b = df.copy()
    b = b[(b['order_purchase_timestamp'] >= start_ts) & (b['order_purchase_timestamp'] <= end_ts)]
    b['ano_mes'] = b['order_purchase_timestamp'].dt.to_period('M').dt.to_timestamp()
    pedidos_mes = b.groupby('ano_mes')['order_id'].nunique().reset_index(name='pedidos')

    orders_ded = b.sort_values('order_purchase_timestamp').drop_duplicates('order_id')
    pagamentos_mes = (orders_ded.groupby(orders_ded['order_purchase_timestamp'].dt.to_period('M').dt.to_timestamp())
                      ['payment_value_total'].sum().reset_index(name='pagamentos'))

    c1, c2 = st.columns(2)
    if not pedidos_mes.empty:
        fig1 = styled_bar(pedidos_mes, 'ano_mes', 'pedidos', 'Pedidos por mes (quantidade)')
        fig1.update_layout(xaxis_title='Mes', yaxis_title='Quantidade de pedidos')
        c1.plotly_chart(fig1, use_container_width=True)
        top_p = pedidos_mes.sort_values('pedidos', ascending=False).head(1)
        st.caption(f"Mes com mais pedidos: **{fmt_mes_ano(top_p['ano_mes'].iloc[0])}** - "
                   f"**{fmt_br(top_p['pedidos'].iloc[0])}**")
    if not pagamentos_mes.empty:
        fig2 = styled_bar(pagamentos_mes, 'order_purchase_timestamp', 'pagamentos',
                          'Pagamentos por mes (R$)')
        fig2.update_layout(xaxis_title='Mes', yaxis_title='Valor (R$)')
        c2.plotly_chart(fig2, use_container_width=True)
        top_r = pagamentos_mes.sort_values('pagamentos', ascending=False).head(1)
        st.caption(f"Mes com maior faturamento: **{fmt_mes_ano(top_r['order_purchase_timestamp'].iloc[0])}** - "
                   f"**{fmt_brl(top_r['pagamentos'].iloc[0])}**")

    # Tabela resumo mensal
    st.markdown("---")
    st.markdown("#### Resumo mensal")
    resumo = pedidos_mes.copy()
    resumo = resumo.merge(pagamentos_mes, left_on='ano_mes', right_on='order_purchase_timestamp', how='outer')
    resumo['Mes'] = resumo['ano_mes'].apply(fmt_mes_ano)
    resumo = resumo[['Mes','pedidos','pagamentos']].sort_values('Mes', ascending=False)
    resumo.columns = ['Mes', 'Pedidos', 'Pagamentos (R$)']
    resumo['Pagamentos (R$)'] = resumo['Pagamentos (R$)'].apply(lambda v: fmt_brl(v) if pd.notna(v) else '-')
    resumo['Pedidos'] = resumo['Pedidos'].apply(lambda v: fmt_br(v) if pd.notna(v) else '-')
    st.dataframe(resumo, hide_index=True, use_container_width=True)

# ============================================================
# 3) Satisfacao
# ============================================================
elif page == PAGES[2]:
    st.subheader("3) Satisfacao do cliente - notas e comentarios")
    r = dedup_reviews(base)
    with_reviews = r[r['review_score'].notna()].copy()

    total_ped = r['order_id'].nunique()
    total_rev = with_reviews['order_id'].nunique()
    cobertura = (total_rev / total_ped * 100) if total_ped else np.nan

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pedidos", fmt_br(total_ped))
    c2.metric("Avaliacoes", fmt_br(total_rev))
    c3.metric("Cobertura", f"{fmt_br(cobertura, 1)}%" if pd.notna(cobertura) else '-')
    c4.metric("Media", fmt_br(with_reviews['review_score'].mean(), 2) if total_rev else '-')
    c5.metric("Mediana", fmt_br(with_reviews['review_score'].median(), 0) if total_rev else '-')

    if total_rev:
        dist = with_reviews['review_score'].value_counts().sort_index().reset_index()
        dist.columns = ['Nota', 'Quantidade']
        dist['pct'] = (dist['Quantidade'] / dist['Quantidade'].sum() * 100).round(1)
        fig = styled_bar(dist, 'Nota', 'Quantidade', 'Distribuicao das notas (1 a 5)', text='pct')
        fig.update_traces(texttemplate="%{text}%")
        fig.update_layout(xaxis_title='Nota', yaxis_title='Quantidade de avaliacoes')
        st.plotly_chart(fig, use_container_width=True)

        with_reviews['has_comment'] = (with_reviews['review_comment_title'].apply(has_text)
                                       | with_reviews['review_comment_message'].apply(has_text))
        com = int(with_reviews['has_comment'].sum())
        sem = total_rev - com
        pie = px.pie(
            pd.DataFrame({'Tipo': ['Com comentario', 'Sem comentario'], 'Quantidade': [com, sem]}),
            names='Tipo', values='Quantidade', hole=0.55,
            title='Taxa de comentarios nas avaliacoes',
            color_discrete_sequence=PAIR,
        )
        pie.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(pie, use_container_width=True)

        with_reviews['bucket'] = pd.cut(with_reviews['review_score'], bins=[0, 2, 3, 5],
                                        labels=['Negativa (<=2)', 'Neutra (=3)', 'Positiva (>=4)'])
        tb = with_reviews.groupby('bucket', observed=False).agg(
            total_avaliacoes=('order_id', 'count'),
            com_comentario=('has_comment', 'sum'),
        ).reset_index()
        tb['com_comentario'] = tb['com_comentario'].astype(int)
        tb['sem_comentario'] = tb['total_avaliacoes'] - tb['com_comentario']
        tb['% que comentou'] = (tb['com_comentario'] / tb['total_avaliacoes'] * 100).round(1)
        tb.columns = ['Faixa de nota', 'Total de avaliacoes', 'Com comentario', 'Sem comentario', '% que comentou']
        st.markdown("**Dos clientes que avaliaram, quantos deixaram comentario?**")
        st.dataframe(tb, hide_index=True, use_container_width=True)

# ============================================================
# 4) Prazo x Satisfacao
# ============================================================
elif page == PAGES[3]:
    st.subheader("4) Padrao entre satisfacao e entrega antes/depois do prazo")
    cols_sel = ['order_id','order_delivered_customer_date','order_estimated_delivery_date',
                'review_score','review_creation_date']
    b = base[cols_sel].copy()
    b.sort_values(['order_id','review_creation_date'], inplace=True)
    b = b.drop_duplicates('order_id', keep='last')
    b = b[b['order_delivered_customer_date'].notna() & b['order_estimated_delivery_date'].notna()
          & b['review_score'].notna()]
    b['delta_dias'] = (b['order_delivered_customer_date'] - b['order_estimated_delivery_date']).dt.total_seconds() / 86400
    b['classe_prazo'] = np.where(b['delta_dias'] > 0, 'Atraso',
                         np.where(b['delta_dias'] < 0, 'Adiantado', 'No prazo'))

    g = b.groupby('classe_prazo')['review_score'].agg(['count','mean','median']).reset_index()

    cols_m = st.columns(min(len(g), 3))
    for i, row in g.iterrows():
        if i < len(cols_m):
            cols_m[i].metric(row['classe_prazo'],
                             f"{fmt_br(row['count'])} aval. | media {fmt_br(row['mean'], 2)}")

    fig = styled_bar(g.sort_values('mean', ascending=False), 'classe_prazo', 'mean',
                     'Nota media por classe de prazo', text='mean')
    fig.update_traces(texttemplate="%{text:.2f}")
    fig.update_layout(xaxis_title='Classe de prazo', yaxis_title='Nota media')
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Distribuicao das notas por classe de prazo:**")
    cross = b.groupby(['classe_prazo','review_score']).size().reset_index(name='Quantidade')
    fig2 = px.bar(cross, x='review_score', y='Quantidade', color='classe_prazo', barmode='group',
                  title='Notas por classe de prazo', color_discrete_sequence=TEAL)
    fig2.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                       xaxis_title='Nota', yaxis_title='Quantidade', separators=",.")
    st.plotly_chart(fig2, use_container_width=True)

# ============================================================
# 5) Categorias
# ============================================================
elif page == PAGES[4]:
    st.subheader("5) Categorias mais/menos vendidas e relacao com preco")

    # Base: aplica filtro de data, mas NAO filtra por status (usuario escolhe)
    cat_base = df.copy()
    cat_base = cat_base[(cat_base['order_purchase_timestamp'] >= start_ts)
                        & (cat_base['order_purchase_timestamp'] <= end_ts)]

    # Filtro de status
    status_list = sorted(cat_base['order_status'].dropna().unique().tolist())
    status_sel = st.multiselect(
        "Filtrar por status do pedido:",
        options=status_list,
        default=status_list,
        help="Selecione um ou mais status. Por padrao todos sao exibidos."
    )
    if status_sel:
        cat_base = cat_base[cat_base['order_status'].isin(status_sel)]

    cat = cat_base[['order_id','order_item_id','product_category_name','price',
                     'product_photos_qty','order_status']].copy()

    agg = cat.groupby('product_category_name').agg(
        itens=('order_item_id','count'), pedidos=('order_id','nunique'),
        preco_medio=('price','mean'), preco_mediano=('price','median'),
        fotos_med=('product_photos_qty','mean')
    ).reset_index()

    top10 = agg.sort_values('itens', ascending=False).head(10)
    bot10 = agg.sort_values('itens', ascending=True).head(10)

    c1, c2 = st.columns(2)
    fig1 = styled_bar(top10, 'product_category_name', 'itens', 'Top 10 categorias por itens vendidos')
    fig1.update_layout(xaxis_title='Categoria', yaxis_title='Itens vendidos')
    c1.plotly_chart(fig1, use_container_width=True)
    fig2 = styled_bar(bot10, 'product_category_name', 'itens', 'Bottom 10 categorias por itens vendidos')
    fig2.update_layout(xaxis_title='Categoria', yaxis_title='Itens vendidos')
    c2.plotly_chart(fig2, use_container_width=True)

    # Tabela detalhada
    st.markdown("---")
    st.markdown("#### Detalhamento das Top 10 categorias")
    tab_cat = top10[['product_category_name','itens','pedidos','preco_medio','preco_mediano','fotos_med']].copy()
    tab_cat.columns = ['Categoria', 'Itens vendidos', 'Pedidos', 'Preco medio (R$)', 'Preco mediano (R$)', 'Fotos (media)']
    tab_cat['Preco medio (R$)'] = tab_cat['Preco medio (R$)'].apply(lambda v: fmt_brl(v))
    tab_cat['Preco mediano (R$)'] = tab_cat['Preco mediano (R$)'].apply(lambda v: fmt_brl(v))
    tab_cat['Itens vendidos'] = tab_cat['Itens vendidos'].apply(lambda v: fmt_br(v))
    tab_cat['Pedidos'] = tab_cat['Pedidos'].apply(lambda v: fmt_br(v))
    tab_cat['Fotos (media)'] = tab_cat['Fotos (media)'].round(1)
    st.dataframe(tab_cat, hide_index=True, use_container_width=True)

    # Grafico comparativo por status
    st.markdown("---")
    st.markdown("#### Top 10 categorias por status do pedido")
    top10_cats = top10['product_category_name'].tolist()
    cat_status = cat[cat['product_category_name'].isin(top10_cats)].copy()
    cat_status_agg = (cat_status.groupby(['product_category_name', 'order_status'])['order_item_id']
                      .count().reset_index(name='itens'))
    fig_status = px.bar(
        cat_status_agg, x='product_category_name', y='itens',
        color='order_status', barmode='group',
        title='Top 10 categorias - Itens por status do pedido',
        color_discrete_sequence=TEAL + ['#e74c3c', '#f39c12', '#3498db', '#9b59b6'],
    )
    fig_status.update_layout(
        xaxis_title='Categoria', yaxis_title='Itens vendidos',
        legend_title_text='Status',
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        separators=",.",
    )
    st.plotly_chart(fig_status, use_container_width=True)

    # Tabela resumo por status
    pivot = cat_status_agg.pivot_table(
        index='product_category_name', columns='order_status',
        values='itens', fill_value=0, aggfunc='sum'
    ).reset_index()
    pivot.rename(columns={'product_category_name': 'Categoria'}, inplace=True)
    # Formatar valores
    for col in pivot.columns[1:]:
        pivot[col] = pivot[col].apply(lambda v: fmt_br(v))
    st.dataframe(pivot, hide_index=True, use_container_width=True)

# ============================================================
# 6) Frete
# ============================================================
elif page == PAGES[5]:
    st.subheader("6) O volume e o peso dos produtos impactam no frete?")
    fr = base[['freight_value','product_weight_g','product_length_cm',
               'product_height_cm','product_width_cm']].dropna()
    fr = fr[(fr['product_weight_g'] > 0) & (fr['product_length_cm'] > 0)
            & (fr['product_height_cm'] > 0) & (fr['product_width_cm'] > 0)]
    fr['volume_cm3'] = fr['product_length_cm'] * fr['product_height_cm'] * fr['product_width_cm']

    if not fr.empty:
        rho_w = fr[['freight_value','product_weight_g']].corr(method='spearman').iloc[0,1]
        rho_v = fr[['freight_value','volume_cm3']].corr(method='spearman').iloc[0,1]
        c1, c2 = st.columns(2)
        c1.metric("Correlacao Spearman (peso x frete)", fmt_br(rho_w, 3))
        c2.metric("Correlacao Spearman (volume x frete)", fmt_br(rho_v, 3))

        sample = fr.sample(min(5000, len(fr)), random_state=42)
        g1, g2 = st.columns(2)
        fig1 = px.scatter(sample, x='product_weight_g', y='freight_value', trendline='ols',
                          title='Frete x Peso (amostra)', color_discrete_sequence=['#1d7874'], opacity=0.4)
        fig2 = px.scatter(sample, x='volume_cm3', y='freight_value', trendline='ols',
                          title='Frete x Volume (amostra)', color_discrete_sequence=['#1d7874'], opacity=0.4)
        for fg in [fig1, fig2]:
            fg.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                             separators=",.",
                             xaxis_title='Peso (g)' if fg == fig1 else 'Volume (cm3)',
                             yaxis_title='Valor do frete (R$)')
        g1.plotly_chart(fig1, use_container_width=True)
        g2.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Sem dados de frete/peso/volume no filtro atual.")

# ============================================================
# 7) Geografia
# ============================================================
elif page == PAGES[6]:
    st.subheader("7) Concentracao geografica de clientes e vendedores")
    geo_base = df[['order_id','customer_state','seller_state']].drop_duplicates('order_id')
    orders_period = df[['order_id','order_purchase_timestamp']].drop_duplicates('order_id')
    orders_period = orders_period[(orders_period['order_purchase_timestamp'] >= start_ts)
                                  & (orders_period['order_purchase_timestamp'] <= end_ts)]
    geo_base = geo_base[geo_base['order_id'].isin(orders_period['order_id'])]

    cli = geo_base['customer_state'].value_counts().reset_index()
    cli.columns = ['UF', 'Quantidade']
    ven = geo_base['seller_state'].value_counts().reset_index()
    ven.columns = ['UF', 'Quantidade']

    # Barras
    st.markdown("#### Graficos de barras")
    c1, c2 = st.columns(2)
    fig1 = styled_bar(cli.head(15), 'UF', 'Quantidade', 'Clientes por UF (Top 15)')
    fig1.update_layout(xaxis_title='Estado', yaxis_title='Quantidade de pedidos')
    c1.plotly_chart(fig1, use_container_width=True)
    fig2 = styled_bar(ven.head(15), 'UF', 'Quantidade', 'Vendedores por UF (Top 15)')
    fig2.update_layout(xaxis_title='Estado', yaxis_title='Quantidade de pedidos')
    c2.plotly_chart(fig2, use_container_width=True)

    # Tabelas
    st.markdown("---")
    st.markdown("#### Dados por UF")
    tc1, tc2 = st.columns(2)
    cli_tab = cli.copy()
    cli_tab['Quantidade'] = cli_tab['Quantidade'].apply(fmt_br)
    cli_tab.columns = ['UF', 'Pedidos (clientes)']
    tc1.dataframe(cli_tab, hide_index=True, use_container_width=True)
    ven_tab = ven.copy()
    ven_tab['Quantidade'] = ven_tab['Quantidade'].apply(fmt_br)
    ven_tab.columns = ['UF', 'Pedidos (vendedores)']
    tc2.dataframe(ven_tab, hide_index=True, use_container_width=True)

    # Mapa do Brasil
    st.markdown("---")
    st.markdown("#### Mapa do Brasil")
    brazil_geo = load_brazil_geo()
    geojson = json.loads(brazil_geo.to_json())

    c1m, c2m = st.columns(2)
    fig_map_cli = px.choropleth(
        cli, geojson=geojson, locations='UF',
        featureidkey='properties.sigla', color='Quantidade',
        color_continuous_scale='Teal', title='Clientes por UF',
    )
    fig_map_cli.update_geos(fitbounds="locations", visible=False)
    fig_map_cli.update_layout(margin=dict(l=0, r=0, t=40, b=0), paper_bgcolor='rgba(0,0,0,0)')
    c1m.plotly_chart(fig_map_cli, use_container_width=True)

    fig_map_ven = px.choropleth(
        ven, geojson=geojson, locations='UF',
        featureidkey='properties.sigla', color='Quantidade',
        color_continuous_scale='Teal', title='Vendedores por UF',
    )
    fig_map_ven.update_geos(fitbounds="locations", visible=False)
    fig_map_ven.update_layout(margin=dict(l=0, r=0, t=40, b=0), paper_bgcolor='rgba(0,0,0,0)')
    c2m.plotly_chart(fig_map_ven, use_container_width=True)

# ============================================================
# 8) Atrasos x Estados
# ============================================================
elif page == PAGES[7]:
    st.subheader("8) Atrasos acontecem mais entre estados diferentes?")
    a = (df[['order_id','customer_state','seller_state','order_status',
             'order_delivered_customer_date','order_estimated_delivery_date',
             'order_purchase_timestamp']]
         .drop_duplicates('order_id'))
    a = a[(a['order_purchase_timestamp'] >= start_ts) & (a['order_purchase_timestamp'] <= end_ts)]
    a = a[(a['order_status'] == 'delivered')
          & a['order_delivered_customer_date'].notna()
          & a['order_estimated_delivery_date'].notna()]
    a['late'] = (a['order_delivered_customer_date'] > a['order_estimated_delivery_date']).astype(int)
    a['mesma_uf'] = (a['customer_state'] == a['seller_state'])

    st.markdown("#### Atraso por UF")
    cust = a.groupby('customer_state')['late'].mean().mul(100).round(2).sort_values(ascending=False).reset_index(name='atraso_%')
    sell = a.groupby('seller_state')['late'].mean().mul(100).round(2).sort_values(ascending=False).reset_index(name='atraso_%')
    c1, c2 = st.columns(2)
    fig1 = styled_bar(cust.head(15), 'customer_state', 'atraso_%', 'Atraso % por UF do cliente')
    fig1.update_layout(xaxis_title='Estado do cliente', yaxis_title='% de atraso')
    c1.plotly_chart(fig1, use_container_width=True)
    fig2 = styled_bar(sell.head(15), 'seller_state', 'atraso_%', 'Atraso % por UF do vendedor')
    fig2.update_layout(xaxis_title='Estado do vendedor', yaxis_title='% de atraso')
    c2.plotly_chart(fig2, use_container_width=True)

    # Tabelas
    st.markdown("---")
    st.markdown("#### Tabelas de atraso por UF")
    tc1, tc2 = st.columns(2)
    cust_tab = cust.copy()
    cust_tab['atraso_%'] = cust_tab['atraso_%'].apply(lambda v: fmt_br(v, 2))
    cust_tab.columns = ['UF Cliente', 'Atraso (%)']
    tc1.dataframe(cust_tab, hide_index=True, use_container_width=True)
    sell_tab = sell.copy()
    sell_tab['atraso_%'] = sell_tab['atraso_%'].apply(lambda v: fmt_br(v, 2))
    sell_tab.columns = ['UF Vendedor', 'Atraso (%)']
    tc2.dataframe(sell_tab, hide_index=True, use_container_width=True)

    # Inter-estadual vs Intra-estadual
    st.markdown("---")
    st.markdown("#### Entregas inter-estaduais vs intra-estaduais")
    inter_intra = a.groupby('mesma_uf').agg(
        total=('order_id','count'),
        atrasados=('late','sum'),
        pct_atraso=('late','mean')
    ).reset_index()
    inter_intra['pct_atraso'] = (inter_intra['pct_atraso'] * 100).round(2)
    inter_intra['tipo'] = inter_intra['mesma_uf'].map({True: 'Mesma UF', False: 'UFs diferentes'})

    k1, k2, k3 = st.columns(3)
    for _, row in inter_intra.iterrows():
        col = k1 if row['mesma_uf'] else k2
        col.metric(f"{row['tipo']}", f"{fmt_br(row['pct_atraso'], 1)}% atraso",
                   delta=f"{fmt_br(row['atrasados'])} de {fmt_br(row['total'])}")
    diff_mesma = inter_intra.loc[inter_intra['mesma_uf'], 'pct_atraso'].values
    diff_outra = inter_intra.loc[~inter_intra['mesma_uf'], 'pct_atraso'].values
    if len(diff_mesma) and len(diff_outra):
        k3.metric("Diferenca (pp)", f"{fmt_br(diff_outra[0] - diff_mesma[0], 1)} pp")

    fig = px.bar(inter_intra, x='tipo', y='pct_atraso', text='pct_atraso',
                 title='Taxa de atraso: mesma UF vs UFs diferentes',
                 color='tipo', color_discrete_sequence=PAIR)
    fig.update_traces(texttemplate="%{text:.1f}%", textposition='outside')
    fig.update_layout(showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                      xaxis_title='Tipo de rota', yaxis_title='% de atraso', separators=",.")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Top 10 rotas (cliente UF <- vendedor UF) com mais atrasos:**")
    routes = (a[a['late'] == 1]
              .groupby(['customer_state','seller_state'])['order_id'].count()
              .sort_values(ascending=False).head(10).reset_index(name='Atrasos'))
    routes['Rota'] = routes['customer_state'] + ' <- ' + routes['seller_state']
    fig_r = styled_bar(routes, 'Rota', 'Atrasos', 'Top 10 rotas com mais atrasos')
    fig_r.update_layout(xaxis_title='Rota (cliente <- vendedor)', yaxis_title='Quantidade de atrasos')
    st.plotly_chart(fig_r, use_container_width=True)

# ============================================================
# 9) Recompra
# ============================================================
elif page == PAGES[8]:
    st.subheader("9) Perfil dos clientes que fizeram recompra")
    r = (df[['order_id','customer_unique_id','order_purchase_timestamp',
             'order_delivered_customer_date','order_estimated_delivery_date',
             'review_score','payment_type_first','payment_installments_max',
             'product_category_name','customer_state','customer_city']]
         .drop_duplicates('order_id').copy())
    r = r[(r['order_purchase_timestamp'] >= start_ts) & (r['order_purchase_timestamp'] <= end_ts)]
    counts = r.groupby('customer_unique_id')['order_id'].nunique()
    r = r.merge(counts.rename('n_orders_customer'), left_on='customer_unique_id', right_index=True)
    r['is_repeat'] = r['n_orders_customer'] > 1
    r['on_time'] = np.where(
        r['order_delivered_customer_date'].isna() | r['order_estimated_delivery_date'].isna(),
        np.nan,
        (r['order_delivered_customer_date'] <= r['order_estimated_delivery_date']).astype(float)
    )

    k1, k2 = st.columns(2)
    repeat_rate = r.drop_duplicates('customer_unique_id')['is_repeat'].mean() * 100
    k1.metric("Taxa de recompra (clientes com >1 pedido)", f"{fmt_br(repeat_rate, 2)}%")

    comp = r.groupby('is_repeat').agg(
        nota_media=('review_score', 'mean'),
        pct_no_prazo=('on_time', lambda s: float(np.nanmean(s)) * 100),
        parcelas_med=('payment_installments_max', 'mean'),
        pedidos=('order_id', 'count')
    ).reset_index()
    comp['is_repeat'] = comp['is_repeat'].map({True: 'Recorrente', False: 'Unico'})
    comp.columns = ['Tipo', 'Nota media', '% no prazo', 'Parcelas (media)', 'Pedidos']
    comp['Nota media'] = comp['Nota media'].apply(lambda v: fmt_br(v, 2))
    comp['% no prazo'] = comp['% no prazo'].apply(lambda v: f"{fmt_br(v, 1)}%")
    comp['Parcelas (media)'] = comp['Parcelas (media)'].apply(lambda v: fmt_br(v, 1))
    comp['Pedidos'] = comp['Pedidos'].apply(lambda v: fmt_br(v))
    k2.dataframe(comp, hide_index=True)

    # Meios de pagamento
    st.markdown("---")
    st.markdown("#### Meios de pagamento")
    mix = r.groupby(['is_repeat','payment_type_first'])['order_id'].count().reset_index(name='count')
    totals = mix.groupby('is_repeat')['count'].transform('sum')
    mix['share'] = (mix['count'] / totals * 100).round(2)
    mix['Grupo'] = mix['is_repeat'].map({True: 'Recorrente', False: 'Unico'})

    fig = px.bar(mix, x='payment_type_first', y='share', color='Grupo', barmode='group',
                 title='Mix de pagamento por grupo', color_discrete_sequence=PAIR)
    fig.update_layout(yaxis_title='%', xaxis_title='Meio de pagamento',
                      plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', separators=",.")
    st.plotly_chart(fig, use_container_width=True)

    # Localizacao
    st.markdown("---")
    st.markdown("#### Localizacao dos clientes")
    loc = (r.groupby(['is_repeat','customer_state'])['order_id'].count()
           .reset_index(name='Pedidos'))
    c1, c2 = st.columns(2)
    rep_loc = loc[loc['is_repeat']].sort_values('Pedidos', ascending=False).head(10)
    uni_loc = loc[~loc['is_repeat']].sort_values('Pedidos', ascending=False).head(10)
    fig1 = styled_bar(rep_loc, 'customer_state', 'Pedidos', 'Top UFs - Recorrentes')
    fig1.update_layout(xaxis_title='Estado', yaxis_title='Quantidade de pedidos')
    c1.plotly_chart(fig1, use_container_width=True)
    fig2 = styled_bar(uni_loc, 'customer_state', 'Pedidos', 'Top UFs - Unicos')
    fig2.update_layout(xaxis_title='Estado', yaxis_title='Quantidade de pedidos')
    c2.plotly_chart(fig2, use_container_width=True)

    # Categorias
    st.markdown("---")
    st.markdown("#### Categorias de produto preferidas")
    cat_rep = (r.groupby(['is_repeat','product_category_name'])['order_id'].count()
               .reset_index(name='Pedidos'))
    c3, c4 = st.columns(2)
    rep_cat = cat_rep[cat_rep['is_repeat']].sort_values('Pedidos', ascending=False).head(10)
    uni_cat = cat_rep[~cat_rep['is_repeat']].sort_values('Pedidos', ascending=False).head(10)
    fig3 = styled_bar(rep_cat, 'product_category_name', 'Pedidos', 'Top categorias - Recorrentes')
    fig3.update_layout(xaxis_title='Categoria', yaxis_title='Quantidade de pedidos')
    c3.plotly_chart(fig3, use_container_width=True)
    fig4 = styled_bar(uni_cat, 'product_category_name', 'Pedidos', 'Top categorias - Unicos')
    fig4.update_layout(xaxis_title='Categoria', yaxis_title='Quantidade de pedidos')
    c4.plotly_chart(fig4, use_container_width=True)

# ============================================================
st.caption("DASHBOARD OLIST | Dados em Tempo Real")
