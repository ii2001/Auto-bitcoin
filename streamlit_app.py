import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import pyupbit
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ==============================
# 1) DB 연결 및 DataFrame 로드
# ==============================
def get_connection():
    return sqlite3.connect('bitcoin_trades.db')


def load_data():
    conn = get_connection()
    query = "SELECT * FROM trades ORDER BY timestamp ASC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


# 초기 투자 금액 계산 함수
def calculate_initial_investment(df):
    initial_krw_balance = df.iloc[0]['krw_balance']
    initial_btc_balance = df.iloc[0]['btc_balance']
    initial_btc_price = df.iloc[0]['btc_krw_price']
    initial_total_investment = initial_krw_balance + (initial_btc_balance * initial_btc_price)
    return initial_total_investment


# 현재 투자 금액 계산 함수
def calculate_current_investment(df):
    current_krw_balance = df.iloc[-1]['krw_balance']
    current_btc_balance = df.iloc[-1]['btc_balance']
    current_btc_price = pyupbit.get_current_price("KRW-BTC")  # 현재 BTC 가격 가져오기
    if current_btc_price is None:  # API 호출 실패 시 마지막 기록된 가격 사용
        current_btc_price = df.iloc[-1]['btc_krw_price']
    current_total_investment = current_krw_balance + (current_btc_balance * current_btc_price)
    return current_total_investment


def calculate_market_return(df):
    # hold가 아닌 첫 투자 판단 시점 찾기
    filtered_df = df[df['decision'].isin(['buy', 'sell'])]  # 필터링 결과를 변수에 저장
    if not filtered_df.empty:  # 필터링된 DataFrame이 비어있지 않은 경우에만 처리
        first_trade = filtered_df.iloc[0]
        last_trade = df.iloc[-1]

        initial_price = first_trade['btc_krw_price']
        current_price = last_trade['btc_krw_price']
        market_return = ((current_price - initial_price) / initial_price) * 100

        # 첫 투자 시점도 반환
        return market_return, pd.to_datetime(first_trade['timestamp'])
    else:
        return 0, None  # 매수/매도 결정이 없을 경우 시장 수익률 0과 None (첫 거래 시점) 반환


# ==============================
# 2) 메인 함수
# ==============================
def main():
    st.title('Bitcoin Trades Viewer')

    # 데이터 로드
    df = load_data()
    if df.empty:
        st.warning('No trade data available.')
        return

    # 초기 투자 금액 계산
    initial_investment = calculate_initial_investment(df)

    # 현재 투자 금액 계산
    current_investment = calculate_current_investment(df)

    # 수익률 계산
    profit_rate = ((current_investment - initial_investment) / initial_investment) * 100

    # 시장 수익률 계산
    market_return, first_trade_date = calculate_market_return(df)

    # 수익률 표시
    col1, col2 = st.columns(2)
    with col1:
        st.header('📈 Strategy Return')
        st.subheader(f'{profit_rate:.2f}%')
    with col2:
        st.header('📊 Market Return')
        st.subheader(f'{market_return:.2f}%')
        market_return, first_trade_date = calculate_market_return(df)

        if first_trade_date is not None:
            caption_text = f'(Since first trade: {first_trade_date.strftime("%Y-%m-%d %H:%M:%S")})'
        else:
            caption_text = '(No first trade date available)'
        st.caption(caption_text)

    # 기본 통계
    st.header('Basic Statistics')
    st.write(f"Total number of trades: {len(df)}")
    st.write(f"First trade date: {df['timestamp'].min()}")
    st.write(f"Last trade date: {df['timestamp'].max()}")

    # BTC 가격 차트와 거래 시점
    st.header('BTC Price with Trading Points')

    # 시장 데이터 로드
    market_df = pyupbit.get_ohlcv("KRW-BTC", interval="day", count=365)
    if not market_df.empty:
        # 차트 생성
        fig = go.Figure()

        # BTC 가격 라인
        fig.add_trace(go.Scatter(
            x=market_df.index,
            y=market_df['close'],
            mode='lines',
            name='BTC Price',
            line=dict(color='gray', width=2),
            hovertemplate='<b>Price</b>: ₩%{y:,.0f}<br>'
        ))

        # timestamp를 datetime으로 변환
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # 매수 포인트
        buy_points = df[df['decision'] == 'buy']
        if not buy_points.empty:
            fig.add_trace(go.Scatter(
                x=buy_points['timestamp'],
                y=buy_points['btc_krw_price'],
                mode='markers',
                name='Buy',
                marker=dict(color='green', size=10, symbol='triangle-up'),
                hovertemplate='<b>Buy Point</b><br>' +
                              'Price: ₩%{y:,.0f}<br>' +
                              'Date: %{x}<br>' +
                              '<extra></extra>'
            ))

        # 매도 포인트
        sell_points = df[df['decision'] == 'sell']
        if not sell_points.empty:
            fig.add_trace(go.Scatter(
                x=sell_points['timestamp'],
                y=sell_points['btc_krw_price'],
                mode='markers',
                name='Sell',
                marker=dict(color='red', size=10, symbol='triangle-down'),
                hovertemplate='<b>Sell Point</b><br>' +
                              'Price: ₩%{y:,.0f}<br>' +
                              'Date: %{x}<br>' +
                              '<extra></extra>'
            ))

        # 홀드 포인트
        hold_points = df[df['decision'] == 'hold']
        if not hold_points.empty:
            fig.add_trace(go.Scatter(
                x=hold_points['timestamp'],
                y=hold_points['btc_krw_price'],
                mode='markers',
                name='Hold',
                marker=dict(color='yellow', size=8, symbol='circle'),
                hovertemplate='<b>Hold Point</b><br>' +
                              'Price: ₩%{y:,.0f}<br>' +
                              'Date: %{x}<br>' +
                              '<extra></extra>'
            ))

        # 차트 레이아웃 설정
        fig.update_layout(
            title='Bitcoin Price with Trading Decisions',
            xaxis_title='Date',
            yaxis_title='Price (KRW)',
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Failed to load market data from pyupbit.")

    # 거래 내역 표시
    st.header('Trade History')
    st.dataframe(df)

    # 거래 결정 분포
    st.header('Trade Decision Distribution')
    decision_counts = df['decision'].value_counts()
    if not decision_counts.empty:
        fig = px.pie(values=decision_counts.values, names=decision_counts.index, title='Trade Decisions')
        st.plotly_chart(fig)
    else:
        st.write("No trade decisions to display.")


if __name__ == "__main__":
    main()
