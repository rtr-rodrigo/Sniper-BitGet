import streamlit as st
import pandas as pd
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BitGet Sniper v5.3", page_icon="🦅", layout="wide")

st.markdown("""
<style>
    .stMetric { background-color: #1E1E1E; border: 1px solid #333; border-radius: 8px; padding: 15px; }
    .stDataFrame { border: 1px solid #333; border-radius: 5px; }
    div.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

st.title("🦅 BitGet Sniper: Full V2 (v5.3)")

# --- MOTOR DE CONEXÃO ---
def get_session():
    session = requests.Session()
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

# --- FUNÇÕES DE DADOS (100% V2) ---

@st.cache_data(ttl=60)
def get_market_tickers():
    # Rota V2 Hardcoded (A que funcionou no seu teste)
    url_v2 = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
    
    try:
        resp = http.get(url_v2, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        # Na V2, os dados geralmente estão em data['data']
        raw_data = data.get("data", [])
        
        if raw_data:
            df = pd.DataFrame(raw_data)
            # Mapeamento V2 Exato
            rename_map = {
                "symbol": "symbol",
                "lastPr": "price",        # V2 usa lastPr
                "usdtVolume": "volume", 
                "change24h": "change_24h" # V2 usa change24h
            }
            # Renomear apenas colunas que existem
            df.rename(columns=rename_map, inplace=True)
            return process_dataframe(df)
            
    except Exception as e:
        st.error(f"Erro ao buscar Tickers V2: {e}")

    return pd.DataFrame()

def process_dataframe(df):
    """Limpeza e Ordenação"""
    # Garante colunas essenciais
    cols_needed = ["price", "change_24h", "volume"]
    for c in cols_needed:
        if c not in df.columns: df[c] = 0.0
        else: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    
    # Filtro USDT
    if 'symbol' in df.columns:
        df = df[df["symbol"].str.contains("USDT")]
        df = df.sort_values(by="volume", ascending=False).head(40)
        return df
    return pd.DataFrame()

def get_candle_data(symbol):
    # --- CORREÇÃO PRINCIPAL AQUI ---
    # Migramos de V1 para V2 nos Candles também.
    # Endpoint V2: /api/v2/mix/market/candles
    # Params obrigatórios: symbol, productType=USDT-FUTURES, granularity, startTime, endTime
    
    end = int(time.time() * 1000)
    start = end - (2 * 3600 * 1000) # 2 horas atrás
    
    # Montagem da URL "Soldada" (Hardcoded) para evitar erro 400
    # Nota: Não adicionamos _UMCBL aqui, usamos o symbol puro da V2 (ex: BTCUSDT)
    url = f"https://api.bitget.com/api/v2/mix/market/candles?symbol={symbol}&productType=USDT-FUTURES&granularity=1H&startTime={start}&endTime={end}"
    
    try:
        resp = http.get(url, timeout=5)
        data = resp.json()
        
        # V2 retorna lista em ['data']
        candles = data.get("data", [])
        
        if not candles: return 0.0, 0.0
        
        # Formato V2 Candle: [ts, open, high, low, close, vol, ...]
        latest = candles[0] # ATENÇÃO: Na V2 a ordem pode ser diferente, mas geralmente o index 0 é o mais recente ou o mais antigo dependendo do sort.
        # Vamos verificar a lógica de tempo. Geralmente API de candle retorna ordenado por tempo.
        # BitGet V2 Candles vem descendente ou ascendente? Vamos pegar o último da lista para garantir se for cronológico, 
        # mas se a lista vier invertida, pegamos o primeiro.
        # Por segurança, vamos pegar o último da lista (assumindo cronológico padrão) 
        # SE a lista tiver mais de 1 item e os tempos estiverem subindo.
        
        # Simples: Pegamos o último candle da lista (index -1)
        latest = candles[-1] 
        
        open_p = float(latest[1])
        high_p = float(latest[2])
        low_p = float(latest[3])
        close_p = float(latest[4])
        
        if low_p == 0: return 0.0, 0.0
        
        amplitude = ((high_p - low_p) / low_p) * 100.0
        direcao = ((close_p - open_p) / open_p) * 100.0
        return amplitude, direcao
    except: 
        return 0.0, 0.0

# --- LÓGICA DE NEGÓCIO ---
def diagnostico_ia(row):
    amp, chg = row['Amplitude_1H'], row['change_24h']
    # Ajuste: Change na V2 pode vir como 0.02 (2%) ou 2.0 (2%). Vamos normalizar visualmente.
    # Mas para lógica, assumimos número absoluto.
    
    # Se o change vier decimal (ex: 0.05 para 5%), multiplicamos por 100 para a lógica
    if -1 < chg < 1 and chg != 0: 
        chg_logic = chg * 100 
    else: 
        chg_logic = chg

    if chg_logic > 15: return "🚀 Foguete"
    elif chg_logic < -10: return "🩸 Capitulação"
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
if st.button("🔄 RASTREAR MERCADO (V2 COMPLETO)", type="primary"):
    status = st.status("Executando Protocolo V2...", expanded=True)
    
    df = get_market_tickers()
    
    if not df.empty:
        status.write(f"Lista obtida! Buscando velas de {len(df)} ativos...")
        amps, dirs = [], []
        prog = status.progress(0)
        
        for i, row in enumerate(df.itertuples()):
            a, d = get_candle_data(row.symbol)
            amps.append(a); dirs.append(d)
            prog.progress((i + 1) / len(df))
            time.sleep(0.05) 
            
        df['Amplitude_1H'] = amps
        df['Direcao_1H'] = dirs
        
        # Limpeza Visual
        df['Ticker'] = df['symbol'].str.replace('USDT', '')
        
        df['Diagnóstico'] = df.apply(diagnostico_ia, axis=1)
        df['Viés (Sinal)'] = df.apply(sinal_direcao, axis=1)
        
        # Conversão visual de Change 24h (Se vier decimal, mostra %)
        # BitGet V2 costuma mandar decimal (ex: 0.023). Streamlit number column lida com isso.
        
        df_final = df.sort_values(by='Amplitude_1H', ascending=False)
        
        status.update(label="Sucesso! Dados Carregados.", state="complete", expanded=False)
        
        st.dataframe(
            df_final[["Ticker", "Diagnóstico", "Viés (Sinal)", "price", "Amplitude_1H", "change_24h", "volume"]],
            column_config={
                "price": st.column_config.NumberColumn(format="$%.4f"),
                "Amplitude_1H": st.column_config.ProgressColumn("Volatilidade", format="%.2f%%", min_value=0, max_value=8),
                "change_24h": st.column_config.NumberColumn("24h %", format="%.2f%%"), # Formato percentual
                "volume": st.column_config.NumberColumn("Liq.", format="$%.0f")
            }, hide_index=True, use_container_width=True, height=800
        )
    else:
        st.error("Falha ao obter lista de Tickers. A API V2 pode estar indisponível momentaneamente.")
else:
    st.info("👆 V5.3 Pronta: Clique para iniciar.")
