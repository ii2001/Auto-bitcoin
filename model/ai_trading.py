import os
import time
import json
import logging
import pyupbit

from openai import OpenAI
from model.data_fetcher import (
    get_upbit_balances, get_ohlcv_df, add_indicators,
    get_fear_and_greed_index, get_bitcoin_news,
    create_driver, perform_chart_actions, capture_and_encode_screenshot
)
from data.db_manager import get_recent_trades, log_trade, init_db
from model.reflection import generate_reflection
from model.analysis import TradingDecision

GPT_MODEL = "o1-mini-2024-09-12"

logger = logging.getLogger(__name__)


def ai_trading(upbit, serpapi_key):
    """AI에게 데이터를 제공하고 매수/매도/홀드 여부를 결정한 뒤,
    주문을 실행하고 DB에 기록을 남긴다."""

    # 1. 현재 투자 상태 조회
    all_balances = get_upbit_balances(upbit)
    filtered_balances = [b for b in all_balances if b['currency'] in ['BTC', 'KRW']]

    # 2. 오더북(호가 데이터)
    orderbook = pyupbit.get_orderbook("KRW-BTC")

    # 3. 차트 데이터 조회 (Daily, Hourly)
    df_daily = get_ohlcv_df(interval="day", count=30)
    df_daily = add_indicators(df_daily)

    df_hourly = get_ohlcv_df(interval="minute60", count=24)
    df_hourly = add_indicators(df_hourly)

    # 4. 공포/탐욕 지수
    fear_greed_index = get_fear_and_greed_index()

    # 5. 뉴스 헤드라인
    news_headlines = get_bitcoin_news(serpapi_key)

    # 6. YouTube 자막 대신 strategy.txt 읽기
    with open("strategy.txt", "r", encoding="utf-8") as f:
        youtube_transcript = f.read()

    # DB 연결
    conn = init_db()
    recent_trades = get_recent_trades(conn)

    # 현재 시장 데이터(분석용)
    current_market_data = {
        "fear_greed_index": fear_greed_index,
        "news_headlines": news_headlines,
        "orderbook": orderbook,
        "daily_ohlcv": df_daily.to_dict(),
        "hourly_ohlcv": df_hourly.to_dict()
    }

    # 반성 생성
    reflection = generate_reflection(recent_trades, current_market_data)

    # OpenAI 객체 생성
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None

    # AI에게 판단 요청
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "user",
                "content": f"""
                You are an expert in Bitcoin investing. Analyze the provided data and determine whether to buy, sell, or hold at the current moment.
                Consider the following in your analysis:
                - Technical indicators and market data
                - Recent news headlines and their potential impact on Bitcoin price
                - The Fear and Greed Index
                - Market sentiment
                - Patterns in the chart image
                - Recent trading performance and reflection

                Recent trading reflection:
                {reflection}

                Particularly important is to always refer to the trading method of 'Wonyyotti', a legendary Korean investor:
                {youtube_transcript}

                Based on this method and the data, return a JSON with:
                1. decision (buy / sell / hold)
                2. percentage (1-100 if buy/sell, 0 if hold)
                3. reason
                
                Return only valid JSON with no markdown formatting or triple backticks.
  Do not include any additional text or explanation outside of the JSON.
                """

            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""Current investment status: {json.dumps(filtered_balances)}
Orderbook: {json.dumps(orderbook)}
Daily OHLCV with indicators (30 days): {df_daily.to_json()}
Hourly OHLCV with indicators (24 hours): {df_hourly.to_json()}
Recent news headlines: {json.dumps(news_headlines)}
Fear and Greed Index: {json.dumps(fear_greed_index)}"""
                    },
                ]
            }
        ],
    )

    # 결과 파싱
    try:
        result = TradingDecision.model_validate_json(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error parsing AI response: {e}")
        return None

    logger.info(f"AI Decision: {result.decision.upper()}")
    logger.info(f"Decision Reason: {result.reason}")

    # 매매 실행
    order_executed = False
    if result.decision == "buy":
        my_krw = upbit.get_balance("KRW")
        if my_krw is None:
            logger.error("Failed to retrieve KRW balance.")
            return None
        buy_amount = my_krw * (result.percentage / 100) * 0.9995  # 수수료 고려
        if buy_amount > 5000:
            logger.info(f"Buy Order Executed: {result.percentage}% of available KRW")
            try:
                order = upbit.buy_market_order("KRW-BTC", buy_amount)
                if order:
                    order_executed = True
                    logger.info(f"Buy order success: {order}")
                else:
                    logger.error("Buy order failed.")
            except Exception as e:
                logger.error(f"Error executing buy order: {e}")

        else:
            logger.warning("Buy Order Failed: Insufficient KRW (less than 5000 KRW)")

    elif result.decision == "sell":
        my_btc = upbit.get_balance("BTC")
        if my_btc is None:
            logger.error("Failed to retrieve BTC balance.")
            return None
        sell_amount = my_btc * (result.percentage / 100)
        current_price = pyupbit.get_current_price("KRW-BTC")
        if sell_amount * current_price > 5000:
            logger.info(f"Sell Order Executed: {result.percentage}% of held BTC")
            try:
                order = upbit.sell_market_order("KRW-BTC", sell_amount)
                if order:
                    order_executed = True
                    logger.info(f"Sell order success: {order}")
                else:
                    logger.error("Sell order failed.")
            except Exception as e:
                logger.error(f"Error executing sell order: {e}")
        else:
            logger.warning("Sell Order Failed: Insufficient BTC (less than 5000 KRW worth)")

    # 거래 실행 여부와 관계없이 현재 잔고 갱신 후 DB 저장
    time.sleep(2)  # API 호출 제한 대비
    balances = upbit.get_balances()
    btc_balance = next((float(b['balance']) for b in balances if b['currency'] == 'BTC'), 0)
    krw_balance = next((float(b['balance']) for b in balances if b['currency'] == 'KRW'), 0)
    btc_avg_buy_price = next((float(b['avg_buy_price']) for b in balances if b['currency'] == 'BTC'), 0)
    current_btc_price = pyupbit.get_current_price("KRW-BTC")

    # 거래 기록
    log_trade(
        conn,
        result.decision,
        result.percentage if order_executed else 0,
        result.reason,
        btc_balance,
        krw_balance,
        btc_avg_buy_price,
        current_btc_price,
        reflection
    )

    conn.close()
    return result
