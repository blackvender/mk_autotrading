import pandas as pd
import mplfinance as mpf
import warnings
from data.data_manager import AdvancedDataManager
from utils.data_converter import DataConverter
from feature_factory import FeatureFactory 
from utils.indicators import TechnicalIndicators 
import numpy as np 

warnings.filterwarnings('ignore')

# [신규] pandas 출력 옵션 설정 (가격이 지수 표기법(e.g., 6.5e+04)으로 나오지 않게 함)
pd.set_option('display.float_format', '{:.2f}'.format)
pd.set_option('display.width', 1000)

# --- 4H POC 계산을 위한 헬퍼 함수 (이전과 동일) ---
def _calculate_4h_poc(df_5m: pd.DataFrame, df_4h_timestamps: pd.Series, 
                      symbol: str) -> pd.Series:
    """
    [v1.0 Test] 5m 데이터를 기반으로 4H POC(Point of Control)를 계산합니다.
    """
    print("   [TEST] Calculating 4H Point of Control (POC) from 5m data...")
    if df_5m.empty or 'close' not in df_5m or 'volume' not in df_5m:
        return pd.Series(index=df_4h_timestamps.index, dtype=float)

    df_5m_copy = df_5m.copy()
    
    price_precision = 0
    if 'BTC' in symbol: price_precision = 0
    elif 'ETH' in symbol: price_precision = 1
    
    df_5m_copy['price_bin'] = df_5m_copy['close'].round(price_precision)
    
    volume_by_4h_price = df_5m_copy.groupby(
        [pd.Grouper(key='timestamp', freq='4H'), 'price_bin']
    )['volume'].sum().reset_index()

    poc_series = volume_by_4h_price.loc[
        volume_by_4h_price.groupby(pd.Grouper(key='timestamp', freq='4H'))['volume'].idxmax()
    ]

    poc_series = poc_series.set_index('timestamp')['price_bin']
    poc_series_aligned = poc_series.reindex(df_4h_timestamps, method='ffill')
    
    return poc_series_aligned.values
# --- [헬퍼 함수 종료] ---


