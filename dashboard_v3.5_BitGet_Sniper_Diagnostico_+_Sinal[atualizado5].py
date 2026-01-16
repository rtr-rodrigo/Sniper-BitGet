import streamlit as st
import pandas as pd
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BitGet Sniper v5.2", page_icon="🦅", layout="wide")

st.markdown("""
<style>
    .stMetric { background-color: #1E1E1E; border: 1px solid #333; border-radius: 8px; padding: 15px; }
    .stDataFrame { border: 1px solid #333; border-radius: 5px; }
    div.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

st.title("🦅 BitGet Sniper: Direct Link (v5.2)")

# --- MOTOR DE CONEXÃO LIMPO ---
def get_session():
    session = requests.Session()
    # Headers "minimalistas" para não confundir o servidor
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    session.headers.update(headers)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

http = get_session()

# --- FUNÇÕES DE DADOS ---

@st.cache_data(ttl=60)
def get_market_tickers():
    # TRUQUE DE ENGENHARIA v5.2:
    # Em vez de passar params={'productType':...}, colocamos direto na URL.
    # Isso evita que a nuvem mude a codificação da interrogação (?) ou do igual (=).
    
    # Tentativa 1: API V2 (Padrão Ouro)
    url_v2 = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
    
    # Tentativa 2: API V1 (Fallback) - Note o 'umcbl' minúsculo hardcoded
    url_v1 = "https://api.bitget.com/api/mix/v1/market/tickers?productType=umcbl"
    
    last_error = None

    # Tenta V2 Primeiro
    try:
        resp = http.get(url_v2, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        # O formato da V2 geralmente é data['data'] direto
        raw_data = data.get("data", [])
        
        if raw_data:
            df = pd.DataFrame(raw_data)
            # Mapeamento V2
            rename_map = {
                "lastPr": "price", "last": "price", 
                "usdtVolume": "volume", 
                "change24h": "change_24h", "priceChangePercent": "change_24h"
            }
            df.rename(columns=rename_map, inplace=True)
            return process_dataframe(df)
            
    except Exception as e:
        last_error = e
        print(f"V2 falhou: {e}")

    # Se V2 falhou, Tenta V1
    try:
        resp = http.get(url_v1, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        raw_data = data.get("data", [])
        
        if raw_data:
            df = pd.DataFrame(raw_data)
            # Mapeamento V1
            rename_map = {
                "last": "price", 
                "usdtVolume": "volume", 
                "priceChangePercent": "change_24h"
            }
            df.rename(columns=rename_map, inplace=True)
            return process_dataframe(df)

    except Exception as e:
        last_error = e

    st.error(f"Erro Crítico (V5.2): {last_error}")
    return pd.DataFrame()

def process_dataframe(df):
    """Função auxiliar para limpar e ordenar os dados independente da API"""
    # Garante colunas numéricas
    for c in ["price", "change_24h", "volume"]:
        if c not in df.columns: df[c] = 0.0
        else: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    
    # Filtro USDT e Ordenação
    if 'symbol' in df.columns:
        df = df[df["symbol"].str.contains("USDT")]
        df = df.sort_values(by="volume", ascending=False).head(40)
        return df
    return pd.DataFrame()

def get_candle_data(symbol):
    # Para candles, forçamos V1 pois é mais simples para histórico
    # url hardcoded sem params dit
    if not symbol.endswith("_UMCBL"): symbol_v1 = f"{symbol}_UMCBL"
    else: symbol_v1 = symbol
        
    end = int(time.time() * 1000)
    start = end - (2 * 3600 * 1000)
    
    # Montagem manual da URL
    url = f"https://api.bitget.com/api/mix/v1/market/candles?symbol={symbol_v1}&granularity=1H&startTime={start}&endTime={end}"
    
    try:
        resp = http.get(url, timeout=5)
        data = resp.json()
        candles = data if isinstance(data, list) else data.get("data", [])
        
        if not candles: return 0.0, 0.0
        
        latest = candles[-1]
        open_p = float(latest[1])
        high_p = float(latest[2])
        low_p = float(latest[3])
        close_p = float(latest[4])
        
        if low_p == 0: return 0.0, 0.0
        
        amplitude = ((high_p - low_p) / low_p) * 100.0
        direcao = ((close_p - open_p) / open_p) * 100.0
        return amplitude, direcao
    except: return 0.0, 0.0

# --- LÓGICA DE NEGÓCIO ---
def diagnostico_ia(row):
    amp, chg = row['Amplitude_1H'], row['change_24h']
    if chg > 15: return "🚀 Foguete"
    elif chg < -10: return "🩸 Capitulação"
    elif amp > 3.5: return "⚡ Volatilidade Extrema"
    elif amp > 2.0: return "👀 Alta Volatilidade"
    else: return "💤 Normal"

def sinal_direcao(row):
    chg, direcao = row['change_24h'], row['Direcao_1H']
    if chg > 0 and direcao > 0: return "🟢 Possível LONG"
    if chg < 0 and direcao < 0: return "🔴 Possível SHORT"
    if chg > 5 and direcao < -0.5: return "🔻 Correção? (Short)"
    if chg < -5 and direcao > 0.5: return "🔺 Repique? (Long)"
    return "⚪ Aguardar"

# --- FRONTEND ---
if st.button("🔄 RASTREAR MERCADO (FORÇA BRUTA)", type="primary"):
    status = st.status("Testando conexão direta...", expanded=True)
    
    df = get_market_tickers()
    
    if not df.empty:
        status.write(f"Conexão estabelecida! Analisando {len(df)} ativos...")
        amps, dirs = [], []
        prog = status.progress(0)
        
        for i, row in enumerate(df.itertuples()):
            a, d = get_candle_data(row.symbol)
            amps.append(a); dirs.append(d)
            prog.progress((i + 1) / len(df))
            time.sleep(0.05) 
            
        df['Amplitude_1H'] = amps
        df['Direcao_1H'] = dirs
        df['Ticker'] = df['symbol'].str.replace('_UMCBL', '').str.replace('USDT', '')
        
        df['Diagnóstico'] = df.apply(diagnostico_ia, axis=1)
        df['Viés (Sinal)'] = df.apply(sinal_direcao, axis=1)
        df_final = df.sort_values(by='Amplitude_1H', ascending=False)
        
        status.update(label="Sucesso!", state="complete", expanded=False)
        
        st.dataframe(
            df_final[["Ticker", "Diagnóstico", "Viés (Sinal)", "price", "Amplitude_1H", "change_24h", "volume"]],
            column_config={
                "price": st.column_config.NumberColumn(format="$%.4f"),
                "Amplitude_1H": st.column_config.ProgressColumn("Volatilidade", format="%.2f%%", min_value=0, max_value=8),
                "volume": st.column_config.NumberColumn("Liq.", format="$%.0f")
            }, hide_index=True, use_container_width=True, height=800
        )
    else:
        st.error("Todas as tentativas falharam. A Bitget pode estar bloqueando a faixa de IP do Streamlit Cloud.")
else:
    st.info("👆 Clique para conectar (v5.2 - URL Hardcoded).")
