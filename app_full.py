# app_full.py
# Streamlit dashboard cobrindo os 9 desafios sobre a base Olist (flat)
# Lê o arquivo olist_consolidado_flat.xlsx (ou upload) e calcula tudo on-the-fly.

import io
import os
import datetime as dt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Desafios 1–9 • Olist", page_icon="📊", layout="wide")
st.title("📊 Dashboard – Desafios 1 a 9 (Olist)")
st.caption("Base: olist_consolidado_flat.xlsx (por item); deduplicação por pedido aplicada conforme o caso.")

# =========================
# Utilidades & Carga de dados
# =========================
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

def has_text(x:str) -> bool:
    if x is None:
        return False
    try:
        return len(str(x).strip()) > 0
    except Exception:
        return False

@st.cache_data(show_spinner=False)
def load_data(uploaded=None, default_path='olist_consolidado_flat.xlsx'):
    if uploaded is not None:
        data = uploaded.read()
        df = pd.read_excel(io.BytesIO(data), engine='openpyxl')
    else:
        if not os.path.exists(default_path):
            st.warning("Envie o Excel (.xlsx) no menu lateral ou coloque 'olist_consolidado_flat.xlsx' na mesma pasta do app.")
            st.stop()
        df = pd.read_excel(default_path, engine='openpyxl')
    # parse datas
    for c in ['order_purchase_timestamp','order_approved_at','order_delivered_carrier_date',
              'order_delivered_customer_date','order_estimated_delivery_date','review_creation_date']:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce')
    return df

# =========================
# Sidebar – Upload & Filtros globais
# =========================
st.sidebar.header("Configurações")
uploaded = st.sidebar.file_uploader("Envie o Excel (.xlsx)", type=["xlsx"]) 
df = load_data(uploaded)

# Checagem de colunas
missing = [c for c in REQ_COLS if c not in df.columns]
if missing:
    st.error(f"Colunas ausentes no arquivo: {missing}")
    st.stop()

# Filtro global de período por mês de compra
min_d = pd.to_datetime(df['order_purchase_timestamp']).min()
max_d = pd.to_datetime(df['order_purchase_timestamp']).max()
if pd.notna(min_d) and pd.notna(max_d):
    default_range = (dt.date(min_d.year, min_d.month, 1), max_d.date())
else:
    default_range = (dt.date(2016,1,1), dt.date.today())

sel_range = st.sidebar.date_input(
    "Período (mês da compra)", value=default_range,
    min_value=dt.date(2016,1,1), max_value=dt.date.today()
)
if isinstance(sel_range, (list,tuple)) and len(sel_range)==2:
    start_ts = pd.to_datetime(sel_range[0])
    end_ts   = pd.to_datetime(sel_range[1]) + pd.offsets.Day(1) - pd.offsets.Second(1)
else:
    start_ts, end_ts = None, None

st.sidebar.markdown("**Escopo de status**")
only_delivered = st.sidebar.toggle("Somente pedidos entregues", value=True)

# Aplicar filtros globais
base = df.copy()
if start_ts is not None and end_ts is not None:
    base = base[(base['order_purchase_timestamp']>=start_ts) & (base['order_purchase_timestamp']<=end_ts)]
if only_delivered:
    base = base[base['order_status']=='delivered']

# Função auxiliar: base deduplicada por pedido mantendo avaliação mais recente
@st.cache_data(show_spinner=False)
def dedup_reviews(b: pd.DataFrame) -> pd.DataFrame:
    cols = ['order_id','order_status','review_score','review_comment_title','review_comment_message','review_creation_date','order_purchase_timestamp']
    r = b[cols].copy()
    r.sort_values(['order_id','review_creation_date'], inplace=True)
    r = r.drop_duplicates('order_id', keep='last')
    return r

