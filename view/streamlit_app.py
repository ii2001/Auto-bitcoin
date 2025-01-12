import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px


def get_connection():
    return sqlite3.connect('../data/bitcoin_trades.db')


def load_data():
    conn = get_connection()
    query = "SELECT * FROM trades"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def main():
    st.set_page_config(
        page_title="Bitcoin Trades Dashboard",
        layout="wide",  # 화면 전체 폭을 사용
        initial_sidebar_state="expanded"
    )

    # # 사이드바
    # st.sidebar.title("Settings")
    # with st.sidebar:
    #     st.write("여기서 필터나 기간 선택 등을 구현할 수 있음")

    st.title('Bitcoin Trades Viewer')
    df = load_data()

    # 요약 정보 섹션(가로로 배치)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Trades", len(df))
    with col2:
        st.metric("First Trade Date", str(df['timestamp'].min()).split("T")[0])
    with col3:
        st.metric("Last Trade Date", str(df['timestamp'].max()).split("T")[0])

    st.markdown("---")  # 구분선

    # 거래 내역 표시
    st.subheader('거래 내역')
    st.dataframe(df)

    # 결정 분포
    st.subheader('결정 분포')
    decision_counts = df['decision'].value_counts()
    fig_pie = px.pie(values=decision_counts.values,
                     names=decision_counts.index,
                     title='Trade Decisions',
                     color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig_pie, use_container_width=True)

    # 2열 레이아웃으로 그래프 배치
    col4, col5 = st.columns(2)
    with col4:
        st.subheader('보유 BTC')
        fig_btc_balance = px.line(df, x='timestamp', y='btc_balance', title='BTC Balance',
                                  color_discrete_sequence=['#FFA07A'])
        st.plotly_chart(fig_btc_balance, use_container_width=True)

    with col5:
        st.subheader('보유 KRW')
        fig_krw_balance = px.line(df, x='timestamp', y='krw_balance', title='KRW Balance',
                                  color_discrete_sequence=['#20B2AA'])
        st.plotly_chart(fig_krw_balance, use_container_width=True)

    # BTC 가격 변동
    st.subheader('BTC 가격 변동')
    fig_btc_price = px.line(df, x='timestamp', y='btc_krw_price', title='BTC Price (KRW)',
                            color_discrete_sequence=['#F08080'])
    st.plotly_chart(fig_btc_price, use_container_width=True)


if __name__ == "__main__":
    main()
