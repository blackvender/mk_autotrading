import pandas as pd
import numpy as np
import ta
from typing import Dict, List, Any, Optional
from strategies.base_strategy import BaseStrategy
from datetime import datetime, timedelta

# --- V4.5.3의 전략 내부 로직 클래스들 ---
class DynamicThresholdManager:
    """동적 임계값 관리 클래스 (V4.5.3 원본 기반)"""
    def __init__(self, config: Dict):
        self.config = config
        self.volatility_history = []
        self.benchmark_atr_volatility = None # 기준 변동성
        
        # 설정값 로드
        self.dynamic_params = {
            'base_volatility': self.config.get('base_volatility', 0.02),
            'momentum_rsi_base': self.config.get('momentum_rsi_base', 65),
            'reversal_rsi_base': self.config.get('reversal_rsi_base', 25),
            'pullback_detection_atr_multiplier': 0.8,
            'crash_detection_atr_multiplier': 1.5,
            'base_position_size': 0.1,
            'max_portfolio_ratio': self.config.get('max_portfolio_ratio', 0.6),
            'max_dca_levels': self.config.get('max_dca_levels', 5),
            'momentum_time_stop_hours': 168,
            'reversal_time_stop_hours': 72,
        }
    
    def update_volatility_benchmark(self, current_atr_1d: float, current_price: float):
        """[V4.7] 변동성 벤치마크 업데이트 (1d ATR 기준)"""
        if current_price == 0 or pd.isna(current_atr_1d): return
        
        current_volatility = current_atr_1d / current_price
        self.volatility_history.append(current_volatility)
        if len(self.volatility_history) > 20: self.volatility_history.pop(0)
        
        if len(self.volatility_history) >= 10:
            self.benchmark_atr_volatility = np.median(self.volatility_history)

    def get_dynamic_threshold(self, threshold_type: str, current_atr: float, current_price: float) -> float:
        """[V4.7] 동적 임계값 계산"""
        static_value = self.dynamic_params.get(threshold_type, 0.5)
        
        if (self.benchmark_atr_volatility is None or current_price == 0 or 
            self.benchmark_atr_volatility == 0 or pd.isna(current_atr)):
            return static_value
            
        try:
            current_volatility = current_atr / current_price
            volatility_ratio = current_volatility / self.benchmark_atr_volatility
            # 변동성 비율에 따른 동적 조정 (조정 강도 50%)
            dynamic_adjustment = 1.0 + (volatility_ratio - 1.0) * 0.5
            return static_value * dynamic_adjustment
        except Exception:
            return static_value

class MultiTimeframeVolatilityAnalyzer:
    """[V4.7] 다중 시간프레임 변동성 분석기 (단순화)"""
    
    def analyze_volatility(self, current_row: pd.Series) -> Dict:
        """[V4.7] DF가 아닌, 모든 지표가 포함된 'current_row'를 받음"""
        try:
            current_price = current_row['close']
            if current_price == 0: return self.get_default_state()

            # 5m(base), 1h, 1d 변동성만 비교
            vol_5m = current_row['atr'] / current_price
            vol_1h = current_row['atr_1h'] / current_price
            vol_1d = current_row['atr_1d'] / current_price
            
            vol_trend = 'increasing' if vol_5m > vol_1h > vol_1d else 'decreasing' if vol_5m < vol_1h < vol_1d else 'stable'
            convergence = (vol_5m / vol_1h + vol_1h / vol_1d) / 2 if vol_1h > 0 and vol_1d > 0 else 1.0
            
            return {
                'overall_level': (vol_5m + vol_1h + vol_1d) / 3,
                'trend': vol_trend,
                'convergence': convergence,
                'state': 'expanding' if convergence > 1.1 else 'converging'
            }
        except Exception as e:
            return self.get_default_state()
            
    def get_default_state(self):
        return {'state': 'normal', 'trend': 'stable', 'overall_level': 0.02, 'convergence': 1.0}

