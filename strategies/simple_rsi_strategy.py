import pandas as pd
from typing import Dict, List, Any
from strategies.base_strategy import BaseStrategy

class SimpleRSIStrategy(BaseStrategy):
    """
    [V4.7 테스트용] 간단한 RSI 매매 전략
    - RSI < 30 매수 (10% 비중)
    - RSI > 70 매도 (전량 청산)
    """
    
    def __init__(self, config: Dict):
        """전략 초기화"""
        super().__init__("SimpleRSIStrategy_v1.0", config)
        print("✅ SimpleRSIStrategy Initialized (for testing).")

    def get_required_features(self) -> Dict[str, List[str]]:
        """
        [V4.7 신규]
        이 전략은 'base' 타임프레임(5m)의 'rsi' 지표 하나만 필요로 합니다.
        """
        return {
            'base': ['rsi'], # 'base'는 main_tf (5m)를 의미
            '1d': ['regime'] 
        }

    def generate_signal(self, data: pd.DataFrame, open_positions: List[Dict]) -> List[Dict[str, Any]]:
        """
        간단한 RSI 매매 신호 생성
        """
        actions = []
        if data.empty:
            return actions

        current_row = data.iloc[-1]
        
        # 'base' 지표는 접미사(suffix) 없이 'rsi'로 접근합니다.
        rsi = current_row.get('rsi') 

        if pd.isna(rsi):
            return actions # RSI가 아직 계산되지 않은 경우 (데이터 초반)

        # 현재 포지션이 있는지 확인
        has_position = len(open_positions) > 0

        # --- 진입 로직 ---
        # 포지션이 없고, RSI가 30 미만일 때 매수
        if not has_position and rsi < 15:
            actions.append({
                'action': 'buy',
                'size_pct': 0.1, # 테스트를 위해 10% 비중
                'trade_mode': 'RSI_Simple',
                'reason': f'RSI {rsi:.2f} < 15',
                'signal_details': {'rsi': rsi}
            })
            print(f"🔔 {current_row['timestamp']} - BUY Signal @ {current_row['close']} (RSI: {rsi:.2f})")

        # --- 청산 로직 ---
        # 포지션이 있고, RSI가 70 초과일 때 매도
        elif has_position and rsi > 60:
            actions.append({
                'action': 'close',
                'percent': 1.0, # 100% 전량 청산
                'reason': f'RSI {rsi:.2f} > 70',
                'trade_mode': 'RSI_Simple' # 닫을 포지션의 모드 (엔진이 필터링)
            })
            print(f"🔔 {current_row['timestamp']} - SELL Signal @ {current_row['close']} (RSI: {rsi:.2f})")
        
        return actions
