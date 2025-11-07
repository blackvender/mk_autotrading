import pandas as pd
import warnings
from data.data_manager import AdvancedDataManager
from feature_factory import FeatureFactory
#from strategies.dynamic_strategy import DynamicVolatilityStrategy_Refactored
#from strategies.simple_rsi_strategy import SimpleRSIStrategy
from strategies.dca_rsi_strategy import DcaRSIStrategy
from backtesting.engine import AdvancedBacktestEngine
from reporting.reporting_service import ReportingService

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

def main():
    """
    [V4.7] 요구사항 기반(Dependency Inversion) 백테스트 파이프라인
    1. 전략 초기화 및 "요구사항" 확인
    2. 요구사항에 따라 "동적" 데이터 준비 (FeatureFactory)
    3. 백테스트 실행 (BacktestEngine)
    4. 리포트 생성 (ReportingService)
    """
    print("🚀 V4.7 Refactored Backtest Pipeline Started (Requirements-Based)")
    print("=" * 60)

    # --- 0. 설정 (Configuration) ---
    symbol = "BTCUSDT_UMCBL"
    start_date = "2022-01-01"
    end_date = "2022-02-28" # 테스트 기간
    
    # 전략 및 엔진 설정
    config = {
        'initial_balance': 6000,
        'commission': 0.0004,
        'slippage': 0.0001,
        'risk_per_trade_total': 0.02,
        'max_leverage': 8,
        'max_open_entries': 5,
        'language': 'en', # 'en' 또는 'ko'
        
        # 전략(Strategy)용 파라미터
        'base_volatility': 0.02,
        'momentum_rsi_base': 60,
        'reversal_rsi_base': 40,
        'max_dca_levels': 5,
        'max_portfolio_ratio': 0.6
    }
    
    print(f"🔧 Config: {symbol} | {start_date} to {end_date}")

    # --- 1. 모듈 초기화 (Initialization) ---
    try:
        data_manager = AdvancedDataManager()
        feature_factory = FeatureFactory(data_manager)
        
        # [V4.7] 전략을 먼저 초기화합니다.
        strategy = DcaRSIStrategy(config)
        
        backtest_engine = AdvancedBacktestEngine(config)
        reporting_service = ReportingService(language=config.get('language', 'en'))
        print(f"✅ All modules initialized. Strategy: {strategy.name}")
    except Exception as e:
        print(f"❌ Module initialization failed: {e}")
        return

    # --- 2. [데이터 준비] (FeatureFactory) ---
    print("\n📊 [Phase 1] Creating Featured DataFrame...")
    try:
        # [V4.7] 전략에서 "요구사항"을 가져옵니다.
        requirements = strategy.get_required_features()
        print(f"   [FF] Strategy requirements received: {requirements}")

        # [V4.7] 팩토리에 요구사항을 전달하여 동적으로 DataFrame 생성
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
        # [V4.7] 엔진 호출 시그니처가 간소화되었습니다.
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
        # 분리된 리포팅 서비스에 결과 객체를 전달하여 리포트 생성
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
