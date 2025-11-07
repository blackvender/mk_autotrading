from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Tuple, Optional, List, Any

class BaseStrategy(ABC):
    """
    [V4.7] 모든 전략의 부모 클래스
    """
    
    def __init__(self, name: str, config: Dict):
        self.name = name
        self.config = config
        self.positions = [] # 이 변수는 V4.7 엔진에서는 사용되지 않습니다.
        self.performance = {}
        self.signals_history = []
        
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame, open_positions: List[Dict]) -> List[Dict[str, Any]]:
        """
        거래 신호 생성
        
        Args:
            data (pd.DataFrame): 현재 시점까지의 모든 (병합된) 데이터
            open_positions (List[Dict]): 현재 엔진이 관리 중인 포지션 목록
            
        Returns:
            List[Dict[str, Any]]: 실행할 신호(action) 목록
        """
        pass

    @abstractmethod
    def get_required_features(self) -> Dict[str, List[str]]:
        """
        [V4.7 신규]
        이 전략이 필요로 하는 지표의 명세서를 반환합니다.
        FeatureFactory는 이 명세서를 보고 지표를 동적으로 생성합니다.
        
        예시:
        {
            'base': ['atr', 'volume_ma_20'], # 메인 타임프레임(5m)
            '1h': ['rsi', 'atr'],           # 1시간봉
            '4h': ['rsi', 'ema_14'],        # 4시간봉
            '1d': ['regime']                # 1일봉
        }
        """
        pass

    def update_balance(self, new_balance: float):
        """
        엔진이 현재 총 자산 가치(equity)를 전략에 업데이트할 수 있도록 허용합니다.
        """
        pass