# =========================
# TABS (1..9)
# =========================
(t1,t2,t3,t4,t5,t6,t7,t8,t9) = st.tabs([
    "1) Tempo de entrega",
    "2) Vendas & Pagamentos",
    "3) Satisfação",
    "4) Prazo × Satisfação",
    "5) Categorias",
    "6) Frete",
    "7) Geografia",
    "8) Atrasos × Estados",
    "9) Recompra",
])

# =====================================
# 1) Tempo de entrega (aprovação → entrega)
# =====================================
with t1:
    st.subheader("1) Tempo de entrega — aprovação → entrega do cliente")
    b = df.copy() if not only_delivered else base.copy()
    m = (b['order_approved_at'].notna()) & (b['order_delivered_customer_date'].notna())
    lead = b.loc[m, ['order_id','order_approved_at','order_delivered_customer_date']].drop_duplicates('order_id')
    lead['dias'] = (lead['order_delivered_customer_date'] - lead['order_approved_at']).dt.total_seconds()/86400
    lead = lead[lead['dias']>=0]

    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Pedidos (amostra)", f"{lead['order_id'].nunique():,}")
    if not lead.empty:
        k2.metric("Média (dias)", f"{lead['dias'].mean():.2f}")
        k3.metric("Mediana (dias)", f"{lead['dias'].median():.2f}")
        k4.metric("P90 (dias)", f"{lead['dias'].quantile(0.90):.2f}")
        k5.metric("P95 (dias)", f"{lead['dias'].quantile(0.95):.2f}")

        fig = px.histogram(lead, x='dias', nbins=50, title='Distribuição do lead time (dias)')
        fig.update_layout(bargap=0.05)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados suficientes no filtro atual.")

# =====================================
# 2) Vendas por mês & Pagamentos
# =====================================
with t2:
    st.subheader("2) Vendas por mês (nº pedidos) e Pagamentos (R$)")
    # Vendas (contagem de order_id únicos por mês da compra)
    b = df.copy()  # aqui consideramos todos os status por padrão nas vendas gerais
    if start_ts is not None and end_ts is not None:
        b = b[(b['order_purchase_timestamp']>=start_ts) & (b['order_purchase_timestamp']<=end_ts)]
    b['ano_mes'] = b['order_purchase_timestamp'].dt.to_period('M').dt.to_timestamp()
    pedidos_mes = b.groupby('ano_mes')['order_id'].nunique().reset_index(name='pedidos')

    # Pagamentos: dedup por pedido e somatório
    orders = b.sort_values('order_purchase_timestamp').drop_duplicates('order_id')
    pagamentos_mes = orders.groupby(orders['order_purchase_timestamp'].dt.to_period('M').dt.to_timestamp())['payment_value_total'].sum().reset_index(name='pagamentos')

    c1,c2 = st.columns(2)
    if not pedidos_mes.empty:
        figp = px.bar(pedidos_mes, x='ano_mes', y='pedidos', title='Pedidos por mês (nº)')
        c1.plotly_chart(figp, use_container_width=True)
        top_p = pedidos_mes.sort_values('pedidos', ascending=False).head(1)
        st.caption(f"Mês com mais pedidos: **{top_p['ano_mes'].dt.strftime('%b/%Y').iloc[0]}** — **{int(top_p['pedidos'].iloc[0]):,}**")
    if not pagamentos_mes.empty:
        figpg = px.bar(pagamentos_mes, x='order_purchase_timestamp', y='pagamentos', title='Pagamentos por mês (R$)')
        c2.plotly_chart(figpg, use_container_width=True)
        top_r = pagamentos_mes.sort_values('pagamentos', ascending=False).head(1)
        st.caption(f"Mês com maior faturamento (pagamentos): **{top_r['order_purchase_timestamp'].dt.strftime('%b/%Y').iloc[0]}** — **R$ {top_r['pagamentos'].iloc[0]:,.2f}**")

