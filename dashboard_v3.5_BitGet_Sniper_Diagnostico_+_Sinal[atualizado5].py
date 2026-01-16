import streamlit as st
import pandas as pd
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BitGet Cloud Sniper v5", page_icon="🦅", layout="wide")

st.markdown("""
<style>
    .stMetric { background-color: #1E1E1E; border: 1px solid #333; border-radius: 8px; padding: 15px; }
    .stDataFrame { border: 1px solid #333; border-radius: 5px; }
    div.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

st.title("🦅 BitGet Sniper: Cloud Edition (Multi-Rota)")

# --- MOTOR DE CONEXÃO ---
def get_session():
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Connection": "keep-alive"
    }
    session.headers.update(headers)
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

http = get_session()

# --- FUNÇÕES DE DADOS ---

@st.cache_data(ttl=60)
def get_market_tickers():
    # Estratégia Multi-Rota: Tenta V2, se falhar tenta V1
    endpoints = [
        ("https://api.bitget.com/api/v2/mix/market/tickers", "v2"), # Rota 1 (Nova)
        ("https://api.bitget.com/api/mix/v1/market/tickers", "v1")  # Rota 2 (Antiga)
    ]
    
    last_error = None

    for url, version in endpoints:
        try:
            params = {"productType": "umcbl"}
            resp = http.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            # Tratamento diferente dependendo da versão e formato
            raw_data = data.get("data", []) if isinstance(data, dict) else data
            
            if not raw_data:
                continue # Tenta a próxima rota

            df = pd.DataFrame(raw_data)
            
            # Normalização de colunas V1 vs V2
            rename_map = {
                "last": "price", "lastPrice": "price", 
                "usdtVolume": "volume", "baseVolume": "volume",
                "priceChangePercent": "change_24h", "chgUTC": "change_24h"
            }
            df.rename(columns=rename_map, inplace=True)
            
            # Garantia de colunas
            for c in ["price", "change_24h", "volume"]:
                if c not in df.columns: df[c] = 0.0
                else: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                
            # Filtro USDT
            if 'symbol' in df.columns:
                df = df[df["symbol"].str.contains("USDT")]
                df = df.sort_values(by="volume", ascending=False).head(40)
                return df
                
        except Exception as e:
            last_error = e
            continue # Tenta a próxima rota

    # Se chegou aqui, falhou em todas
    if last_error:
        st.error(f"Erro Crítico de Conexão: {last_error}")
    return pd.DataFrame()

def get_candle_data(symbol):
    # Rota Candles (V1 costuma ser mais permissiva para candles)
    url = "https://api.bitget.com/api/mix/v1/market/candles"
    end = int(time.time() * 1000)
    start = end - (2 * 3600 * 1000)
    params = {"symbol": symbol, "granularity": "1H", "startTime": start, "endTime": end}
    
    try:
        resp = http.get(url, params=params, timeout=5)
        data = resp.json()
        candles = data if isinstance(data, list) else data.get("data", [])
        
        if not candles: return 0.0, 0.0
        
        latest = candles[-1]
        open_p, high_p, low_p, close_p = float(latest[1]), float(latest[2]), float(latest[3]), float(latest[4])
        
        if low_p == 0: return 0.0, 0.0
        
        amplitude = ((high_p - low_p) / low_p) * 100.0
        direcao = ((close_p - open_p) / open_p) * 100.0
        return amplitude, direcao
    except: return 0.0, 0.0

# --- LÓGICA V3.5 ---
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
if st.button("🔄 RASTREAR MERCADO (CLOUD)", type="primary"):
    status = st.status("Testando rotas de conexão...", expanded=True)
    
    df = get_market_tickers()
    
    if not df.empty:
        status.write(f"Conectado! Analisando {len(df)} ativos...")
        amps, dirs = [], []
        prog = status.progress(0)
        
        for i, row in enumerate(df.itertuples()):
            a, d = get_candle_data(row.symbol)
            amps.append(a); dirs.append(d)
            prog.progress((i + 1) / len(df))
            time.sleep(0.05) # Delay amigo da API
            
        df['Amplitude_1H'] = amps
        df['Direcao_1H'] = dirs
        df['Ticker'] = df['symbol'].str.replace('USDT_UMCBL', '').str.replace('_UMCBL', '')
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
        st.warning("⚠️ Não foi possível obter dados. Veja o erro detalhado acima.")
else:
    st.info("👆 Servidor Cloud Ativo. Clique para iniciar.")
