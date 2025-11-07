import pandas as pd
import numpy as np
import ta
from typing import Dict, List, Any, Optional
from strategies.base_strategy import BaseStrategy
from datetime import datetime, timedelta

# --- V4.5.3의 전략 내부 로직 클래스들 ---
# (DynamicThresholdManager, MultiTimeframeVolatilityAnalyzer 클래스는 수정 없이 원본 유지)
class DynamicThresholdManager:
    """동적 임계값 관리 클래스 (V4.5.3 원본 기반)"""
    def __init__(self, config: Dict):
        self.config = config
        self.volatility_history = []
        self.benchmark_atr_volatility = None # 기준 변동성
        
        # 설정값 로드
        self.dynamic_params = {
            'base_volatility': self.config.get('base_volatility', 0.02),
            # [v2.0] 이 값들은 더 이상 _calculate_..._entry_signals에서 직접 사용되지 않음
            # 'momentum_rsi_base': self.config.get('momentum_rsi_base', 65),
            # 'reversal_rsi_base': self.config.get('reversal_rsi_base', 25),
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
            dynamic_adjustment = 1.0 + (volatility_ratio - 1.0) * 0.5
            return static_value * dynamic_adjustment
        except Exception:
            return static_value

class MultiTimeframeVolatilityAnalyzer:
    """[V4.7] 다중 시간프레임 변동성 분석기 (v2.0 레짐 엔진의 보조로 사용)"""
    
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

# --- V4.7 -> V5.0 (Regime v2.0) 전략 클래스 ---
class DynamicStrategy_v2(BaseStrategy):
    """
    [V5.0 / Phase 3.2.4] v2.0 레짐 스코어 기반 전략
    v0.1의 'regime_1d' 대신 v2.0의 4대 핵심 점수를 기반으로
    모드를 결정하고 진입/청산 신호를 생성합니다.
    """
    
    def __init__(self, config: Dict):
        super().__init__("DynamicStrategy_v2_Regime", config)
        
        self.threshold_manager = DynamicThresholdManager(config)
        self.volatility_analyzer = MultiTimeframeVolatilityAnalyzer()
        
        # 전략 상태
        self.current_mode = 'momentum' # v2.0 스코어에 의해 동적으로 덮어써짐
        # [v2.0] self.current_regime 제거
        self.current_regime_label = "Transition" # [v2.0 신규] 모니터링용 라벨
        
        self.volatility_state = self.volatility_analyzer.get_default_state()
        self.dca_status = { 'momentum': {'current_level': 0}, 'reversal': {'current_level': 0} }
        self.take_profit_status = { 'momentum': {'stages_completed': 0}, 'reversal': {'stages_completed': 0} }
        
        # [v2.0] 모드 전환 로직은 _check_mode_switch에서 v2.0 스코어 기반으로 변경됨
        self.mode_cooldown = {'momentum': 24, 'reversal': 48}
        self.last_mode_switch = None
        
        print("✅ Strategy v2.0 (Regime Score Based) Initialized.")
    
    def get_required_features(self) -> Dict[str, List[str]]:
        """
        [v2.0 수정 / Checklist 2]
        v2.0 레짐 엔진의 5개 컬럼과 S/R Zone을 명시적으로 요청합니다.
        """
        return {
            # 메인 타임프레임(5m)에 필요한 지표
            'base': ['atr', 'atr_ma_20', 'volume_ma_20', 'bb_upper', 'ema_20'],
            
            # 상위 타임프레임에 필요한 지표
            '15m': ['rsi', 'atr'], # DCA 로직에서 아직 사용
            '1h': ['rsi', 'atr', 'volume_avg_20', 'ema_14'], 
            '4h': ['rsi', 'ema_14', 'ema_50'], # v0.1 잔여 (정리 필요)
            
            # [v2.0] 1d 요구사항 전면 수정
            '1d': [
                'atr', 'ema_14', # 기존 요구사항
                
                # --- v2.0 신규 요구사항 ---
                'regime_label_1d',          # (필수) v2.0 엔진 트리거 및 모니터링
                'regime_trend_score',       # (필수) 핵심 전략 점수 1
                'regime_energy_score',      # (필수) 핵심 전략 점수 2
                'regime_reversion_score',   # (필수) 핵심 전략 점수 3
                'regime_sr_pressure_score', # (필수) 핵심 전략 점수 4
                
                # --- S/R Zone (Phase 3.2.1) 요구사항 ---
                'support_1d',
                'resistance_1d',
                'support_score_1d',
                'resistance_score_1d'
            ]
        }

    def generate_signal(self, data: pd.DataFrame, open_positions: List[Dict]) -> List[Dict[str, Any]]:
        """[v2.0] v2.0 스코어 기반으로 모드를 결정하고 신호 생성"""
        try:
            if data.empty: return []
            current_row = data.iloc[-1]
            current_time = current_row['timestamp']
            current_price = current_row['close']
            actions = []
            
            # 1. 변동성 분석 업데이트 (v4.7과 동일)
            self._update_volatility_analysis(current_row)
            
            # 2. [v2.0] 레짐 라벨 (모니터링용)
            self.current_regime_label = current_row['regime_label_1d'] 
            
            # 3. [v2.0] 스코어 기반 모드 전환 확인 (핵심 수정)
            self._check_mode_switch_v2(current_row, current_time)
            
            # 4. 포지션 분류 (v4.7과 동일)
            momentum_positions = [p for p in open_positions if p.get('trade_mode') == 'momentum']
            reversal_positions = [p for p in open_positions if p.get('trade_mode') == 'reversal']
            
            # 5. [v2.0 수정] 청산 신호 생성 (핵심 수정)
            if momentum_positions:
                actions.extend(self._calculate_momentum_exit_signals_v2(momentum_positions, current_row))
            if reversal_positions:
                actions.extend(self._calculate_reversal_exit_signals_v2(reversal_positions, current_row))
            
            # 6. 진입 신호 생성 (청산이 없을 때만)
            if not actions:
                # [v2.0] _calculate_..._entry_signals 내부에서 v2.0 스코어로 진입 결정
                if self.current_mode == 'momentum':
                    actions.extend(self._calculate_momentum_entry_signals_v2(len(momentum_positions), current_row, data))
                elif self.current_mode == 'reversal':
                    actions.extend(self._calculate_reversal_entry_signals_v2(len(reversal_positions), current_row, data))
            
            return actions
            
        except KeyError as e:
            # v2.0 컬럼이 누락되었는지 확인
            # print(f"❌ Signal generation error: Missing key {e} at {current_row['timestamp']}. Check get_required_features.")
            return []
        except Exception as e:
            # print(f"❌ Signal generation error at {current_row['timestamp']}: {e}")
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

    def _check_mode_switch_v2(self, current_row: pd.Series, current_time: datetime):
        """
        [v2.0 수정 / Checklist 3]
        v0.1 라벨 대신 v2.0 스코어로 모드를 결정합니다.
        """
        # 1. v2.0 스코어 읽기
        s_trend = current_row['regime_trend_score']
        s_reversion = current_row['regime_reversion_score']
        
        # 2. 스코어 기반 모드 결정
        target_mode = None
        if s_trend > 0.3: # 추세 점수가 긍정적일 때
            target_mode = 'momentum'
        elif s_trend < -0.3 and s_reversion < -0.5: # 추세가 부정적이고 과매도일 때
            target_mode = 'reversal'
        
        # 3. 쿨다운 로직 (v4.7과 동일)
        if target_mode and target_mode != self.current_mode:
            if self.last_mode_switch:
                hours_since_switch = (current_time - self.last_mode_switch).total_seconds() / 3600
                cooldown_hours = self.mode_cooldown.get(self.current_mode, 24)
                if hours_since_switch < cooldown_hours: return
            
            self.current_mode = target_mode
            self.last_mode_switch = current_time

    def _calculate_momentum_entry_signals_v2(self, num_entries: int, current_row: pd.Series, data: pd.DataFrame) -> List[Dict]:
        """
        [v2.0 수정 / Checklist 3]
        v0.1 RSI/EMA 대신 v2.0 스코어로 진입을 결정합니다.
        """
        actions = []
        max_levels = self.threshold_manager.dynamic_params['max_dca_levels']
        if num_entries >= max_levels: return actions
        
        try:
            # 1. v2.0 스코어 읽기
            s_trend = current_row['regime_trend_score']
            s_energy = current_row['regime_energy_score']
            s_sr = current_row['regime_sr_pressure_score'] # +1(지지) ~ -1(저항)
            
            if num_entries == 0: # 초기 진입
                # [v2.0 로직] Uptrend-Impulse (강한 상승 방출) 확인
                # (s_trend > 0.5) 및 (s_energy > 0.7) 
                if (s_trend > 0.5 and s_energy > 0.7):
                    
                    pos_size = self._calculate_dynamic_position_size('momentum', 0)
                    actions.append({
                        'action': 'buy', 'size_pct': pos_size, 'trade_mode': 'momentum',
                        'reason': 'Momentum v2.0 Entry (Impulse)',
                        'signal_details': {'trend': s_trend, 'energy': s_energy, 'label': self.current_regime_label}
                    })
            else: # DCA 진입
                # [v2.0 로직] S/R 압력 점수 기반 눌림목 매수 (지지 근접)
                # (s_sr > 0.8: 지지선에 매우 근접)
                if s_sr > 0.8: 
                    pos_size = self._calculate_dynamic_position_size('momentum', num_entries)
                    actions.append({
                        'action': 'buy', 'size_pct': pos_size, 'trade_mode': 'momentum',
                        'reason': 'Momentum v2.0 DCA (S/R Pressure)',
                        'signal_details': {'dca_level': num_entries + 1, 'sr_pressure': s_sr}
                    })
            return actions
        except Exception as e: return []
    
    def _calculate_reversal_entry_signals_v2(self, num_entries: int, current_row: pd.Series, data: pd.DataFrame) -> List[Dict]:
        """
        [v2.0 수정 / Checklist 3]
        v0.1 RSI 대신 v2.0 스코어로 진입을 결정합니다.
        """
        actions = []
        max_levels = self.threshold_manager.dynamic_params['max_dca_levels']
        if num_entries >= max_levels: return actions
        
        try:
            # 1. v2.0 스코어 읽기
            s_reversion = current_row['regime_reversion_score']
            s_energy = current_row['regime_energy_score']
            
            if num_entries == 0: # 초기 진입
                # [v2.0 로직] Transition (과매도/급락) 확인
                # (s_reversion < -0.8) 및 (s_energy > 0.5: 에너지가 있어야 되돌림) 
                if (s_reversion < -0.8 and s_energy > 0.5):
                    pos_size = self._calculate_dynamic_position_size('reversal', 0)
                    actions.append({
                        'action': 'buy', 'size_pct': pos_size, 'trade_mode': 'reversal',
                        'reason': 'Reversal v2.0 Entry (Oversold)',
                        'signal_details': {'reversion': s_reversion, 'energy': s_energy, 'label': self.current_regime_label}
                    })
            else: # DCA 진입
                # [v2.0 로직] 더 깊은 과매도 (패닉)
                if s_reversion < -0.95: # 더 깊은 과매도
                    pos_size = self._calculate_dynamic_position_size('reversal', num_entries)
                    actions.append({
                        'action': 'buy', 'size_pct': pos_size, 'trade_mode': 'reversal',
                        'reason': 'Reversal v2.0 DCA (Panic)',
                        'signal_details': {'dca_level': num_entries + 1, 'reversion': s_reversion}
                    })
            return actions
        except Exception as e: return []

    def _calculate_momentum_exit_signals_v2(self, positions: List[Dict], current_row: pd.Series) -> List[Dict]:
        """[v2.0 수정] MDD 해결을 위해 v2.0 스코어 기반 청산 로직 추가"""
        
        # --- [v2.0 수정] v2.0 스코어 기반 청산 ---
        s_trend = current_row['regime_trend_score']
        s_reversion = current_row['regime_reversion_score']
        
        # 1. 추세가 꺾이거나(0.1 미만) 과매수(0.9 초과)일 때 청산
        if s_trend < 0.1:
            return [{'action': 'close', 'percent': 1.0, 'reason': f'Momentum v2.0 Exit (Trend Died)', 'trade_mode': 'momentum'}]
        
        if s_reversion > 0.9:
            return [{'action': 'close', 'percent': 1.0, 'reason': f'Momentum v2.0 Exit (Overbought TP)', 'trade_mode': 'momentum'}]
        # --- [v2.0 수정 완료] ---

        # [v4.7] 기존 타임 스탑 로직 (안전장치)
        current_time = current_row['timestamp']
        time_stop_hours = self.threshold_manager.dynamic_params['momentum_time_stop_hours']
        
        hold_hours = (current_time - positions[0]['entry_time']).total_seconds() / 3600
        if hold_hours > time_stop_hours:
            return [{'action': 'close', 'percent': 1.0, 'reason': f'Momentum Time Stop ({time_stop_hours}h)', 'trade_mode': 'momentum'}]
            
        return []

    def _calculate_reversal_exit_signals_v2(self, positions: List[Dict], current_row: pd.Series) -> List[Dict]:
        """[v2.0 수정] MDD 해결을 위해 v2.0 스코어 기반 청산 로직 추가"""
        
        # --- [v2.0 수정] v2.0 스코어 기반 청산 ---
        s_reversion = current_row['regime_reversion_score']
        
        # 1. 과매도(reversal)가 끝나고 과매수(>0.8) 구간에 진입 시 수익 실현
        if s_reversion > 0.8:
             return [{'action': 'close', 'percent': 1.0, 'reason': f'Reversal v2.0 Exit (Overbought TP)', 'trade_mode': 'reversal'}]
        # --- [v2.0 수정 완료] ---

        # [v4.7] 기존 타임 스탑 로직 (안전장치)
        current_time = current_row['timestamp']
        time_stop_hours = self.threshold_manager.dynamic_params['reversal_time_stop_hours']

        hold_hours = (current_time - positions[0]['entry_time']).total_seconds() / 3600
        if hold_hours > time_stop_hours:
            return [{'action': 'close', 'percent': 1.0, 'reason': f'Reversal Time Stop ({time_stop_hours}h)', 'trade_mode': 'reversal'}]
            
        return []

    # --- v4.7 원본 로직 (수정 없이 유지) ---
    def _detect_momentum_pullback(self, current_row: pd.Series, data: pd.DataFrame) -> bool:
        """[v4.7] 모멘텀 눌림목 감지 (v2.0에서는 사용되지 않음, DCA 로직 변경됨)"""
        try:
            current_price = current_row['close']
            current_atr = current_row['atr'] # 5m ATR
            dynamic_threshold = self.threshold_manager.get_dynamic_threshold(
                'pullback_detection_atr_multiplier', current_atr, current_price
            )
            daily_change = (current_price - data['close'].iloc[-2]) / data['close'].iloc[-2]
            
            rsi_condition = current_row['rsi_15m'] < 40
            volume_condition = current_row['volume'] > current_row['volume_ma_20']
            
            return (daily_change < -dynamic_threshold and rsi_condition and volume_condition)
        except: return False

    def _detect_reversal_crash(self, current_row: pd.Series, data: pd.DataFrame) -> bool:
        """[v4.7] 되돌림 급락 감지 (v2.0에서는 사용되지 않음, DCA 로직 변경됨)"""
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
        base_size = self.threshold_manager.dynamic_params['base_position_size']
        volatility_adjustment = 1.0
        if self.volatility_state:
            vol_state = self.volatility_state['state']
            if vol_state == 'expanding': volatility_adjustment = 0.8
            else: volatility_adjustment = 1.2
        
        level_adjustment = 0.7 ** current_level
        raw_size = base_size * level_adjustment * volatility_adjustment
        position_size = max(raw_size, 0.005) # 최소 0.5%
        return min(position_size, self.threshold_manager.dynamic_params['max_portfolio_ratio'])