# =====================================
# 3) Satisfação: notas e comentários
# =====================================
with t3:
    st.subheader("3) Satisfação do cliente — notas e comentários")
    r = dedup_reviews(base)  # por padrão, escopo de 'base' (respeita 'somente entregues')
    with_reviews = r[r['review_score'].notna()].copy()

    total_ped = r['order_id'].nunique()
    total_rev = with_reviews['order_id'].nunique()
    cobertura = (total_rev/total_ped*100) if total_ped else np.nan

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Pedidos (escopo)", f"{total_ped:,}")
    c2.metric("Avaliações c/ nota", f"{total_rev:,}")
    c3.metric("Cobertura", f"{cobertura:.2f}%" if pd.notna(cobertura) else '-')
    c4.metric("Média da nota", f"{with_reviews['review_score'].mean():.2f}" if total_rev else '-')
    c5.metric("Mediana", f"{with_reviews['review_score'].median():.2f}" if total_rev else '-')

    if total_rev:
        dist = with_reviews['review_score'].value_counts().sort_index().reset_index()
        dist.columns = ['nota','qtd']
        dist['pct'] = (dist['qtd']/dist['qtd'].sum()*100).round(2)
        figb = px.bar(dist, x='nota', y='qtd', text='pct', title='Distribuição das notas (1–5★)')
        figb.update_traces(texttemplate="%{text}%", textposition='outside')
        st.plotly_chart(figb, use_container_width=True)

        with_reviews['has_comment'] = with_reviews['review_comment_title'].apply(has_text) | with_reviews['review_comment_message'].apply(has_text)
        coment_rate = with_reviews['has_comment'].mean()*100
        pie = px.pie(pd.DataFrame({'tipo':['Com comentário','Sem comentário'],
                                    'valor':[with_reviews['has_comment'].sum(), total_rev-with_reviews['has_comment'].sum()]}),
                      names='tipo', values='valor', hole=0.55, title='Taxa de comentários nas avaliações')
        st.plotly_chart(pie, use_container_width=True)

        with_reviews['bucket'] = pd.cut(with_reviews['review_score'], bins=[0,2,3,5], labels=['Negativa (≤2★)','Neutra (=3★)','Positiva (≥4★)'])
        tb = with_reviews.groupby('bucket')['has_comment'].mean().mul(100).round(2).reset_index(name='% com comentário')
        st.dataframe(tb, hide_index=True)

# =====================================
# 4) Prazo × Satisfação
# =====================================
with t4:
    st.subheader("4) Relação: cumprimento de prazo × satisfação")
    cols = ['order_id','order_status','order_delivered_customer_date','order_estimated_delivery_date','review_score','review_creation_date']
    b = df.copy() if not only_delivered else base.copy()
    pxs = b[cols].copy()
    pxs.sort_values(['order_id','review_creation_date'], inplace=True)
    pxs = pxs.drop_duplicates('order_id', keep='last')
    pxs = pxs[(pxs['order_delivered_customer_date'].notna()) & (pxs['order_estimated_delivery_date'].notna()) & (pxs['review_score'].notna())]
    pxs['delta_dias'] = (pxs['order_delivered_customer_date'] - pxs['order_estimated_delivery_date']).dt.total_seconds()/86400
    pxs['classe_prazo'] = np.where(pxs['delta_dias']>1e-9, 'Atraso', np.where(pxs['delta_dias']<-1e-9,'Adiantado','No prazo'))

    g = pxs.groupby('classe_prazo')['review_score'].agg(['count','mean','median']).reset_index()
    c1,c2,c3 = st.columns(3)
    for i,row in g.iterrows():
        c = [c1,c2,c3][i]
        c.metric(f"{row['classe_prazo']}: avaliações", f"{int(row['count']):,}")
    fig = px.bar(g.sort_values('mean', ascending=False), x='classe_prazo', y='mean', text='mean', title='Nota média por classe de prazo')
    fig.update_traces(texttemplate="%{text:.2f}")
    st.plotly_chart(fig, use_container_width=True)

