import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

# --- V4.5.3의 TradingCycle 클래스를 이곳으로 이동 ---
# (엔진과 리포터가 공통으로 사용하는 핵심 데이터 모델)
class TradingCycle:
    """
    [V5.5]
    - (PnL, AvgPrice) v4.11 로직 유지
    - (MDD 0.00% 버그) v5.5에서 _update_drawdown_calculation 수정
    """
    
    def __init__(self, cycle_id, start_time, initial_balance, mode):
        self.cycle_id = cycle_id
        self.start_time = start_time
        self.initial_balance = initial_balance 
        self.mode = mode
        self.positions: List[Dict[str, Any]] = []
        
        # [V4.9] entry_balance는 사이클 시작 시점의 '총 자산' (Equity)
        self.entry_balance = initial_balance 
        
        self.cycle_pnl = 0.0
        self.total_investment = 0.0 
        
        # 자산 곡선
        self.equity_curve: List[Dict[str, Any]] = [{
            'timestamp': start_time, 'equity': initial_balance,
            'price': 0, 'drawdown': 0
        }]
        
        # [V5.5] max_drawdown은 0.0 (비율)으로 초기화
        self.max_drawdown = 0.0
        
        # [V5.5] MDD 계산 기준점을 'entry_balance'로 고정 (Fixed Peak)
        self.peak_equity = initial_balance
        self.is_active = True
        self.start_price = 0
        self.end_price = 0
        
        # MDD 분석용
        self.drawdown_curve = [0]
        # [V5.5] Fixed Peak 이므로 peak_points는 시작점 하나만 가짐
        self.peak_points = [{'equity': initial_balance, 'timestamp': start_time}]
        self.trough_points = [{'equity': initial_balance, 'timestamp': start_time}] # 최저점을 기록

        # 차트 생성용
        self.chart_data_points: List[Dict[str, Any]] = []
        self.signals_history: List[Dict[str, Any]] = []
    
    def add_chart_data_point(self, timestamp, price, equity, signals, positions, balance):
        """차트 생성을 위한 데이터 포인트 추가"""
        data_point = {
            'timestamp': timestamp, 'price': price, 'equity': equity,
            'signals': signals.copy() if signals else [],
            'positions': positions.copy(), 'balance': balance
        }
        self.chart_data_points.append(data_point)
        
        equity_point = {
            'timestamp': timestamp, 'equity': equity,
            'price': price, 'drawdown': 0
        }
        self.equity_curve.append(equity_point)
        self._update_drawdown_calculation(timestamp, equity)
        
        if signals:
            for signal in signals:
                self.signals_history.append({
                    'timestamp': timestamp, 'signal': signal.copy(), 'price': price
                })
                
    def _update_drawdown_calculation(self, timestamp, current_equity):
        """
        [V5.5 BUG FIX] MDD 0.00% 오류 수정
        - 사용자 요구사항: "첫 진입 에쿼티 대비 최대 하락" (Fixed Peak)
        - V4.11 로직은 수익권($120)에서 하락($110) 시 current_drawdown이 음수가 되어 
        - max_drawdown(0)을 갱신하지 못하는 오류가 있었음.
        
        - [FIX] 자산이 시작점(peak_equity)보다 *아래로 내려간 경우에만* MDD를 갱신합니다.
        """
        try:
            # [V5.5] peak_equity는 self.entry_balance (첫 진입 자산)로 항상 고정
            
            # [V5.5] (중요) current_drawdown은 (첫 진입 자산 - 현재 자산)입니다.
            # 이 값이 '양수'일 때만(즉, 하락했을 때만) 갱신합니다.
            current_drawdown_pct = (self.peak_equity - current_equity) / self.peak_equity if self.peak_equity > 0 else 0
            
            # [V5.5 BUG FIX]
            # 만약 current_drawdown_pct가 0보다 크다면 (즉, 실제 손실 구간)
            # max_drawdown과 비교하여 갱신합니다.
            if current_drawdown_pct > 0:
                if current_drawdown_pct > self.max_drawdown:
                    self.max_drawdown = current_drawdown_pct
            
            # [V5.5] 자산 곡선에는 현재 상태를 그대로 기록
            # (음수/양수 모두 기록, -0.1 (수익권) 또는 +0.05 (손실권))
            self.drawdown_curve.append(current_drawdown_pct) 
            if self.equity_curve:
                # [V5.5] (수정) 0보다 큰 경우에만 하락률을 기록합니다.
                self.equity_curve[-1]['drawdown'] = max(0, current_drawdown_pct)

            # [V5.5] 최저점(Trough)은 항상 갱신 (get_mdd_analysis에서 사용)
            self.trough_points.append({'timestamp': timestamp, 'equity': current_equity})
            
        except Exception as e:
            print(f"⚠️ MDD calculation error: {e}")
   
    def get_mdd_analysis(self) -> Dict[str, Any]:
        """[V5.5] Fixed Peak MDD 상세 분석 로직"""
        try:
            if not self.equity_curve or len(self.equity_curve) < 2:
                return self._get_default_mdd_analysis()

            # [V5.5] "첫 진입 에쿼티"(peak_point)는 항상 고정
            corresponding_peak = self.peak_points[0] # __init__에서 설정된 시작점
            peak_equity = corresponding_peak.get('equity', self.initial_balance)
            peak_time = corresponding_peak.get('timestamp', self.start_time)

            # [V5.5] equity_curve에서 "가장 낮았던 지점"을 찾음
            # min() 함수는 equity_curve 리스트 전체를 검색하여 'equity' 키가 가장 낮은 딕셔너리를 반환
            max_dd_trough_point = min(self.equity_curve, key=lambda x: x.get('equity', float('inf')))
            trough_equity = max_dd_trough_point.get('equity', self.initial_balance)
            trough_time = max_dd_trough_point.get('timestamp', self.start_time)

            # [V5.5] (중요) MDD% 계산
            # self.max_drawdown은 _update_drawdown_calculation에서 5분봉마다
            # (peak - current) / peak > max_drawdown을 검사하므로 
            # 가장 정확한 "Fixed Peak" MDD 비율(0.4011)을 가짐
            
            final_mdd_pct = self.max_drawdown * 100
            
            if final_mdd_pct > 0:
                 # MDD가 발생함 (Cycle 9)
                 max_drawdown_amount = peak_equity * self.max_drawdown
                 # (trough_equity, trough_time은 근사치로 사용)
            else:
                 # MDD가 0.00%임 (Cycle 7, 8)
                 max_drawdown_amount = 0.0
                 trough_equity = peak_equity
                 trough_time = peak_time

            return {
                'max_drawdown_pct': final_mdd_pct,
                'max_drawdown_amount': max_drawdown_amount,
                'peak_equity': peak_equity, 'trough_equity': trough_equity,
                'peak_time': peak_time, 'trough_time': trough_time,
                'recovery_info': self._calculate_recovery_info(corresponding_peak, max_dd_trough_point),
                'drawdown_duration_hours': (trough_time - peak_time).total_seconds() / 3600
            }
        except Exception as e:
            print(f"⚠️ get_mdd_analysis error: {e}")
            return self._get_default_mdd_analysis()
    
    def _get_default_mdd_analysis(self):
        """기본 MDD 분석 데이터 반환"""
        return {
            'max_drawdown_pct': 0, 'max_drawdown_amount': 0,
            'peak_equity': self.entry_balance, 'trough_equity': self.entry_balance,
            'peak_time': self.start_time, 'trough_time': self.start_time,
            'recovery_info': 'No drawdown data', 'drawdown_duration_hours': 0
        }
    
    def _calculate_recovery_info(self, peak_point, trough_point):
        """회복 기간 및 정보 계산 (V4.5.3 원본)"""
        try:
            recovery_time = None
            for equity_point in self.equity_curve:
                if (isinstance(equity_point, dict) and 
                    equity_point.get('timestamp') > trough_point['timestamp'] and 
                    equity_point.get('equity', 0) >= peak_point['equity']):
                    recovery_time = equity_point['timestamp']
                    break
            
            if recovery_time:
                recovery_hours = (recovery_time - trough_point['timestamp']).total_seconds() / 3600
                return f"Recovered in {recovery_hours:.1f}h"
            else:
                return "Not recovered" if not self.is_active else "Active"
        except Exception as e:
            return "Recovery data unavailable"
            
    def add_position(self, position):
        """[V4.11 수정] 포지션의 '복사본'을 추가 (평단가 계산 오류 수정)"""
        # [V4.11 FIX] 엔진의 position 객체를 참조하지 않고 복사본을 저장
        self.positions.append(position.copy()) 
        
        if len(self.positions) == 1: 
            self.start_price = position['entry_price']
        
        # [V4.9 추가] 총 투자금액(레버리지 포함) 누적
        self.total_investment += position.get('position_size', 0)

    def add_close_signal(self, timestamp, signal, price):
        self.signals_history.append({
            'timestamp': timestamp, 'signal': signal,
            'price': price, 'action': 'close'
        })
            
    def calculate_current_equity(self, current_price, current_balance):
        position_value = sum(p['quantity'] * current_price for p in self.positions)
        return current_balance + position_value

    def close_cycle(self, end_time, final_equity, final_price): # <-- [FIX 1] 파라미터 2번을 final_equity로 변경
        """[V4.9 수정] 사이클 종료 시 PnL 계산"""
        self.end_time = end_time
        self.final_balance = final_equity # <-- [FIX 2] 전달받은 final_equity를 그대로 사용
        self.end_price = final_price
        self.is_active = False
        
        # final_equity = self.calculate_current_equity(final_price, final_balance) # <-- [FIX 3] 버그 유발하는 재계산 로직 제거
        
        if self.entry_balance > 0:
            self.cycle_return = (final_equity - self.entry_balance) / self.entry_balance # <-- 올바른 final_equity로 수익률 계산
        else:
            self.cycle_return = 0
            
        # [V4.9 추가] USDT 기준 PnL 저장
        self.cycle_pnl = final_equity - self.entry_balance

    def get_summary(self):
        """[V4.11 수정] 사이클 요약 정보 (평단가, PnL, 총투자금 추가)"""
        try:
            # [V4.11] add_position(position.copy()) 수정으로 인해 self.positions가 정확한 수량을 유지
            total_quantity = sum(p.get('quantity', 0) for p in self.positions)
            total_cost = sum(p.get('entry_price', 0) * p.get('quantity', 0) for p in self.positions)
            avg_entry_price = total_cost / total_quantity if total_quantity > 0 else self.start_price
            
            mdd_analysis = self.get_mdd_analysis()
            
            return {
                'cycle_id': self.cycle_id, 'mode': self.mode,
                'start_time': self.start_time, 'end_time': getattr(self, 'end_time', None),
                'positions_count': len(self.positions),
                'initial_balance': self.entry_balance, 'final_balance': getattr(self, 'final_balance', self.entry_balance),
                
                # [V4.9 추가]
                'total_invested': self.total_investment, # 총 투자 원금 (USDT)
                'avg_entry_price': avg_entry_price,      # 평단가
                'cycle_pnl': self.cycle_pnl,             # 순손익 (USDT)
                
                'return_pct': getattr(self, 'cycle_return', 0) * 100,
                'max_drawdown': mdd_analysis['max_drawdown_pct'],
                'max_drawdown_amount': mdd_analysis['max_drawdown_amount'],
                'drawdown_duration': mdd_analysis['drawdown_duration_hours'],
                'recovery_info': mdd_analysis['recovery_info'],
                'duration_hours': (getattr(self, 'end_time', self.start_time) - self.start_time).total_seconds() / 3600 if hasattr(self, 'end_time') else 0
            }
        except Exception as e:
            print(f"❌ Cycle get_summary error: {e}")
            return self._get_default_summary()
    
    def _get_default_summary(self):
        return { 'cycle_id': self.cycle_id, 'mode': self.mode, 'start_time': self.start_time, 'end_time': None,
            'positions_count': 0, 'initial_balance': self.entry_balance, 'final_balance': self.entry_balance,
            'total_invested': 0, 'avg_entry_price': 0, 'cycle_pnl': 0,
            'return_pct': 0, 'max_drawdown': 0, 'max_drawdown_amount': 0,
            'drawdown_duration': 0, 'recovery_info': 'Data unavailable', 'duration_hours': 0
        }

    def get_chart_cycle_data(self):
        return self.chart_data_points
    
    def get_position_details_for_chart(self):
        """차트용 포지션 상세 정보 생성 (V4.5.3 원본)"""
        position_details = []
        for signal_data in self.signals_history:
            signal = signal_data['signal']
            action_type = signal.get('action')
            if action_type == 'buy':
                position_details.append({
                    'time': signal_data['timestamp'], 'price': signal_data['price'],
                    'size': signal.get('size_pct', 0), 'mode': signal.get('trade_mode', 'unknown'),
                    'reason': signal.get('reason', ''), 'type': 'BUY', 'action': 'entry'
                })
            elif action_type == 'close':
                position_details.append({
                    'time': signal_data['timestamp'], 'price': signal_data['price'],
                    'size': signal.get('percent', 0), 'mode': signal.get('trade_mode', 'unknown'),
                    'reason': signal.get('reason', ''), 'type': 'SELL', 'action': 'exit'
                })
        return position_details

# --- V4.6 신규: 표준 결과 객체 ---
@dataclass
class BacktestResult:
    """
    백테스트 엔진이 리포팅 서비스로 전달하는 표준 결과 객체입니다.
    이 객체는 모든 원시 데이터와 성과 지표를 포함합니다.
    """
    metrics: Dict[str, Any]
    trades: List[Dict[str, Any]]
    trading_cycles: List[TradingCycle]
    config: Dict[str, Any]
    strategy_name: str
    backtest_period: str
    featured_dataframe: pd.DataFrame
    regime_data: Optional[pd.DataFrame] = None