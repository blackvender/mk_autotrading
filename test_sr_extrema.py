import pandas as pd
import mplfinance as mpf
import warnings
from data.data_manager import AdvancedDataManager
from utils.data_converter import DataConverter
from utils.indicators import TechnicalIndicators # find_local_extrema가 추가되었다고 가정

warnings.filterwarnings('ignore')

def run_extrema_test():
    """
    1. 1D 데이터를 로드하고 리샘플링합니다.
    2. 'find_local_extrema' 함수를 호출하여 지지/저항 후보를 찾습니다.
    3. mplfinance로 차트에 시각화하여 결과를 검증합니다.
    """
    print("🚀 [Phase 3.2.1] S/R 극값 탐지기(find_local_extrema) 테스트 시작...")

    # --- 1. 데이터 준비 ---
    try:
        data_manager = AdvancedDataManager()
        converter = DataConverter()
        
        # 5m 원본 데이터를 로드합니다 (데이터가 없으면 API로 다운로드).
        # 테스트를 위해 2년치 데이터를 로드합니다.
        print("Loading 5m data (approx. 2 years)...")
        df_5m = data_manager.safe_data_load(
            symbol="BTCUSDT_UMCBL", 
            timeframe='5m', 
            start_date="2023-01-01", 
            end_date="2024-12-31"
        )
        
        if df_5m is None or df_5m.empty:
            print("❌ 5m 데이터 로드 실패. 테스트를 종료합니다.")
            return

        # 1D 데이터로 리샘플링
        print("Resampling 5m -> 1H -> 4H -> 1D...")
        df_1h = converter.resample_to_1h(df_5m)
        df_4h = converter.resample_to_4h(df_1h)
        df_1d = converter.resample_to_1d(df_4h)
        df_1d.set_index('timestamp', inplace=True)
        
        print(f"✅ 1D 데이터 준비 완료: {len(df_1d)} 일")

    except Exception as e:
        print(f"❌ 데이터 준비 중 오류 발생: {e}")
        return

    # --- 2. S/R 극값 탐지 실행 ---
    try:
        # order=10 (약 2주) 기준으로 극값을 찾습니다 (1D 차트이므로 order 값을 더 크게 설정).
        order_period = 10 
        print(f"Running find_local_extrema (order={order_period})...")
        
        support_levels, resistance_levels = TechnicalIndicators.find_local_extrema(
            df_1d, 
            order=order_period
        )
        
        if support_levels.isnull().all() and resistance_levels.isnull().all():
            print("⚠️ 극값을 찾지 못했습니다. (데이터가 너무 짧거나 order 값이 너무 클 수 있습니다.)")
        else:
            print("✅ 극값 탐지 완료.")
            
    except AttributeError:
        print("❌ 'TechnicalIndicators' 클래스에 'find_local_extrema' 함수가 없습니다.")
        print("   [조치] 이전 단계에서 제안한 코드를 'utils/indicators.py'에 추가했는지 확인해 주세요.")
        return
    except Exception as e:
        print(f"❌ 극값 탐지 중 오류 발생: {e}")
        return

    # --- 3. 차트 시각화 ---
    try:
        print("Generating chart...")
        
        # 2024년 데이터만 차트로 그림 (전체는 너무 길 수 있음)
        df_plot = df_1d.loc["2024-01-01":]

        # [수정] 추가 플롯(addplot) 리스트 생성
        # df_plot의 인덱스와 동일한 기간으로 S/R 데이터를 잘라냅니다.
        apds = [
            # 지지선 플롯 (녹색 삼각형)
            mpf.make_addplot(support_levels[df_plot.index], type='scatter', marker='^', color='green', markersize=100),
            # 저항선 플롯 (빨간색 역삼각형)
            mpf.make_addplot(resistance_levels[df_plot.index], type='scatter', marker='v', color='red', markersize=100)
        ]

        # 차트 저장
        output_file = 'sr_extrema_test.png'
        mpf.plot(
            df_plot,
            type='candle',
            style='charles',
            title='Phase 3.2.1 - Local Extrema (S/R) Test (1D Chart)',
            ylabel='Price (USDT)',
            addplot=apds,
            figsize=(20, 10),
            volume=True,
            savefig=output_file
        )
        
        print(f"🎉 테스트 완료! 결과 차트가 {output_file} 파일로 저장되었습니다.")
        print("   [검증] 차트를 열어 녹색(▲)과 빨간색(▼) 마커가 유의미한 지지/저항 레벨에 찍혔는지 확인해 주세요.")

    except Exception as e:
        print(f"❌ 차트 생성 중 오류 발생: {e}")
        import traceback
        traceback.print_exc() # [추가] 더 자세한 오류 확인
        print("   [참고] 'mplfinance'와 'scipy' 라이브러리가 설치되어 있어야 합니다. (pip install mplfinance scipy)")

if __name__ == "__main__":
    run_extrema_test()