# =====================================
# 5) Categorias (mais/menos vendidas) e relação com preço/fotos
# =====================================
with t5:
    st.subheader("5) Categorias – volume e indicadores")
    cat = base[['order_id','order_item_id','product_category_name','price','product_photos_qty']].copy()
    agg = cat.groupby('product_category_name').agg(
        itens=('order_item_id','count'), pedidos=('order_id','nunique'),
        preco_medio=('price','mean'), preco_mediano=('price','median'),
        fotos_med=('product_photos_qty','mean')
    ).reset_index()
    top5 = agg.sort_values('itens', ascending=False).head(10)
    bot5 = agg.sort_values('itens', ascending=True).head(10)
    c1,c2 = st.columns(2)
    c1.plotly_chart(px.bar(top5, x='product_category_name', y='itens', title='Top categorias por itens'), use_container_width=True)
    c2.plotly_chart(px.bar(bot5, x='product_category_name', y='itens', title='Bottom categorias por itens'), use_container_width=True)

    st.markdown("**Correlação simples (por categoria):**")
    corr_price = agg[['preco_mediano','itens']].corr().iloc[0,1]
    corr_photos = agg[['fotos_med','itens']].corr().iloc[0,1]
    k1,k2 = st.columns(2)
    k1.metric("r(preço mediano, itens)", f"{corr_price:.3f}")
    k2.metric("r(fotos médias, itens)", f"{corr_photos:.3f}")

    c3,c4 = st.columns(2)
    c3.plotly_chart(px.scatter(agg, x='preco_mediano', y='itens', trendline='ols', title='Preço mediano × Itens'), use_container_width=True)
    c4.plotly_chart(px.scatter(agg, x='fotos_med', y='itens', trendline='ols', title='Fotos médias × Itens'), use_container_width=True)

# =====================================
# 6) Frete – impacto de peso e volume
# =====================================
with t6:
    st.subheader("6) Frete – relação com peso e volume")
    f = base[['freight_value','product_weight_g','product_length_cm','product_height_cm','product_width_cm']].dropna()
    f = f[(f['product_weight_g']>0) & (f['product_length_cm']>0) & (f['product_height_cm']>0) & (f['product_width_cm']>0)]
    f['volume_cm3'] = f['product_length_cm']*f['product_height_cm']*f['product_width_cm']
    if not f.empty:
        rho_w = f[['freight_value','product_weight_g']].corr(method='spearman').iloc[0,1]
        rho_v = f[['freight_value','volume_cm3']].corr(method='spearman').iloc[0,1]
        c1,c2 = st.columns(2)
        c1.metric("Spearman ρ (peso × frete)", f"{rho_w:.3f}")
        c2.metric("Spearman ρ (volume × frete)", f"{rho_v:.3f}")
        g1,g2 = st.columns(2)
        g1.plotly_chart(px.scatter(f.sample(min(5000,len(f)), random_state=42), x='product_weight_g', y='freight_value', trendline='ols', title='Frete × Peso (amostra)'), use_container_width=True)
        g2.plotly_chart(px.scatter(f.sample(min(5000,len(f)), random_state=42), x='volume_cm3', y='freight_value', trendline='ols', title='Frete × Volume (amostra)'), use_container_width=True)
    else:
        st.info("Sem dados de frete/peso/volume no filtro atual.")

# =====================================
# 7) Geografia – concentração clientes × vendedores
# =====================================
with t7:
    st.subheader("7) Geografia – concentração de clientes e vendedores")
    g = df[['order_id','customer_state','seller_state','customer_city','seller_city']].drop_duplicates('order_id')
    if start_ts is not None and end_ts is not None:
        orders_period = df[['order_id','order_purchase_timestamp']].drop_duplicates('order_id')
        orders_period = orders_period[(orders_period['order_purchase_timestamp']>=start_ts) & (orders_period['order_purchase_timestamp']<=end_ts)]
        g = g[g['order_id'].isin(orders_period['order_id'])]
    c1,c2 = st.columns(2)
    cli = g['customer_state'].value_counts().head(15).reset_index()
    ven = g['seller_state'].value_counts().head(15).reset_index()
    cli.columns = ['UF','qtde']; ven.columns = ['UF','qtde']
    c1.plotly_chart(px.bar(cli, x='UF', y='qtde', title='Clientes por UF (Top 15)'), use_container_width=True)
    c2.plotly_chart(px.bar(ven, x='UF', y='qtde', title='Vendedores por UF (Top 15)'), use_container_width=True)

