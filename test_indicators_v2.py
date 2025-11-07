import pandas as pd
import mplfinance as mpf
import warnings
from data.data_manager import AdvancedDataManager
from utils.data_converter import DataConverter
from utils.indicators import TechnicalIndicators # v1.3.1 (SMI 버그 수정됨)
import numpy as np

warnings.filterwarnings('ignore')

def run_v2_indicators_test():
    """
    [Phase 3.2.3] v2.0 신규 지표(HMA, SMI, Efficiency, Squeeze)를 테스트합니다.
    """
    print("🚀 [Phase 3.2.3] v2.0 신규 지표 테스트 시작...")
    
    symbol = "BTCUSDT_UMCBL"
    start_date = "2024-01-01"
    end_date = "2024-06-30"

    # --- 1. 데이터 준비 (1D) ---
    try:
        data_manager = AdvancedDataManager()
        converter = DataConverter()
        
        print(f"Loading 5m data for {symbol}...")
        df_5m = data_manager.safe_data_load(
            symbol=symbol, timeframe='5m', 
            start_date=start_date, end_date=end_date
        )
        if df_5m is None or df_5m.empty:
            print("❌ 5m 데이터 로드 실패. 테스트를 종료합니다.")
            return

        print("Resampling 5m -> 1H -> 4H -> 1D...")
        df_1h = converter.resample_to_1h(df_5m)
        df_4h = converter.resample_to_4h(df_1h)
        df_1d = converter.resample_to_1d(df_4h)
        df_1d.set_index('timestamp', inplace=True)
        
        print(f"✅ 1D ({len(df_1d)} 행) 데이터 준비 완료.")

    except Exception as e:
        print(f"❌ 데이터 준비 중 오류 발생: {e}")
        return

    # --- 2. v2.0 신규 지표 계산 ---
    try:
        print("Calculating v2.0 Indicators (HMA, SMI, Fractal Efficiency, Squeeze)...")
        
        df_1d['hma_9'] = TechnicalIndicators.calculate_hma(df_1d, 9)
        df_1d['hma_21'] = TechnicalIndicators.calculate_hma(df_1d, 21)
        df_1d['smi_oscillator'] = TechnicalIndicators.calculate_smi(df_1d)
        df_1d['fractal_efficiency'] = TechnicalIndicators.calculate_fractal_efficiency(df_1d, 20)
        df_1d['squeeze'] = TechnicalIndicators.is_volatility_squeeze(df_1d, 20).astype(float) # 0.0 or 1.0

        print("✅ v2.0 지표 계산 완료.")
            
    except Exception as e:
        print(f"❌ 지표 계산 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- 3. 차트 시각화 (v1.2 수정) ---
    try:
        print("Generating chart...")
        
        # [수정] 볼륨(panel=1)을 addplot에 수동으로 추가
        apds = [
            # 1. HMA (패널 0 - 메인 차트)
            mpf.make_addplot(df_1d['hma_9'], panel=0, color='blue', width=0.7),
            mpf.make_addplot(df_1d['hma_21'], panel=0, color='orange', width=0.7),
            
            # 2. Volume (패널 1 - 볼륨 차트)
            mpf.make_addplot(df_1d['volume'], panel=1, type='bar', color='gray', ylabel='Volume'),
            
            # 3. SMI (패널 2 - 오실레이터)
            mpf.make_addplot(df_1d['smi_oscillator'], panel=2, color='purple', ylabel='SMI'),
            mpf.make_addplot(pd.Series(0, index=df_1d.index), panel=2, color='gray', linestyle='--'),

            # 4. Fractal Efficiency (패널 3 - 오실레이터)
            mpf.make_addplot(df_1d['fractal_efficiency'], panel=3, color='green', ylabel='Efficiency'),
            mpf.make_addplot(pd.Series(0, index=df_1d.index), panel=3, color='gray', linestyle='--'),
            
            # 5. Squeeze (패널 4 - 0/1 플래그)
            mpf.make_addplot(df_1d['squeeze'], panel=4, type='bar', color='red', ylabel='Squeeze')
        ]

        # 차트 저장 (패널 5개)
        output_file = 'test_indicators_v2.png'
        mpf.plot(
            df_1d,
            type='candle',
            style='charles',
            title='Phase 3.2.3 - v2.0 Indicators Test (1D Chart)',
            ylabel='Price (USDT)',
            addplot=apds,
            panel_ratios=(8, 2, 2, 2, 1), # (메인, 볼륨, SMI, Efficiency, Squeeze)
            figsize=(20, 15),
            volume=False, # [수정] 자동 볼륨 끄기 (수동으로 addplot에 추가했으므로)
            savefig=output_file
        )
        
        print(f"🎉 테스트 완료! 결과 차트가 {output_file} 파일로 저장되었습니다.")
        print("   [검증] 차트를 열어 5개의 패널이 모두 정상적으로 출력되는지 확인해 주세요.")

    except Exception as e:
        print(f"❌ 차트 생성 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_v2_indicators_test()