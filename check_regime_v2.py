import pandas as pd
import mplfinance as mpf
import warnings
from data.data_manager import AdvancedDataManager
from utils.data_converter import DataConverter
from feature_factory import FeatureFactory # [신규] 팩토리 임포트
import time

warnings.filterwarnings('ignore')

def run_v2_regime_visualization_mpl():
    """
    [Phase 3.2.3 최종 시각화]
    mplfinance를 사용하여 1D 캔들 차트와
    FeatureFactory의 v2.0 최종 4대 점수를 함께 그립니다.
    """
    print("="*50)
    print("🚀 [Viz] v2.0 Regime Scores (mplfinance) Visualization")
    print("="*50)
    
    symbol = "BTCUSDT"
    start_date = "2023-01-01"
    end_date = "2024-10-31"
    
    start_time = time.time()

    # --- 1. [데이터 준비 1] 정확한 1D OHLCV (차트 기반용) ---
    # (test_indicators_v2.py 템플릿 방식)
    try:
        print(f"Loading 5m data for {symbol} (for True 1D OHLC)...")
        data_manager = AdvancedDataManager()
        converter = DataConverter()
        
        df_5m_raw = data_manager.safe_data_load(
            symbol=symbol, timeframe='5m', 
            start_date=start_date, end_date=end_date
        )
        if df_5m_raw is None or df_5m_raw.empty:
            print("❌ 5m 데이터 로드 실패. 테스트를 종료합니다.")
            return

        print("Resampling 5m -> 1H -> 4H -> 1D (True OHLC)...")
        df_1h_raw = converter.resample_to_1h(df_5m_raw)
        df_4h_raw = converter.resample_to_4h(df_1h_raw)
        df_1d_true_ohlc = converter.resample_to_1d(df_4h_raw)
        df_1d_true_ohlc.set_index('timestamp', inplace=True)
        
        print(f"✅ 1D True OHLCV ({len(df_1d_true_ohlc)} 행) 준비 완료.")

    except Exception as e:
        print(f"❌ [데이터 준비 1] 오류: {e}")
        return

    # --- 2. [데이터 준비 2] v2.0 레짐 점수 (팩토리 실행) ---
    # (check_regime_v2.py 방식)
    try:
        print("\nRunning FeatureFactory to get v2.0 Regime Scores...")
        ff = FeatureFactory(data_manager=data_manager)
        
        requirements = {
            '1d': ['regime', 'poc'] # v2.0 레짐 엔진 실행
        }
    
        df_featured = ff.create_featured_dataframe(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            main_tf='5m',
            requirements=requirements
        )
        
        print("Resampling 5m features -> 1D Regime Scores...")
        df_featured['timestamp'] = pd.to_datetime(df_featured['timestamp'])
        df_1d_regime = df_featured.set_index('timestamp').resample('1D').last()
        
        regime_cols = [
            'regime_trend_score', 'regime_energy_score', 
            'regime_reversion_score', 'regime_sr_pressure_score',
            'regime_label_1d' # 라벨도 일단 가져옴
        ]
        
        print("✅ v2.0 Regime Scores 준비 완료.")
        
    except Exception as e:
        print(f"❌ [데이터 준비 2] 팩토리 실행 오류: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- 3. [병합] 1D OHLCV + 1D 레짐 점수 ---
    try:
        print("\nMerging True 1D OHLCV + v2.0 Regime Scores...")
        # 1D OHLCV의 인덱스를 기준으로 레짐 점수를 병합
        df_plot = df_1d_true_ohlc.join(df_1d_regime[regime_cols])
        
        # 최근 100일만 차트로 (너무 길면 보기 힘듦)
        df_plot = df_plot.tail(500) 
        df_plot = df_plot.dropna(subset=['open', 'high', 'low', 'close'] + regime_cols)
        
        if df_plot.empty:
            print("❌ 병합 후 데이터가 없습니다. 날짜 범위나 데이터를 확인하세요.")
            return
            
        print(f"✅ 최종 플로팅 데이터 준비 완료 ({len(df_plot)} 행).")

    except Exception as e:
        print(f"❌ [병합] 오류: {e}")
        return

    # --- 4. [시각화] mplfinance로 차트 생성 ---
    try:
        print("Generating mplfinance chart (last 100 days)...")
        
        # 패널 구성 (템플릿 기반)
        apds = [
            # 1. Panel 2: -1 to +1 Oscillators (Trend, Reversion, S/R)
            mpf.make_addplot(df_plot['regime_trend_score'], panel=2, color='blue', width=0.7),
            mpf.make_addplot(df_plot['regime_reversion_score'], panel=2, color='green', width=0.7),
            mpf.make_addplot(df_plot['regime_sr_pressure_score'], panel=2, color='red', width=0.7, 
                             ylabel='Scores'), # Y-Label
            mpf.make_addplot(pd.Series(0, index=df_plot.index), panel=2, color='gray', linestyle='--'),

            # 2. Panel 3: 0 to +1 Energy Score
            mpf.make_addplot(df_plot['regime_energy_score'], panel=3, color='orange', 
                             type='bar', ylabel='Energy') # 에너지 점수는 바로 그리는 것이 직관적
        ]

        # 차트 저장
        output_file = 'visualize_regime_v2_mpl.png'
        mpf.plot(
            df_plot,
            type='candle',
            style='charles',
            title='Phase 3.2.3 - v2.0 Regime Scores Visualization (1D Chart)',
            ylabel='Price (USDT)',
            addplot=apds,
            panel_ratios=(10, 3, 3, 2), # (메인, 볼륨, Scores, Energy)
            figsize=(20, 15),
            volume=True, # Panel 1에 볼륨 자동 추가
            savefig=output_file
        )
        
        total_time = time.time() - start_time
        print(f"\n🎉 테스트 완료! (Total Time: {total_time:.2f}s)")
        print(f"  결과 차트가 {output_file} 파일로 저장되었습니다.")
        print("\n--- Panel 2 Legend ---")
        print("  🔵 Blue:   regime_trend_score")
        print("  🟢 Green:  regime_reversion_score")
        print("  🔴 Red:    regime_sr_pressure_score")
        print("------------------------")

    except Exception as e:
        print(f"❌ 차트 생성 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_v2_regime_visualization_mpl()