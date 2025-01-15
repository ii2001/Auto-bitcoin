import os
import time
import schedule
import logging
from dotenv import load_dotenv
import pyupbit

from model.ai_trading import ai_trading
from data.db_manager import init_db

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# .env 파일 불러오기
load_dotenv()


def main_job():
    # 중복 실행 방지용 플래그
    global trading_in_progress

    if trading_in_progress:
        logger.warning("Trading job is already in progress, skipping this run.")
        return

    try:
        trading_in_progress = True
        # 업비트 객체 생성
        access = os.getenv("UPBIT_ACCESS_KEY")
        secret = os.getenv("UPBIT_SECRET_KEY")
        if not access or not secret:
            logger.error("Upbit API key not found. Please set them in .env.")
            return

        upbit = pyupbit.Upbit(access, secret)

        # SERPAPI 키
        serpapi_key = os.getenv("SERPAPI_API_KEY")

        # AI 트레이딩 수행
        result = ai_trading(upbit, serpapi_key)
        if result:
            logger.info(f"Final Decision: {result}")
        else:
            logger.info("No decision returned.")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        trading_in_progress = False


if __name__ == "__main__":
    trading_in_progress = False
    # DB 초기화(최초 실행시)
    init_db()

    # 일정 스케줄링
    schedule.every().day.at("09:00").do(main_job)
    schedule.every().day.at("15:00").do(main_job)
    schedule.every().day.at("21:00").do(main_job)

    # 테스트 용으로 즉시 한번 실행
    main_job()

    while True:
        schedule.run_pending()
        time.sleep(1)
