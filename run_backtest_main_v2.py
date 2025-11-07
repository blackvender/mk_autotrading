import pandas as pd
import warnings
from data.data_manager import AdvancedDataManager
from feature_factory import FeatureFactory
# [v2.0 수정] v0.1 전략들 주석 처리
#from strategies.dynamic_strategy import DynamicVolatilityStrategy_Refactored
#from strategies.simple_rsi_strategy import SimpleRSIStrategy
#from strategies.dca_rsi_strategy import DcaRSIStrategy

# [v2.0 수정] Phase 3.2.4에서 완성한 v2.0 스코어 기반 전략 임포트
from strategies.dynamic_strategy_v2 import DynamicStrategy_v2

from backtesting.engine import AdvancedBacktestEngine
from reporting.reporting_service import ReportingService

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

def main():
    """
    [V5.0 / Phase 3.2.5] v2.0 스코어 기반 스윙 전략 백테스트
    1. v2.0 전략(DynamicStrategy_v2) 초기화
    2. v2.0 요구사항(5개 컬럼)을 FeatureFactory에 전달
    3. 백테스트 실행 (BacktestEngine)
    4. 리포트 생성 (KPI: MDD < 15%, Sharpe > 1.5) 
    """
    print("🚀 [Phase 3.2.5] v2.0 Regime Score Strategy Backtest Started")
    print("=" * 60)

    # --- 0. 설정 (Configuration) ---
    # [v2.0 수정] DataManager가 인식하는 표준 심볼명으로 변경
    symbol = "BTCUSDT" 
    
    # [v2.0 수정] 1D 스윙 전략 검증을 위해 테스트 기간 연장
    start_date = "2022-01-01"
    end_date = "2023-12-31" 
    
    # 전략 및 엔진 설정
    config = {
        'initial_balance': 6000,
        'commission': 0.0004,
        'slippage': 0.0001,
        'risk_per_trade_total': 0.02,
        'max_leverage': 8,
        'max_open_entries': 5,
        'language': 'ko', # [v2.0 수정] 리포트 언어 'ko'로 변경 (선택 사항)
        
        # v2.0 전략(DynamicStrategy_v2)용 파라미터
        'base_volatility': 0.02,
        'max_dca_levels': 5,
        'max_portfolio_ratio': 0.6
    }
    
    print(f"🔧 Config: {symbol} | {start_date} to {end_date}")

    # --- 1. 모듈 초기화 (Initialization) ---
    try:
        data_manager = AdvancedDataManager()
        feature_factory = FeatureFactory(data_manager)
        
        # [v2.0 수정] Phase 3.2.4에서 완성한 v2.0 전략으로 교체
        strategy = DynamicStrategy_v2(config)
        
        backtest_engine = AdvancedBacktestEngine(config)
        reporting_service = ReportingService(language=config.get('language', 'ko'))
        print(f"✅ All modules initialized. Strategy: {strategy.name}")
    except Exception as e:
        print(f"❌ Module initialization failed: {e}")
        return

    # --- 2. [데이터 준비] (FeatureFactory) ---
    print("\n📊 [Phase 1] Creating Featured DataFrame...")
    try:
        # v2.0 전략이 v2.0 팩토리에 필요한 모든 요구사항(5개 컬럼)을 요청
        requirements = strategy.get_required_features()
        print(f"   [FF] Strategy requirements received: {requirements}")

        featured_df = feature_factory.create_featured_dataframe(
            symbol, start_date, end_date, 
            main_tf='5m', 
            requirements=requirements
        )
        
        if featured_df.empty:
            print("❌ No data found for the specified period.")
            return
            
        print(f"✅ Featured DataFrame (5m) Created: {len(featured_df)} rows")
        
    except Exception as e:
        print(f"❌ Data preparation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- 3. [백테스트 실행] (BacktestEngine) ---
    print("\n⚙️ [Phase 2] Backtest Engine Running...")
    try:
        backtest_result = backtest_engine.run_custom_period_backtest(
            df=featured_df,
            strategy=strategy
        )
        print("🎉 Backtest Completed! (Raw data generated)")
    except Exception as e:
        print(f"❌ Backtest execution failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # --- 4. [리포트 생성] (ReportingService) ---
    print(f"\n📄 [Phase 3] Report Generation Running...")
    try:
        # ReportingService가 결과 객체를 받아 리포트 생성
        reporting_service.generate_report(backtest_result)
        print(f"✅ Report Generation Completed! Check 'backtest_results' folder.")
    except Exception as e:
        print(f"❌ Report generation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 필요한 라이브러리가 설치되어 있는지 확인
    try:
        import ta
        import mplfinance
        from binance.client import Client
    except ImportError as e:
        print(f"!! Required library not found: {e.name}")
        print("Please run: pip install python-binance pandas numpy ta mplfinance")
    else:
        main()