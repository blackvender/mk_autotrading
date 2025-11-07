import pandas as pd
import mplfinance as mpf
import warnings
from data.data_manager import AdvancedDataManager
from utils.data_converter import DataConverter
from feature_factory import FeatureFactory 
from utils.indicators import TechnicalIndicators 
import numpy as np 

warnings.filterwarnings('ignore')

def run_sr_zone_test():
    """
    [Phase 3.2.1 최종 검증]
    모든 S/R 탐지 알고리즘(Extrema, POC, Zones)을 종합적으로 테스트합니다.
    """
    print("🚀 [Phase 3.2.1] S/R Zone 클러스터링 및 스코어링 최종 테스트 시작...")
    
    symbol = "BTCUSDT_UMCBL"
    start_date = "2024-01-01"
    end_date = "2024-06-30" # 6개월 데이터로 테스트

    # --- 1. 데이터 준비 ---
    try:
        data_manager = AdvancedDataManager()
        converter = DataConverter()
        
        print(f"Loading 5m data for {symbol}...")
        df_5m = data_manager.safe_data_load(
            symbol=symbol, 
            timeframe='5m', 
            start_date=start_date, 
            end_date=end_date
        )
        if df_5m is None or df_5m.empty:
            print("❌ 5m 데이터 로드 실패. 테스트를 종료합니다.")
            return

        print("Resampling 5m -> 1H -> 4H -> 1D...")
        df_1h = converter.resample_to_1h(df_5m)
        df_4h = converter.resample_to_4h(df_1h)
        df_1d = converter.resample_to_1d(df_4h)
        
        print(f"✅ 1D ({len(df_1d)} 행) 및 5m ({len(df_5m)} 행) 데이터 준비 완료.")

    except Exception as e:
        print(f"❌ 데이터 준비 중 오류 발생: {e}")
        return

    # --- 2. S/R Zone 계산 실행 ---
    try:
        # 2a. (입력 1) 극값(Extrema) 계산
        # [수정] order=10 (21일) -> order=3 (7일)으로 변경하여 민감도 증가
        order_period = 3
        print(f"Running find_local_extrema (order={order_period})...")
        support_raw, resistance_raw = TechnicalIndicators.find_local_extrema(df_1d, order=order_period)
        df_1d['support_levels_raw'] = support_raw
        df_1d['resistance_levels_raw'] = resistance_raw

        # 2b. (입력 2) POC 계산
        print("Running _calculate_daily_poc...")
        poc_series = FeatureFactory._calculate_daily_poc(
            df_5m=df_5m,
            df_1d_timestamps=df_1d['timestamp'], 
            symbol=symbol
        )
        df_1d['poc_1d'] = poc_series

        # 2c. (함수 테스트) S/R Zone 및 Score 계산
        print("Running _calculate_sr_zones...")
        df_1d_result = FeatureFactory._calculate_sr_zones(df_1d.copy(), symbol)
        
        if 'support_1d' not in df_1d_result.columns:
            df_1d_result['support_1d'] = np.nan
            df_1d_result['support_score_1d'] = 0.0
        if 'resistance_1d' not in df_1d_result.columns:
            df_1d_result['resistance_1d'] = np.nan
            df_1d_result['resistance_score_1d'] = 0.0
        if 'poc_1d' not in df_1d_result.columns: # df_1d_result는 df_1d의 복사본이 아님
            df_1d_result['poc_1d'] = df_1d['poc_1d']
        if 'support_levels_raw' not in df_1d_result.columns: # 원본 극값 확인용
             df_1d_result['support_levels_raw'] = df_1d['support_levels_raw']
             df_1d_result['resistance_levels_raw'] = df_1d['resistance_levels_raw']
            
        print("✅ S/R Zone 및 Score 계산 완료.")
            
    except Exception as e:
        print(f"❌ S/R Zone 계산 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- 3. 차트 시각화 (수정됨) ---
    try:
        print("Generating chart...")
        
        df_plot = df_1d_result.set_index('timestamp')
        
        # [수정] min_score_to_plot을 5로 낮춰서 더 많은 Zone을 관찰
        min_score_to_plot = 3
        
        support_zones = df_plot[['support_1d', 'support_score_1d']].dropna().drop_duplicates()
        resistance_zones = df_plot[['resistance_1d', 'resistance_score_1d']].dropna().drop_duplicates()

        high_score_supports = support_zones[support_zones['support_score_1d'] >= min_score_to_plot]['support_1d'].tolist()
        high_score_resistances = resistance_zones[resistance_zones['resistance_score_1d'] >= min_score_to_plot]['resistance_1d'].tolist()

        print(f"Found {len(high_score_supports)} high-score support zones (Score >= {min_score_to_plot}).")
        print(f"Found {len(high_score_resistances)} high-score resistance zones (Score >= {min_score_to_plot}).")
        
        hlines_dict = {
            'hlines': high_score_supports + high_score_resistances,
            'colors': ['g'] * len(high_score_supports) + ['r'] * len(high_score_resistances),
            'linestyle': '--',
            'linewidths': 0.5
        }
        
        # [수정] 원본 극값(Raw Extrema)을 다시 플롯에 추가
        apds = []
        if 'poc_1d' in df_plot.columns:
            apds.append(mpf.make_addplot(df_plot['poc_1d'], type='scatter', marker='.', color='blue', markersize=30))
        if 'support_levels_raw' in df_plot.columns:
            apds.append(mpf.make_addplot(df_plot['support_levels_raw'], type='scatter', marker='^', color='#c0c0c0', markersize=20))
        if 'resistance_levels_raw' in df_plot.columns:
            apds.append(mpf.make_addplot(df_plot['resistance_levels_raw'], type='scatter', marker='v', color='#c0c0c0', markersize=20))

        output_file = 'sr_zones_test.png'
        mpf.plot(
            df_plot,
            type='candle',
            style='charles',
            title=f'Phase 3.2.1 - S/R Zone Test (Order={order_period}, Min Score={min_score_to_plot})',
            ylabel='Price (USDT)',
            addplot=apds,
            hlines=hlines_dict, 
            figsize=(20, 10),
            volume=True,
            savefig=output_file
        )
        
        print(f"🎉 테스트 완료! 결과 차트가 {output_file} 파일로 저장되었습니다.")
        print(f"   [검증] 회색(▲▼) 점들이 더 많이 보이고, 녹색/빨간색 수평선이 더 많이 탐지되는지 확인해 주세요.")

    except Exception as e:
        print(f"❌ 차트 생성 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_sr_zone_test()