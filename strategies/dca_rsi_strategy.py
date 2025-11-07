import pandas as pd
from typing import Dict, List, Any
from strategies.base_strategy import BaseStrategy
from utils.logger import trading_logger # 상태 로깅을 위해 추가

class DcaRSIStrategy(BaseStrategy):
    """
    [V4.7.3] 상태 기반 분할 매수(DCA) RSI 테스트 전략
    
    - "하락 파동"을 탄다: 1차 매수 후, RSI가 반등했다가 '다시' 하락할 때 2차 매수.
    - 상태 변수(awaiting_bounce)를 두어, 너무 빠른 연속 매수를 방지.
    
    - 1차: RSI < 30
    - (반등 확인: RSI가 최저점 대비 3포인트 이상 상승)
    - 2차: RSI < 25
    - (반등 확인: RSI가 최저점 대비 3포인트 이상 상승)
    - 3차: RSI < 20
    - 청산: RSI > 60 (전량)
    """
    
    def __init__(self, config: Dict):
        super().__init__("DcaRSIStrategy_v1.1_(Stateful)", config)
        
        # 전략 설정
        self.buy_levels = config.get('rsi_buy_levels', [15, 30, 30])
        self.buy_sizes = config.get('rsi_buy_sizes', [0.1, 0.1, 0.1])
        self.sell_level = config.get('rsi_sell_level', 50)
        self.max_dca_level = len(self.buy_levels)
        
        # [V4.7.3] 상태 관리 변수
        # RSI 반등 확인 전까지 추가 매수를 금지하는 플래그
        self.awaiting_bounce = False 
        # 현재 하락 파동의 RSI 최저점을 기록
        self.rsi_low_watermark = 100.0
        # RSI가 최저점 대비 이만큼 오르면 "반등"으로 간주
        self.bounce_threshold = 10.0 

    def get_required_features(self) -> Dict[str, List[str]]:
        """
        [V4.7.2]
        - base (5m): 'rsi' (매매 로직용)
        - 1d (1일봉): 'regime' (리포팅용)
        """
        return {
            'base': ['rsi'],
            '1d': ['regime'] # 리포팅을 위해 항상 레짐 요청
        }

    def _reset_state(self):
        """모든 상태를 초기화합니다."""
        self.awaiting_bounce = False
        self.rsi_low_watermark = 100.0

    def generate_signal(self, data: pd.DataFrame, open_positions: List[Dict]) -> List[Dict[str, Any]]:
        """
        상태(State)를 기반으로 한 분할 매수 신호 생성
        """
        actions: List[Dict[str, Any]] = []
        if len(data) < 2: # prev_rsi 비교를 위해 최소 2개 데이터 필요
            return actions

        # 현재 상태
        current_row = data.iloc[-1]
        prev_row = data.iloc[-2]
        current_rsi = current_row['rsi']
        prev_rsi = prev_row['rsi'] # 반등 확인용
        
        current_dca_level = len(open_positions)
        
        # --- 1. 청산 로직 (가장 높은 우선순위) ---
        if current_dca_level > 0 and current_rsi > self.sell_level:
            actions.append({
                'action': 'close', 'percent': 1.0, # 100% 전량 청산
                'trade_mode': 'DCA_RSI',
                'reason': f'RSI {current_rsi:.2f} > {self.sell_level}'
            })
            # 청산 시 모든 상태 초기화
            self._reset_state()
            trading_logger.log_info(f"DCA_RSI: Full Sell Triggered. State Reset.")
            return actions # 청산 신호가 발생하면 추가 진입 X

        # --- 2. 최대 진입 횟수 도달 시 종료 ---
        if current_dca_level >= self.max_dca_level:
            return actions # 이미 최대 레벨, 추가 진입 X

        # --- 3. 상태별 분할 매수 로직 ---
        
        # [상태 1: "반등 대기" 상태]
        # 1차(또는 2차) 매수 직후, RSI가 충분히 반등할 때까지 대기
        if self.awaiting_bounce:
            # 3a. 현재 RSI가 이전 최저점보다 낮으면, 최저점 갱신
            if current_rsi < self.rsi_low_watermark:
                self.rsi_low_watermark = current_rsi
            
            # 3b. RSI가 최저점 대비 'bounce_threshold'만큼 반등했는지 확인
            elif current_rsi > self.rsi_low_watermark + self.bounce_threshold:
                # "반등" 확인!
                self.awaiting_bounce = False # 다음 하락 파동을 기다리는 상태로 전환
                self.rsi_low_watermark = 100.0 # 최저점 초기화
                trading_logger.log_info(f"DCA_RSI: Bounce Detected at RSI {current_rsi:.2f}. "
                                        f"Waiting for next dip (Level {current_dca_level+1}).")
            
            # (반등 대기 상태에서는 절대 추가 매수 안 함)
            return actions

        # [상태 2: "진입 대기" 상태]
        # (awaiting_bounce == False)
        # 현재 DCA 레벨에 맞는 다음 진입 조건을 확인함
        
        target_rsi = self.buy_levels[current_dca_level]
        buy_size = self.buy_sizes[current_dca_level]

        # 4. 진입 조건 확인: RSI가 목표보다 낮아졌는가?
        if current_rsi < target_rsi:
            actions.append({
                'action': 'buy',
                'size_pct': buy_size, # 현재 레벨의 비중
                'trade_mode': 'DCA_RSI',
                'reason': f'DCA Entry {current_dca_level+1} (RSI {current_rsi:.2f} < {target_rsi})'
            })
            
            # [중요] 매수 직후, "반등 대기" 상태로 전환
            self.awaiting_bounce = True
            # 현재 RSI를 이 파동의 최저점으로 설정
            self.rsi_low_watermark = current_rsi
            trading_logger.log_info(f"DCA_RSI: Level {current_dca_level+1} Buy Triggered at RSI {current_rsi:.2f}. "
                                    f"Awaiting bounce.")

        return actions

