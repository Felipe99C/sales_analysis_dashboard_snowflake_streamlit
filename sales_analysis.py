import pandas as pd
import streamlit as st
import altair as alt
from snowflake.snowpark.context import get_active_session

# =============================================================================
# Configura o título da página, ícone e layout wide para melhor visualização
# =============================================================================
st.set_page_config(page_title="Sales Analysis", page_icon="📊", layout="wide")
st.title("📊 Sales Analysis Dashboard")

# Abre sessão com Snowflake
session = get_active_session()

# =============================================================================
# Função para fazer os Joins de todas as tabelas dimensão com a fato no Snowflake
# Otimização importante!! fazer o JOIN no banco ao invés de trazer tabelas separadas (bem mais performático)
# =============================================================================

@st.cache_data
def load_sales_data():
    """
    Carrega dados já consolidados com JOIN de todas as dimensões.
    Mais eficiente que carregar tabelas separadas e fazer JOIN em Python.
    """
    query = """
    SELECT 
        fv.ID_TRANSACAO,
        fv.DATA,
        fv.QUANTIDADE_VENDIDA,
        fv.TOTAL_VENDA,
        dc.NOME AS CUSTOMER_NAME,
        dc.CIDADE AS CUSTOMER_CITY,
        dc.ESTADO AS CUSTOMER_STATE,
        dl.NOME AS STORE_NAME,
        dl.CIDADE AS STORE_CITY,
        dl.ESTADO AS STORE_STATE,
        dp.NOME AS PRODUCT_NAME,
        dp.MARCA AS BRAND,
        dp.CATEGORIA AS CATEGORY,
        dv.NOME AS SALESPERSON_NAME,
        dd.ANO AS YEAR,
        dd.MES AS MONTH,
        dd.DIA AS DAY
    FROM dsa_db.schema3.fato_venda fv
    LEFT JOIN dsa_db.schema3.dim_cliente dc ON fv.CLIENTE = dc.ID_CLIENTE
    LEFT JOIN dsa_db.schema3.dim_loja dl ON fv.LOJA = dl.CODIGO
    LEFT JOIN dsa_db.schema3.dim_produto dp ON fv.PRODUTO = dp.CODIGO_SKU
    LEFT JOIN dsa_db.schema3.dim_vendedor dv ON fv.VENDEDOR = dv.MATRICULA
    LEFT JOIN dsa_db.schema3.dim_data dd ON fv.DATA = dd.DATA_COMPLETA
    """
    df = session.sql(query).to_pandas()
    
    # Converte data e cria colunas de período para análises temporais
    df['DATA'] = pd.to_datetime(df['DATA'])
    df['MONTH_YEAR'] = df['DATA'].dt.to_period('M').astype(str)
    df['QUARTER'] = df['DATA'].dt.quarter
    
    return df

with st.spinner('Loading data...'):
    df_sales = load_sales_data()

# =============================================================================
# FILTROS LATERAIS (SIDEBAR)
# Permite ao usuário filtrar os dados por loja, produto, categoria, vendedor e período
# Os filtros são aplicados em todas as visualizações do dashboard
# =============================================================================

st.sidebar.title("🔍 Filters")

# Filtro por cidade da loja
store_filter = st.sidebar.multiselect(
    "Store City:",
    options=sorted(df_sales["STORE_CITY"].unique()),
    default=None
)

# Filtro por produto
product_filter = st.sidebar.multiselect(
    "Product:",
    options=sorted(df_sales["PRODUCT_NAME"].unique()),
    default=None
)

# Filtro por categoria
category_filter = st.sidebar.multiselect(
    "Category:",
    options=sorted(df_sales["CATEGORY"].unique()),
    default=None
)

# Filtro por vendedor
salesperson_filter = st.sidebar.multiselect(
    "Salesperson:",
    options=sorted(df_sales["SALESPERSON_NAME"].unique()),
    default=None
)