def run_sr_zone_4h_test():
    """
    [Phase 3.2.1 4H 검증]
    알고리즘을 테스트하고, 탐지된 S/R Zone의 값을 터미널에 출력합니다.
    """
    print("🚀 [Phase 3.2.1] S/R Zone (4H) 테스트 시작...")
    
    symbol = "BTCUSDT_UMCBL"
    start_date = "2024-01-01"
    end_date = "2024-06-30" # 6개월 데이터로 테스트
    
    # [파라미터 설정] 논의된 최적값 사용
    order_period = 5
    min_score_to_plot = 300
    print(f"   [Params] S/R 극값(Extrema) Order = {order_period} (7캔들)")
    print(f"   [Params] 차트 표시 최소 점수(Min Score) = {min_score_to_plot}")


    # --- 1. 데이터 준비 ---
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

        print("Resampling 5m -> 1H -> 4H...")
        df_1h = converter.resample_to_1h(df_5m)
        df_4h = converter.resample_to_4h(df_1h)
        df_test = df_4h
        
        print(f"✅ 4H ({len(df_test)} 행) 및 5m ({len(df_5m)} 행) 데이터 준비 완료.")

    except Exception as e:
        print(f"❌ 데이터 준비 중 오류 발생: {e}")
        return

    # --- 2. S/R Zone 계산 실행 ---
    try:
        # 2a. (입력 1) 4H 극값(Extrema) 계산
        print(f"Running find_local_extrema (order={order_period}) on 4H data...")
        support_raw, resistance_raw = TechnicalIndicators.find_local_extrema(df_test, order=order_period)
        df_test['support_levels_raw'] = support_raw
        df_test['resistance_levels_raw'] = resistance_raw

        # 2b. (입력 2) 4H POC 계산
        print("Running _calculate_4h_poc (Test Version)...")
        poc_series = _calculate_4h_poc(
            df_5m=df_5m,
            df_4h_timestamps=df_test['timestamp'], 
            symbol=symbol
        )
        df_test['poc_4h'] = poc_series

        # 2c. (함수 테스트) 4H S/R Zone 및 Score 계산
        print("Running _calculate_sr_zones on 4H data...")
        df_4h_result = FeatureFactory._calculate_sr_zones(
            df_test.copy(), 
            symbol, 
            poc_col_name='poc_4h' # 4H POC 컬럼명 전달
        )
        
        # (차트용 데이터 원본 병합)
        if 'poc_4h' not in df_4h_result.columns: 
            df_4h_result['poc_4h'] = df_test['poc_4h']
            
        print("✅ 4H S/R Zone 및 Score 계산 완료.")
            
    except Exception as e:
        print(f"❌ S/R Zone 계산 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- 3. 차트 시각화 및 값 출력 ---
    try:
        print("\n" + "="*60)
        print("🚀 [Phase 3.2.1] S/R Zone 최종 결과 (4H)")
        print("="*60)
        
        df_plot = df_4h_result.set_index('timestamp')
        
        # 3a. 모든 S/R 영역(Zone) 및 스코어 추출
        support_zones = df_plot[['support_1d', 'support_score_1d']].dropna().drop_duplicates().sort_values(by='support_score_1d', ascending=False)
        resistance_zones = df_plot[['resistance_1d', 'resistance_score_1d']].dropna().drop_duplicates().sort_values(by='resistance_score_1d', ascending=False)

        # [신규] 전체 탐지된 영역 상위 10개 출력
        print("\n[전체 탐지된 지지 영역 (Support Zones) - 상위 10개 (점수 내림차순)]")
        print(support_zones.nlargest(10, 'support_score_1d'))
        
        print("\n[전체 탐지된 저항 영역 (Resistance Zones) - 상위 10개 (점수 내림차순)]")
        print(resistance_zones.nlargest(10, 'resistance_score_1d'))

        # 3b. 차트에 그릴 영역 필터링
        high_score_supports = support_zones[support_zones['support_score_1d'] >= min_score_to_plot]
        high_score_resistances = resistance_zones[resistance_zones['resistance_score_1d'] >= min_score_to_plot]

        # [신규] 차트에 그려질 S/R 레벨 값 목록 상세 출력
        print(f"\n[차트에 표시될 S/R 영역 (Score >= {min_score_to_plot}점)]")
        print("--- 🟢 지지선 (Support) ---")
        print(high_score_supports.sort_values(by='support_1d', ascending=False))
        print("\n--- 🔴 저항선 (Resistance) ---")
        print(high_score_resistances.sort_values(by='resistance_1d', ascending=False))
        print("="*60 + "\n")
        
        # 3c. 차트 플롯 설정
        hlines_dict = {
            'hlines': high_score_supports['support_1d'].tolist() + high_score_resistances['resistance_1d'].tolist(),
            'colors': ['g'] * len(high_score_supports) + ['r'] * len(high_score_resistances),
            'linestyle': '--',
            'linewidths': 0.5
        }
        
        apds = []
        if 'poc_4h' in df_plot.columns:
            apds.append(mpf.make_addplot(df_plot['poc_4h'], type='scatter', marker='.', color='blue', markersize=30))

        # 차트 저장
        output_file = 'sr_zones_test_4H.png'
        mpf.plot(
            df_plot,
            type='candle',
            style='charles',
            title=f'Phase 3.2.1 - S/R Zone Test (4H Chart, Order={order_period}, Min Score={min_score_to_plot})',
            ylabel='Price (USDT)',
            addplot=apds,
            hlines=hlines_dict, 
            figsize=(20, 10),
            volume=True,
            savefig=output_file
        )
        
        print(f"🎉 테스트 완료! 결과 차트가 {output_file} 파일로 저장되었습니다.")

    except Exception as e:
        print(f"❌ 차트 생성 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_sr_zone_4h_test()