import streamlit as st
import pandas as pd
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BitGet Sniper Cloud", page_icon="🦅", layout="wide")

st.markdown("""
<style>
    .stMetric { background-color: #1E1E1E; border: 1px solid #333; border-radius: 8px; padding: 15px; }
    .stDataFrame { border: 1px solid #333; border-radius: 5px; }
    div.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

st.title("🦅 BitGet Sniper: Diagnóstico + Sinal (Versão Cloud)")

# --- MOTOR DE CONEXÃO ROBUSTO ---
def get_session():
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Connection": "keep-alive"
    }
    session.headers.update(headers)
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

http = get_session()

# --- BACKEND ---
@st.cache_data(ttl=60)
def get_market_tickers():
    url = "https://api.bitget.com/api/mix/v1/market/tickers"
    params = {"productType": "umcbl"}
    try:
        resp = http.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        raw_data = data.get("data", []) if isinstance(data, dict) else data
        if not raw_data: return pd.DataFrame()
        
        df = pd.DataFrame(raw_data)
        rename_map = {"last": "price", "lastPrice": "price", "usdtVolume": "volume", "priceChangePercent": "change_24h", "chgUTC": "change_24h"}
        df.rename(columns=rename_map, inplace=True)
        
        for c in ["price", "change_24h", "volume"]:
            if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
            
        df = df[df["symbol"].str.contains("USDT")] 
        df = df.sort_values(by="volume", ascending=False).head(40)
        return df
    except Exception:
        return pd.DataFrame()

def get_candle_data(symbol):
    url = "https://api.bitget.com/api/mix/v1/market/candles"
    end = int(time.time() * 1000)
    start = end - (2 * 3600 * 1000)
    params = {"symbol": symbol, "granularity": "1H", "startTime": start, "endTime": end}
    try:
        resp = http.get(url, params=params, timeout=10)
        data = resp.json()
        candles = data if isinstance(data, list) else data.get("data", [])
        if not candles: return 0.0, 0.0
        
        latest = candles[-1]
        open_p, high_p, low_p, close_p = float(latest[1]), float(latest[2]), float(latest[3]), float(latest[4])
        
        if low_p == 0 or open_p == 0: return 0.0, 0.0
        
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
    if chg > 5 and direcao < -0.5: return "🔻 Correção? (Short curto)"
    if chg < -5 and direcao > 0.5: return "🔺 Repique? (Long curto)"
    return "⚪ Aguardar"

# --- FRONTEND ---
if st.button("🔄 RASTREAR MERCADO", type="primary"):
    status = st.status("Conectando via Nuvem...", expanded=True)
    df = get_market_tickers()
    
    if not df.empty:
        status.write(f"Analisando {len(df)} ativos...")
        amps, dirs = [], []
        prog = status.progress(0)
        
        for i, row in enumerate(df.itertuples()):
            a, d = get_candle_data(row.symbol)
            amps.append(a); dirs.append(d)
            prog.progress((i + 1) / len(df))
            time.sleep(0.05)
            
        df['Amplitude_1H'] = amps
        df['Direcao_1H'] = dirs
        df['Ticker'] = df['symbol'].str.replace('USDT_UMCBL', '').str.replace('_UMCBL', '')
        df['Diagnóstico'] = df.apply(diagnostico_ia, axis=1)
        df['Viés (Sinal)'] = df.apply(sinal_direcao, axis=1)
        df_final = df.sort_values(by='Amplitude_1H', ascending=False)
        
        status.update(label="Pronto!", state="complete", expanded=False)
        
        try:
            top = df_final.iloc[0]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Top Volatilidade", top['Ticker'], f"{top['Amplitude_1H']:.2f}%")
            c2.metric("Diagnóstico", top['Diagnóstico'])
            c3.metric("Sinal", top['Viés (Sinal)'])
            c4.metric("Volume", f"${top['volume']/1_000_000:.1f}M")
        except: pass
        
        st.dataframe(
            df_final[["Ticker", "Diagnóstico", "Viés (Sinal)", "price", "Amplitude_1H", "change_24h", "volume"]],
            column_config={
                "price": st.column_config.NumberColumn(format="$%.4f"),
                "Amplitude_1H": st.column_config.ProgressColumn("Volatilidade (1h)", format="%.2f%%", min_value=0, max_value=8),
                "change_24h": st.column_config.NumberColumn("24h %", format="%.2f%%"),
                "volume": st.column_config.NumberColumn("Liq.", format="$%.0f")
            }, hide_index=True, use_container_width=True, height=800
        )
    else:
        st.error("Erro ao conectar na API.")
else:
    st.info("👆 Dashboard v3.5 Cloud: Clique para rastrear.")