# Filtro por intervalo de datas
st.sidebar.subheader("Date Range")
min_date = df_sales['DATA'].min()
max_date = df_sales['DATA'].max()
date_range = st.sidebar.date_input(
    "Select period:",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# ===================================================================
# Aplica todos os filtros selecionados pelo usuário no dataset
# ====================================================================

df_filtered = df_sales.copy()

if store_filter:
    df_filtered = df_filtered[df_filtered["STORE_CITY"].isin(store_filter)]
if product_filter:
    df_filtered = df_filtered[df_filtered["PRODUCT_NAME"].isin(product_filter)]
if category_filter:
    df_filtered = df_filtered[df_filtered["CATEGORY"].isin(category_filter)]
if salesperson_filter:
    df_filtered = df_filtered[df_filtered["SALESPERSON_NAME"].isin(salesperson_filter)]
if len(date_range) == 2:
    df_filtered = df_filtered[
        (df_filtered['DATA'] >= pd.to_datetime(date_range[0])) &
        (df_filtered['DATA'] <= pd.to_datetime(date_range[1]))
    ]

# =============================================================================
# INDICADORES DE PERFORMANCE (KPIs)
# Exibe métricas principais em cards: receita total, número de transações, ticket médio e quantidade total de unidades vendidas
# =============================================================================

st.header("📈 Key Performance Indicators")

col1, col2, col3, col4 = st.columns(4)

total_revenue = df_filtered['TOTAL_VENDA'].sum()
total_transactions = len(df_filtered)
avg_ticket = df_filtered['TOTAL_VENDA'].mean()
total_quantity = df_filtered['QUANTIDADE_VENDIDA'].sum()

col1.metric("Total Revenue", f"R$ {total_revenue:,.2f}")
col2.metric("Transactions", f"{total_transactions:,}")
col3.metric("Average Ticket", f"R$ {avg_ticket:,.2f}")
col4.metric("Total Units Sold", f"{total_quantity:,}")

st.divider()

# =============================================================================
# VISUALIZAÇÕES PRINCIPAIS
# =============================================================================

# =============================================================================
# Parte com os 3 gráficos principais do dashboard
# =============================================================================

st.header("📊 Sales Overview")

col_left, col_right = st.columns(2)

# -----------------------------------------------------------------------------
# GRÁFICO 1: Top 10 Produtos por Receita
# Mostra os 10 produtos que mais geraram receita (gráfico de barras horizontal)
# -----------------------------------------------------------------------------
with col_left:
    st.subheader("Total Sales by Product")
    
    product_sales = df_filtered.groupby('PRODUCT_NAME')['TOTAL_VENDA'].sum().reset_index()
    product_sales = product_sales.sort_values('TOTAL_VENDA', ascending=False).head(10)
    
    chart_product = (
        alt.Chart(product_sales)
        .mark_bar()
        .encode(
            x=alt.X('TOTAL_VENDA:Q', title='Total Sales (R$)'),
            y=alt.Y('PRODUCT_NAME:N', sort='-x', title='Product'),
            color=alt.Color('PRODUCT_NAME:N', legend=None),
            tooltip=[
                alt.Tooltip('PRODUCT_NAME:N', title='Product'),
                alt.Tooltip('TOTAL_VENDA:Q', title='Sales', format=',.2f')
            ]
        )
        .properties(height=400)
    )
    st.altair_chart(chart_product, use_container_width=True)

# -----------------------------------------------------------------------------
# GRÁFICO 2: Distribuição de Vendas por Categoria
# Mostra a proporção de vendas entre categorias (gráfico de pizza/donut)
# -----------------------------------------------------------------------------

with col_right:
    st.subheader("Total Sales by Category")
    
    category_sales = df_filtered.groupby('CATEGORY')['TOTAL_VENDA'].sum().reset_index()
    
    chart_category = (
        alt.Chart(category_sales)
        .mark_arc(innerRadius=50)
        .encode(
            theta=alt.Theta('TOTAL_VENDA:Q'),
            color=alt.Color('CATEGORY:N', legend=alt.Legend(title="Category")),
            tooltip=[
                alt.Tooltip('CATEGORY:N', title='Category'),
                alt.Tooltip('TOTAL_VENDA:Q', title='Sales', format=',.2f')
            ]
        )
        .properties(height=400)
    )
    st.altair_chart(chart_category, use_container_width=True)

st.divider()

# -----------------------------------------------------------------------------
# GRÁFICO 3: Evolução Temporal das Vendas
# Mostra a tendência de vendas ao longo do tempo por cidade da loja (série temporal)
# -----------------------------------------------------------------------------

st.subheader("Sales Trend Over Time")

monthly_sales = df_filtered.groupby(['MONTH_YEAR', 'STORE_CITY'])['TOTAL_VENDA'].sum().reset_index()

chart_time = (
    alt.Chart(monthly_sales)
    .mark_line(point=True)
    .encode(
        x=alt.X('MONTH_YEAR:T', title='Month'),
        y=alt.Y('TOTAL_VENDA:Q', title='Total Sales (R$)'),
        color=alt.Color('STORE_CITY:N', legend=alt.Legend(title="Store City")),
        tooltip=[
            alt.Tooltip('MONTH_YEAR:T', title='Month'),
            alt.Tooltip('STORE_CITY:N', title='City'),
            alt.Tooltip('TOTAL_VENDA:Q', title='Sales', format=',.2f')
        ]
    )
    .properties(height=400)
)
st.altair_chart(chart_time, use_container_width=True)

st.divider()

# =============================================================================
# ANÁLISES DETALHADAS (ABAS)
# parte com análises mais aprofundadas organizadas em 4 abas
# ===========================================================================

st.header("🔍 Detailed Analysis")

tab1, tab2, tab3, tab4 = st.tabs([
    "🏆 Top Performers",
    "📅 Seasonality",
    "📊 Pareto Analysis",
    "📋 Raw Data"
])

# -----------------------------------------------------------------------------
# ABA 1: Mostra rankings dos melhores vendedores e lojas por receita
# -----------------------------------------------------------------------------

with tab1:
    col_a, col_b = st.columns(2)
    
    # Top 10 Vendedores
    with col_a:
        st.subheader("Top 10 Salespersons")
        top_salespersons = (
            df_filtered.groupby('SALESPERSON_NAME')['TOTAL_VENDA']
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .reset_index()
        )
        
        chart_salespersons = (
            alt.Chart(top_salespersons)
            .mark_bar()
            .encode(
                x=alt.X('TOTAL_VENDA:Q', title='Total Sales (R$)'),
                y=alt.Y('SALESPERSON_NAME:N', sort='-x', title='Salesperson'),
                color=alt.value('#1f77b4'),
                tooltip=[
                    alt.Tooltip('SALESPERSON_NAME:N', title='Salesperson'),
                    alt.Tooltip('TOTAL_VENDA:Q', title='Sales', format=',.2f')
                ]
            )
            .properties(height=400)
        )
        st.altair_chart(chart_salespersons, use_container_width=True)
    
    # Top 10 Lojas (por cidade)
    with col_b:
        st.subheader("Top 10 Stores")
        top_stores = (
            df_filtered.groupby('STORE_CITY')['TOTAL_VENDA']
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .reset_index()
        )
        
        chart_stores = (
            alt.Chart(top_stores)
            .mark_bar()
            .encode(
                x=alt.X('TOTAL_VENDA:Q', title='Total Sales (R$)'),
                y=alt.Y('STORE_CITY:N', sort='-x', title='Store City'),
                color=alt.value('#ff7f0e'),
                tooltip=[
                    alt.Tooltip('STORE_CITY:N', title='Store'),
                    alt.Tooltip('TOTAL_VENDA:Q', title='Sales', format=',.2f')
                ]
            )
            .properties(height=400)
        )
        st.altair_chart(chart_stores, use_container_width=True)

# -----------------------------------------------------------------------------
# ABA 2: Sazonalidade
# Analisa padrões de vendas ao longo dos meses e trimestres (util para identificar períodos de alta/baixa demanda)
# -----------------------------------------------------------------------------

    with tab2:
    # Padrão Mensal (agregado de todos os anos)
    st.subheader("Monthly Sales Pattern")
    
    monthly_pattern = (
        df_filtered.groupby('MONTH')['TOTAL_VENDA']
        .sum()
        .reset_index()
    )
    monthly_pattern['MONTH_NAME'] = monthly_pattern['MONTH'].map({
        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
        7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
    })
    
    chart_seasonality = (
        alt.Chart(monthly_pattern)
        .mark_line(point=True, size=3)
        .encode(
            x=alt.X('MONTH:O', title='Month', axis=alt.Axis(labelExpr="datum.value == 1 ? 'Jan' : datum.value == 2 ? 'Feb' : datum.value == 3 ? 'Mar' : datum.value == 4 ? 'Apr' : datum.value == 5 ? 'May' : datum.value == 6 ? 'Jun' : datum.value == 7 ? 'Jul' : datum.value == 8 ? 'Aug' : datum.value == 9 ? 'Sep' : datum.value == 10 ? 'Oct' : datum.value == 11 ? 'Nov' : 'Dec'")),
            y=alt.Y('TOTAL_VENDA:Q', title='Total Sales (R$)'),
            tooltip=[
                alt.Tooltip('MONTH_NAME:N', title='Month'),
                alt.Tooltip('TOTAL_VENDA:Q', title='Sales', format=',.2f')
            ]
        )
        .properties(height=400)
    )
    st.altair_chart(chart_seasonality, use_container_width=True)
    
    # Análise Trimestral
    st.subheader("Quarterly Sales")
    quarterly_sales = (
        df_filtered.groupby('QUARTER')['TOTAL_VENDA']
        .sum()
        .reset_index()
    )
    quarterly_sales['QUARTER_NAME'] = 'Q' + quarterly_sales['QUARTER'].astype(str)
    
    chart_quarterly = (
        alt.Chart(quarterly_sales)
        .mark_bar()
        .encode(
            x=alt.X('QUARTER_NAME:N', title='Quarter', sort=['Q1', 'Q2', 'Q3', 'Q4']),
            y=alt.Y('TOTAL_VENDA:Q', title='Total Sales (R$)'),
            color=alt.Color('QUARTER_NAME:N', legend=None),
            tooltip=[
                alt.Tooltip('QUARTER_NAME:N', title='Quarter'),
                alt.Tooltip('TOTAL_VENDA:Q', title='Sales', format=',.2f')
            ]
        )
        .properties(height=400)
    )
    st.altair_chart(chart_quarterly, use_container_width=True)

# -----------------------------------------------------------------------------
# ABA 3: Análise de Pareto
# Identifica quais produtos representam 80% da receita total
# Gráfico combina barras (vendas por produto) e linha (% acumulado)
# Auxilia na identificação dos produtos chave para p negócio
# -----------------------------------------------------------------------------

    with tab3:
    st.subheader("Pareto Analysis - Products (80/20 Rule)")
    
    # Calcula percentual acumulado
    pareto_products = (
        df_filtered.groupby('PRODUCT_NAME')['TOTAL_VENDA']
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    pareto_products['CUMULATIVE_SALES'] = pareto_products['TOTAL_VENDA'].cumsum()
    pareto_products['CUMULATIVE_PERCENTAGE'] = (
        pareto_products['CUMULATIVE_SALES'] / pareto_products['TOTAL_VENDA'].sum() * 100
    )
    pareto_products['PRODUCT_NUMBER'] = range(1, len(pareto_products) + 1)
    
    # Gráfico com eixos duplos (barras + linha)
    base = alt.Chart(pareto_products).encode(
        x=alt.X('PRODUCT_NUMBER:O', title='Product Rank')
    )
    
    bars = base.mark_bar(color='steelblue').encode(
        y=alt.Y('TOTAL_VENDA:Q', title='Sales (R$)', axis=alt.Axis(titleColor='steelblue')),
        tooltip=[
            alt.Tooltip('PRODUCT_NAME:N', title='Product'),
            alt.Tooltip('TOTAL_VENDA:Q', title='Sales', format=',.2f'),
            alt.Tooltip('CUMULATIVE_PERCENTAGE:Q', title='Cumulative %', format='.1f')
        ]
    )
    
    line = base.mark_line(color='red', size=2).encode(
        y=alt.Y('CUMULATIVE_PERCENTAGE:Q', title='Cumulative Percentage (%)', axis=alt.Axis(titleColor='red')),
        tooltip=[
            alt.Tooltip('CUMULATIVE_PERCENTAGE:Q', title='Cumulative %', format='.1f')
        ]
    )
    
    # Linha de referência em 80%
    rule = alt.Chart(pd.DataFrame({'y': [80]})).mark_rule(color='orange', strokeDash=[5, 5]).encode(y='y:Q')
    
    chart_pareto = alt.layer(bars, line, rule).resolve_scale(y='independent').properties(height=400)
    st.altair_chart(chart_pareto, use_container_width=True)
    
    # Insight: quantos produtos representam 80% das vendas
    products_80 = pareto_products[pareto_products['CUMULATIVE_PERCENTAGE'] <= 80]
    st.info(f"💡 **Insight:** {len(products_80)} products ({len(products_80)/len(pareto_products)*100:.1f}%) generate 80% of total sales.")

# -----------------------------------------------------------------------------
# ABA 4: Dados Brutos
# Exibe tabela com dados filtrados e botão para download em CSV
# -----------------------------------------------------------------------------

    with tab4:
    st.subheader("Sales Data Table")
    
    # Seleciona as colunas relevantes para exibição
    display_columns = [
        'DATA', 'PRODUCT_NAME', 'CATEGORY', 'STORE_CITY',
        'SALESPERSON_NAME', 'QUANTIDADE_VENDIDA', 'TOTAL_VENDA'
    ]
    
    # Exibe dataframe formatado
    st.dataframe(
        df_filtered[display_columns].style.format({
            'TOTAL_VENDA': 'R$ {:,.2f}',
            'QUANTIDADE_VENDIDA': '{:,}'
        }),
        use_container_width=True,
        height=400
    )
    
    # Botão de download
    csv = df_filtered[display_columns].to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name='sales_data_filtered.csv',
        mime='text/csv',
    )

# =============================================================================
# Parte do Rodapé - perfumaria final
# =============================================================================
st.divider()
st.caption("📊 Sales Analysis Dashboard")  