# =====================================
# 8) Atrasos × Estados (cliente e vendedor)
# =====================================
with t8:
    st.subheader("8) Atrasos × Estados")
    a = df[['order_id','customer_state','seller_state','order_status','order_delivered_customer_date','order_estimated_delivery_date','order_purchase_timestamp']].drop_duplicates('order_id')
    if start_ts is not None and end_ts is not None:
        a = a[(a['order_purchase_timestamp']>=start_ts) & (a['order_purchase_timestamp']<=end_ts)]
    a = a[(a['order_status']=='delivered') & a['order_delivered_customer_date'].notna() & a['order_estimated_delivery_date'].notna()]
    a['late'] = (a['order_delivered_customer_date']>a['order_estimated_delivery_date']).astype(int)
    cust = a.groupby('customer_state')['late'].mean().mul(100).round(2).sort_values(ascending=False).reset_index(name='atraso_%')
    sell = a.groupby('seller_state')['late'].mean().mul(100).round(2).sort_values(ascending=False).reset_index(name='atraso_%')
    c1,c2 = st.columns(2)
    c1.plotly_chart(px.bar(cust.head(15), x='customer_state', y='atraso_%', title='Atraso por UF do cliente (Top 15)'), use_container_width=True)
    c2.plotly_chart(px.bar(sell.head(15), x='seller_state', y='atraso_%', title='Atraso por UF do vendedor (Top 15)'), use_container_width=True)

# =====================================
# 9) Recompra – perfil de quem recompra
# =====================================
with t9:
    st.subheader("9) Recompra – comparação entre clientes recorrentes e não recorrentes")
    r = df[['order_id','customer_unique_id','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date','review_score','payment_type_first','payment_installments_max','product_category_name']].drop_duplicates('order_id').copy()
    if start_ts is not None and end_ts is not None:
        r = r[(r['order_purchase_timestamp']>=start_ts) & (r['order_purchase_timestamp']<=end_ts)]
    counts = r.groupby('customer_unique_id')['order_id'].nunique()
    r = r.merge(counts.rename('n_orders_customer'), left_on='customer_unique_id', right_index=True)
    r['is_repeat'] = r['n_orders_customer']>1

    def on_time(row):
        if pd.isna(row['order_delivered_customer_date']) or pd.isna(row['order_estimated_delivery_date']):
            return np.nan
        return int(row['order_delivered_customer_date']<=row['order_estimated_delivery_date'])
    r['on_time'] = r.apply(on_time, axis=1)

    k1,k2 = st.columns(2)
    repeat_rate = r['is_repeat'].mean()*100
    k1.metric("Taxa de recompra (clientes com >1 pedido)", f"{repeat_rate:.2f}%")

    comp = r.groupby('is_repeat').agg(
        nota_media=('review_score','mean'),
        pct_no_prazo=('on_time', lambda s: float(np.nanmean(s))*100),
        parcelas_med=('payment_installments_max','mean'),
        pedidos=('order_id','count')
    ).reset_index()
    k2.dataframe(comp, hide_index=True)

    mix = r.groupby(['is_repeat','payment_type_first'])['order_id'].count().groupby(level=0).apply(lambda s: (s/s.sum()*100)).reset_index(name='share')
    fig = px.bar(mix, x='payment_type_first', y='share', color='is_repeat', barmode='group', title='Meios de pagamento – mix por grupo')
    fig.update_layout(yaxis_tickformat='.0%')
    st.plotly_chart(fig, use_container_width=True)

st.caption("© Análises executadas localmente no dataset informado. Para dúvidas ou extensões (mapas, segmentações por categoria/UF), fale comigo.")