# --- V4.7 전략 클래스 ---
class DynamicVolatilityStrategy_Refactored(BaseStrategy):
    """
    [V4.7] 리팩토링된 전략
    데이터 준비 로직이 제거되고, FeatureFactory가 생성한
    'featured_df' 하나에만 의존하여 의사결정을 수행합니다.
    """
    
    def __init__(self, config: Dict):
        """[V4.7] 생성자에서 더 이상 5개의 DataFrame을 받지 않습니다."""
        super().__init__("DynamicVolatilityStrategy_Refactored_v4.7", config)
        
        # [제거] self.df_24h, self.df_4h 등 모든 DataFrame 멤버 변수 제거
        
        self.threshold_manager = DynamicThresholdManager(config)
        self.volatility_analyzer = MultiTimeframeVolatilityAnalyzer()
        
        # 전략 상태
        self.current_mode = 'momentum'
        self.current_regime = "상승_횡보" # 기본값
        self.volatility_state = self.volatility_analyzer.get_default_state()
        self.dca_status = { 'momentum': {'current_level': 0}, 'reversal': {'current_level': 0} }
        self.take_profit_status = { 'momentum': {'stages_completed': 0}, 'reversal': {'stages_completed': 0} }
        self.mode_cooldown = {'momentum': 24, 'reversal': 48}
        self.last_mode_switch = None
        
        print("✅ Refactored Strategy v4.7 Initialized (Data-Independent)")
    
    def get_required_features(self) -> Dict[str, List[str]]:
        """
        [V4.7 신규]
        이 전략이 필요로 하는 지표의 명세서를 반환합니다.
        """
        return {
            # 메인 타임프레임(5m)에 필요한 지표
            'base': ['atr', 'atr_ma_20', 'volume_ma_20', 'bb_upper', 'ema_20'],
            
            # 상위 타임프레임에 필요한 지표
            '15m': ['rsi', 'atr'],
            '1h': ['rsi', 'atr', 'volume_avg_20', 'ema_14'], # 'volume_avg_20'
            '4h': ['rsi', 'ema_14', 'ema_50'],
            '1d': ['regime', 'atr', 'ema_14'] # 'regime'은 1d에서만 계산
        }

    def generate_signal(self, data: pd.DataFrame, open_positions: List[Dict]) -> List[Dict[str, Any]]:
        """[V4.7] 모든 지표가 병합된 'data' DataFrame을 받음"""
        try:
            if data.empty: return []
            current_row = data.iloc[-1]
            current_time = current_row['timestamp']
            current_price = current_row['close']
            actions = []
            
            # 1. 변동성 분석 업데이트
            self._update_volatility_analysis(current_row)
            
            # 2. 레짐 판단 (current_row에서 직접 읽기)
            self.current_regime = current_row['regime_1d'] 
            
            # 3. 모드 전환 확인
            self._check_mode_switch(current_time)
            
            # 4. 포지션 분류
            momentum_positions = [p for p in open_positions if p.get('trade_mode') == 'momentum']
            reversal_positions = [p for p in open_positions if p.get('trade_mode') == 'reversal']
            
            # 5. 청산 신호 생성
            if momentum_positions:
                actions.extend(self._calculate_momentum_exit_signals(momentum_positions, current_row))
            if reversal_positions:
                actions.extend(self._calculate_reversal_exit_signals(reversal_positions, current_row))
            
            # 6. 진입 신호 생성 (청산이 없을 때만)
            if not actions:
                if self.current_mode == 'momentum':
                    actions.extend(self._calculate_momentum_entry_signals(len(momentum_positions), current_row, data))
                elif self.current_mode == 'reversal':
                    actions.extend(self._calculate_reversal_entry_signals(len(reversal_positions), current_row, data))
            
            return actions
            
        except Exception as e:
            # print(f"❌ Signal generation error at {data.iloc[-1]['timestamp']}: {e}")
            return []
    
    def _update_volatility_analysis(self, current_row: pd.Series):
        """[V4.7] 변동성 분석 (current_row 사용)"""
        try:
            current_atr_1d = current_row['atr_1d']
            current_price = current_row['close']
            self.threshold_manager.update_volatility_benchmark(current_atr_1d, current_price)
            self.volatility_state = self.volatility_analyzer.analyze_volatility(current_row)
        except Exception as e:
            self.volatility_state = self.volatility_analyzer.get_default_state()

    def _check_mode_switch(self, current_time: datetime):
        """모드 전환 확인"""
        momentum_regimes = ["상승_강세", "상승_약세", "상승_횡보"]
        reversal_regimes = ["하락_강세", "하락_약세", "하락_횡보"]
        
        target_mode = None
        if self.current_regime in momentum_regimes: target_mode = 'momentum'
        elif self.current_regime in reversal_regimes: target_mode = 'reversal'
        
        if target_mode and target_mode != self.current_mode:
            if self.last_mode_switch:
                hours_since_switch = (current_time - self.last_mode_switch).total_seconds() / 3600
                cooldown_hours = self.mode_cooldown.get(self.current_mode, 24)
                if hours_since_switch < cooldown_hours: return
            
            self.current_mode = target_mode
            self.last_mode_switch = current_time

    def _calculate_momentum_entry_signals(self, num_entries: int, current_row: pd.Series, data: pd.DataFrame) -> List[Dict]:
        """[V4.7] 모멘텀 진입 (current_row 사용)"""
        actions = []
        max_levels = self.threshold_manager.dynamic_params['max_dca_levels']
        if num_entries >= max_levels: return actions
        
        try:
            current_price = current_row['close']
            current_atr = current_row['atr'] # 5m ATR
            
            # [수정] 지표를 self.df_4h가 아닌 current_row에서 직접 읽음
            rsi_4h = current_row['rsi_4h']
            rsi_15m = current_row['rsi_15m']
            ema_14_4h = current_row['ema_14_4h']
            ema_14_1h = current_row['ema_14_1h']
            
            dynamic_rsi_threshold = self.threshold_manager.get_dynamic_threshold(
                'momentum_rsi_base', current_atr, current_price
            )
            
            if num_entries == 0: # 초기 진입
                if (current_price > ema_14_4h and 
                    current_price > ema_14_1h and 
                    rsi_4h < dynamic_rsi_threshold and rsi_15m < 65):
                    
                    pos_size = self._calculate_dynamic_position_size('momentum', 0)
                    actions.append({
                        'action': 'buy', 'size_pct': pos_size, 'trade_mode': 'momentum',
                        'reason': 'Momentum Initial Entry',
                        'signal_details': {'rsi_4h': rsi_4h, 'regime': self.current_regime}
                    })
            else: # 물타기
                if self._detect_momentum_pullback(current_row, data):
                    pos_size = self._calculate_dynamic_position_size('momentum', num_entries)
                    actions.append({
                        'action': 'buy', 'size_pct': pos_size, 'trade_mode': 'momentum',
                        'reason': 'Momentum DCA - Pullback',
                        'signal_details': {'dca_level': num_entries + 1, 'rsi_15m': rsi_15m}
                    })
            return actions
        except Exception as e: return []
    
    def _calculate_reversal_entry_signals(self, num_entries: int, current_row: pd.Series, data: pd.DataFrame) -> List[Dict]:
        """[V4.7] 되돌림 진입 (current_row 사용)"""
        actions = []
        max_levels = self.threshold_manager.dynamic_params['max_dca_levels']
        if num_entries >= max_levels: return actions
        
        try:
            current_price = current_row['close']
            current_atr = current_row['atr']
            
            rsi_4h = current_row['rsi_4h']
            # 'volume_ma_20'은 5m 기준 (base)
            volume_decreasing = current_row['volume'] < current_row['volume_ma_20'] 
            
            dynamic_rsi_threshold = self.threshold_manager.get_dynamic_threshold(
                'reversal_rsi_base', current_atr, current_price
            )
            
            if num_entries == 0:
                if rsi_4h < dynamic_rsi_threshold and volume_decreasing:
                    pos_size = self._calculate_dynamic_position_size('reversal', 0)
                    actions.append({
                        'action': 'buy', 'size_pct': pos_size, 'trade_mode': 'reversal',
                        'reason': 'Reversal Initial Entry',
                        'signal_details': {'rsi_4h': rsi_4h, 'regime': self.current_regime}
                    })
            else:
                if self._detect_reversal_crash(current_row, data):
                    pos_size = self._calculate_dynamic_position_size('reversal', num_entries)
                    actions.append({
                        'action': 'buy', 'size_pct': pos_size, 'trade_mode': 'reversal',
                        'reason': 'Reversal DCA - Crash',
                        'signal_details': {'dca_level': num_entries + 1, 'rsi_15m': current_row['rsi_15m']}
                    })
            return actions
        except Exception as e: return []

    def _calculate_momentum_exit_signals(self, positions: List[Dict], current_row: pd.Series) -> List[Dict]:
        """[V4.7] 모멘텀 청산 (current_row 사용)"""
        current_time = current_row['timestamp']
        time_stop_hours = self.dynamic_params['momentum_time_stop_hours']
        
        hold_hours = (current_time - positions[0]['entry_time']).total_seconds() / 3600
        if hold_hours > time_stop_hours:
            return [{'action': 'close', 'percent': 1.0, 'reason': f'Momentum Time Stop ({time_stop_hours}h)', 'trade_mode': 'momentum'}]
            
        # (V4.5.3의 변동성 기반 수익 실현 로직은 생략되었으나, 필요시 여기에 추가)
        return []

    def _calculate_reversal_exit_signals(self, positions: List[Dict], current_row: pd.Series) -> List[Dict]:
        """[V4.7] 되돌림 청산 (current_row 사용)"""
        current_time = current_row['timestamp']
        time_stop_hours = self.dynamic_params['reversal_time_stop_hours']

        hold_hours = (current_time - positions[0]['entry_time']).total_seconds() / 3600
        if hold_hours > time_stop_hours:
            return [{'action': 'close', 'percent': 1.0, 'reason': f'Reversal Time Stop ({time_stop_hours}h)', 'trade_mode': 'reversal'}]
            
        return []

    def _detect_momentum_pullback(self, current_row: pd.Series, data: pd.DataFrame) -> bool:
        """[V4.7] 모멘텀 눌림목 감지 (current_row 사용)"""
        try:
            current_price = current_row['close']
            current_atr = current_row['atr'] # 5m ATR
            dynamic_threshold = self.threshold_manager.get_dynamic_threshold(
                'pullback_detection_atr_multiplier', current_atr, current_price
            )
            # 5분봉 기준 1봉 전 대비 하락폭
            daily_change = (current_price - data['close'].iloc[-2]) / data['close'].iloc[-2]
            
            rsi_condition = current_row['rsi_15m'] < 40
            volume_condition = current_row['volume'] > current_row['volume_ma_20']
            
            return (daily_change < -dynamic_threshold and rsi_condition and volume_condition)
        except: return False

    def _detect_reversal_crash(self, current_row: pd.Series, data: pd.DataFrame) -> bool:
        """[V4.7] 되돌림 급락 감지 (current_row 사용)"""
        try:
            current_price = current_row['close']
            current_atr = current_row['atr'] # 5m ATR
            dynamic_threshold = self.threshold_manager.get_dynamic_threshold(
                'crash_detection_atr_multiplier', current_atr, current_price
            )
            daily_change = (current_price - data['close'].iloc[-2]) / data['close'].iloc[-2]
            
            rsi_condition = current_row['rsi_15m'] < 25
            volatility_shock = current_atr > (current_row['atr_ma_20'] * 1.5)
            
            return (daily_change < -dynamic_threshold and rsi_condition and volatility_shock)
        except: return False

    def _calculate_dynamic_position_size(self, mode: str, current_level: int) -> float:
        """동적 포지션 사이징"""
        base_size = self.dynamic_params['base_position_size']
        volatility_adjustment = 1.0
        if self.volatility_state:
            vol_state = self.volatility_state['state']
            if vol_state == 'expanding': volatility_adjustment = 0.8
            else: volatility_adjustment = 1.2
        
        level_adjustment = 0.7 ** current_level
        raw_size = base_size * level_adjustment * volatility_adjustment
        position_size = max(raw_size, 0.005) # 최소 0.5%
        return min(position_size, self.dynamic_params['max_portfolio_ratio'])


