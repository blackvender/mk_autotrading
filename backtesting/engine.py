import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import os
import json
from backtesting.performance_metrics import PerformanceMetrics
from reporting.report_models import BacktestResult, TradingCycle
import warnings

warnings.filterwarnings('ignore')

class AdvancedBacktestEngine:
    
    def __init__(self, config: Dict):
        
        # 설정 로드
        self.initial_balance = config.get('initial_balance', 6000)
        self.current_balance = self.initial_balance # 실제 현금 잔고
        self.total_equity = self.initial_balance     # 총 자산 가치 (현금 + 포지션 가치)
        self.commission = config.get('commission', 0.0004)
        self.slippage = config.get('slippage', 0.0001)
        self.risk_per_trade_total = config.get('risk_per_trade_total', 0.02)
        self.max_leverage = config.get('max_leverage', 8)
        self.max_open_entries = config.get('max_open_entries', 5)
        self.language = config.get('language', 'en')
        
        self.strategy_name = "Unknown Strategy"
        self.backtest_start_date = None
        self.backtest_end_date = None
        self.actual_backtest_period = "N/A"
        
        # V4.5.3 사이클 관리 시스템
        self.trading_cycles: List[TradingCycle] = [] # 모든 완료된 사이클
        self.active_cycle: Optional[TradingCycle] = None # 현재 활성 사이클
        self.cycle_counter = 0

        # 트레이딩 상태
        self.positions: List[Dict[str, Any]] = []
        self.trade_history: List[Dict[str, Any]] = []
        self.equity_curve: List[float] = [self.initial_balance]

        # V4.7 리포팅용 데이터
        self.regime_data: Optional[pd.DataFrame] = None
        
        print("✅ Refactored Backtest Engine V4.7 Initialized (Execution-Only)")

    def _t(self, text: str) -> str:
        if self.language == 'ko':
            return text
        return text

    def calculate_total_equity(self, current_price: float) -> float:
        """
        [FIX] V5.7:
        총 자산(Equity)을 '현금 + (포지션의 현재 가치)'로 재정의합니다.
        - 포지션의 현재 가치 = (사용된 마진) + (현재 미실현 손익)
        - 이전 로직 (self.current_balance + position_value)은
          position_value가 레버리지가 포함된 '총 포지션 규모'를 반환하여
          에쿼티 계산에 오류를 유발했습니다. (예: $6000가 아닌 $48000 반환)
        """
        
        # 1. 모든 오픈 포지션의 가치를 계산
        total_position_equity = 0
        if self.positions:
            for p in self.positions:
                # 미실현 손익 (Unrealized PnL)
                unrealized_pnl = (current_price - p['entry_price']) * p['quantity']
                
                # 현재 이 포지션이 차지하는 에쿼티 = 사용된 마진 + 미실현 손익
                # (수수료는 이미 current_balance에서 차감되었음)
                total_position_equity += (p['margin_used'] + unrealized_pnl)

        # 2. 총 자산 = (남은 현금) + (모든 포지션의 현재 에쿼티 가치)
        return self.current_balance + total_position_equity

    def update_equity_curve(self, current_price: float):
        """자산 곡선 업데이트"""
        self.total_equity = self.calculate_total_equity(current_price)
        self.equity_curve.append(self.total_equity)

    def run_custom_period_backtest(self, df: pd.DataFrame, strategy, 
                                   start_date: Optional[str] = None, 
                                   end_date: Optional[str] = None) -> BacktestResult:
        
        self.backtest_start_date = start_date
        self.backtest_end_date = end_date
        self._extract_strategy_name(strategy)

        # 날짜 필터링
        if start_date: df = df[df['timestamp'] >= pd.to_datetime(start_date)].copy()
        if end_date: df = df[df['timestamp'] <= pd.to_datetime(end_date)].copy()
            
        if len(df) == 0:
            raise ValueError("No data found for the specified period.")
            
        self._calculate_actual_backtest_period(df, start_date, end_date)
        
        if 'regime_label_1d' in df.columns:
            self.regime_data = df[['timestamp', 'regime_label_1d']].copy()
            self.regime_data.rename(columns={'regime_label_1d': 'regime_1d'}, inplace=True)
        elif 'regime_1d' in df.columns:
             self.regime_data = df[['timestamp', 'regime_1d']].copy()
        else:
            print("   [Engine] ⚠️ 'regime_label_1d' (v2.0) column not found. Regime reporting will be 'Unknown'.")
        
        # 백테스트 실행
        trades, metrics = self._run_backtest(df, strategy)
        
        # [V4.6] 표준 결과 객체 생성
        result = BacktestResult(
            metrics=metrics,
            trades=self.trade_history,
            trading_cycles=self.trading_cycles,
            config=self._get_config_dict(),
            strategy_name=self.strategy_name,
            backtest_period=self.actual_backtest_period,
            featured_dataframe=df,
            regime_data=self.regime_data
        )
        return result

    def _run_backtest(self, df: pd.DataFrame, strategy) -> tuple:
        """
        [V5.5] (중요) PnL $+16,177 버그 수정
        - Mode Switch 시, Cycle 8의 최종 자산을 Cycle 9의 'BUY' 실행 *전* 자산으로 사용
        """
        print("   [Engine] Running main backtest loop...")
        
        self.equity_curve = [self.initial_balance]
        self.trading_cycles = []
        self.active_cycle = None
        self.cycle_counter = 0
        
        for i in range(1, len(df)):
            try:
                current_data = df.iloc[:i]
                current_row = df.iloc[i]
                current_time = current_row['timestamp']
                current_price = current_row['close'] # [FIX] '종가'는 계속 사용
                
                if pd.isna(current_price):
                    continue
                
                current_equity_before_trade = self.calculate_total_equity(current_price)
                if hasattr(strategy, 'update_balance'):
                    strategy.update_balance(current_equity_before_trade)
                
                signals = strategy.generate_signal(current_data, self.positions)
                
                cycle_to_finalize = None
                
                for signal in signals:
                    closed_cycle_obj = self._execute_signal_with_cycle(
                        signal, current_row, current_time, current_data, current_equity_before_trade
                    )
                    if closed_cycle_obj:
                        cycle_to_finalize = closed_cycle_obj
                
                # [V5.5] (중요) 'BUY'/'CLOSE'가 *모두* 실행된 후의 최종 자산 ('종가' 기준)
                current_equity_after_trade = self.calculate_total_equity(current_price)

                # --- [FIX] MDD 계산 로직 수정 ---
                if self.active_cycle:
                    # [FIX] MDD 계산을 위해 '저가(low)' 기준의 에쿼티를 별도 계산
                    # current_row에 'low' 컬럼이 있어야 합니다.
                    current_low_price = current_row['low']
                    equity_at_low = self.calculate_total_equity(current_low_price)

                    self.active_cycle.add_chart_data_point(
                        current_time, 
                        current_price,              # 차트용 가격은 '종가' 유지
                        equity_at_low,              # MDD 계산용 에쿼티는 '저가' 기준 값 전달
                        signals, 
                        self.positions, 
                        self.current_balance
                    )
                # --- [FIX] 수정 완료 ---
                
                if cycle_to_finalize:
                    # [V5.5 BUG FIX]
                    # Mode Switch로 닫히는 사이클(Cycle 8)은,
                    # 'final_equity_for_log'에 저장된 'BUY 실행 전' 자산을 사용합니다.
                    # 일반 종료(Close Signal) 사이클은 이 속성이 없으므로,
                    # 'CLOSE 실행 후' 자산인 'current_equity_after_trade'를 사용합니다.
                    final_equity_for_this_cycle = getattr(
                        cycle_to_finalize, 
                        'final_equity_for_log', # Mode Switch 시 저장된 값
                        current_equity_after_trade # 일반 Close 시 사용되는 값
                    )

                    self._finalize_and_store_cycle(
                        cycle_to_finalize, 
                        current_time, 
                        current_price,
                        final_equity_for_this_cycle # [V5.5] 분리된 자산 사용
                    )
                    
                    if self.active_cycle == cycle_to_finalize:
                        self.active_cycle = None
                
                self.update_equity_curve(current_price)
                
            except Exception as e:
                print(f"   [Engine] ❌ Error in backtest loop at {current_row.get('timestamp', 'N/A')}: {e}")
                continue
        
        print("   [Engine] Finalizing backtest...")
        self._finalize_backtest(df.iloc[-1]['timestamp'], df.iloc[-1]['close'])
        
        metrics = self._calculate_performance_metrics()
        
        return self.trade_history, metrics

    def _execute_signal_with_cycle(self, signal: Dict, current_row: pd.Series, current_time: datetime, current_data: pd.DataFrame, current_equity_before_trade: float) -> Optional[TradingCycle]:
        """
        [V5.5] PnL $+16,177 버그 수정
        - Mode Switch 시, 닫힐 사이클(Cycle 8)에 'BUY 실행 전' 자산을 저장합니다.
        """
        action = signal.get('action')
        trade_mode = signal.get('trade_mode', 'unknown')
        current_price = current_row['close']
        
        old_cycle_to_close = None

        if action == 'buy':
            cycle_start_condition = not self.active_cycle or self.active_cycle.mode != trade_mode
            
            if cycle_start_condition:
                if self.active_cycle: # [V5.5] Mode Switch 감지
                    old_cycle_to_close = self.active_cycle # 닫힐 Cycle 8 저장
                    old_cycle_to_close.close_reason_for_log = 'Mode Switch'
                    
                    # [V5.5 BUG FIX]
                    # Cycle 9의 'BUY'가 실행되기 *전*의 자산(current_equity_before_trade)을
                    # 닫힐 Cycle 8의 '최종 자산'으로 임시 저장합니다.
                    old_cycle_to_close.final_equity_for_log = current_equity_before_trade
                
                self.cycle_counter += 1
                self.active_cycle = TradingCycle(self.cycle_counter, current_time, current_equity_before_trade, trade_mode)
            
            # 'BUY' 실행 (Cycle 9의 'BUY'가 여기서 실행됨)
            success = self._execute_buy(signal, current_price, current_time, trade_mode)
            
            if success and self.active_cycle and self.positions:
                latest_position = self.positions[-1]
                if latest_position.get('trade_mode') == self.active_cycle.mode:
                    self.active_cycle.add_position(latest_position)
                    
        elif action == 'close':
            self._execute_close(signal, current_row, current_time, trade_mode)
            
            mode_positions_after = [p for p in self.positions if p.get('trade_mode') == trade_mode]
            cycle_end_condition = self.active_cycle and self.active_cycle.mode == trade_mode and not mode_positions_after
            
            if cycle_end_condition:
                old_cycle_to_close = self.active_cycle
                old_cycle_to_close.close_reason_for_log = signal.get('reason', 'Close Signal')
                # 'final_equity_for_log'는 저장하지 않습니다.
                # 메인 루프가 'CLOSE 실행 후'의 'current_equity_after_trade'를 사용합니다.
        
        return old_cycle_to_close

    def _execute_buy(self, signal: Dict, current_price: float, current_time: datetime, trade_mode: str) -> bool:
        """[V4.5.3] 매수 실행 로직 (수정 없음)"""
        try:
            size_pct = signal.get('size_pct', 0.1)
            min_size_pct = 0.005 # 최소 0.5%
            size_pct = max(size_pct, min_size_pct)
            
            current_equity = self.calculate_total_equity(current_price)
            investment_amount = current_equity * size_pct * self.max_leverage
            
            if len(self.positions) >= self.max_open_entries:
                return False

            quantity = investment_amount / current_price
            commission_cost = investment_amount * self.commission
            total_cost = investment_amount + commission_cost
            
            margin_required = investment_amount / self.max_leverage
            
            if margin_required > self.current_balance:
                print(f"   [Engine] ❌ Insufficient balance for margin: {margin_required:.2f} > {self.current_balance:.2f}")
                return False
                
            position = {
                'entry_time': current_time, 'entry_price': current_price,
                'quantity': quantity, 'trade_mode': trade_mode,
                'position_size': investment_amount,
                'size_pct': size_pct, 'commission': commission_cost,
                'margin_used': margin_required
            }
            self.positions.append(position)
            
            self.current_balance -= (margin_required + commission_cost)
            
            return True
        except Exception as e:
            print(f"   [Engine] ❌ Buy execution failed: {e}")
            return False

    def _execute_close(self, signal: Dict, current_row: pd.Series, current_time: datetime, trade_mode: str):
        """[V4.5.3] 매도 실행 로직 (수정 없음)"""
        try:
            current_price = current_row['close']
            close_percent = signal.get('percent', 1.0)
            reason = signal.get('reason', 'unknown')
            
            mode_positions = [p for p in self.positions if p.get('trade_mode') == trade_mode]
            if not mode_positions: return
                
            total_quantity = sum(p['quantity'] for p in mode_positions)
            total_investment = sum(p['position_size'] for p in mode_positions)
            total_margin_used = sum(p['margin_used'] for p in mode_positions)
            avg_entry_price = sum(p['entry_price'] * p['quantity'] for p in mode_positions) / total_quantity
            
            close_quantity = total_quantity * close_percent
            close_investment = total_investment * close_percent
            close_margin = total_margin_used * close_percent
            
            close_value = current_price * close_quantity
            commission_cost = close_value * self.commission
            net_proceeds = close_value - commission_cost
            
            pnl_amount = (current_price - avg_entry_price) * close_quantity
            net_pnl = pnl_amount - (commission_cost + sum(p['commission'] for p in mode_positions) * close_percent)
            
            self.current_balance += (close_margin + net_pnl)
            
            trade_record = {
                'entry_time': mode_positions[0]['entry_time'], 'exit_time': current_time,
                'entry_price': avg_entry_price, 'exit_price': current_price,
                'quantity': close_quantity, 'pnl': net_pnl,
                'pnl_pct': net_pnl / close_margin if close_margin > 0 else 0,
                'trade_mode': trade_mode, 'reason': reason,
                'commission': commission_cost, 'total_investment': close_investment,
            }
            self.trade_history.append(trade_record)
            
            if close_percent >= 0.999:
                self.positions = [p for p in self.positions if p.get('trade_mode') != trade_mode]
            else:
                remaining_ratio = 1.0 - close_percent
                for p in self.positions:
                    if p.get('trade_mode') == trade_mode:
                        p['quantity'] *= remaining_ratio
                        p['position_size'] *= remaining_ratio
                        p['margin_used'] *= remaining_ratio
                        p['commission'] *= remaining_ratio
                
        except Exception as e:
            print(f"   [Engine] ❌ Close execution failed: {e}")

    def _finalize_backtest(self, last_time: datetime, last_price: float):
        """[V5.1] 최종 백테스트 종료 로직"""
        if self.positions:
            print("   [Engine] Closing all open positions at backtest end...")
            for position in self.positions[:]:
                close_signal = {'action': 'close', 'percent': 1.0, 'reason': 'Backtest end close', 'trade_mode': position['trade_mode']}
                self._execute_close(
                    close_signal,
                    pd.Series({'close': last_price, 'timestamp': last_time}),
                    last_time,
                    position['trade_mode']
                )
        
        # [V5.1] 활성 사이클이 남아있으면 최종 처리
        if self.active_cycle:
            final_equity = self.calculate_total_equity(last_price)
            self.active_cycle.close_reason_for_log = 'Backtest end'
            self._finalize_and_store_cycle(
                self.active_cycle, 
                last_time, 
                last_price, 
                final_equity
            )
            self.active_cycle = None

    def _finalize_and_store_cycle(self, cycle_obj: TradingCycle, end_time: datetime, final_price: float, final_equity: float):
        """
        [V5.1] (신규) _close_active_cycle을 대체합니다.
        전달받은 사이클 객체를 최종 처리하고 저장합니다.
        """
        if not cycle_obj: return
        try:
            # _execute_signal_with_cycle에서 임시 저장한 종료 사유
            reason = getattr(cycle_obj, 'close_reason_for_log', 'Unknown')
            
            # [V5.1] 메인 루프에서 계산된 최종 자산으로 사이클 종료
            cycle_obj.close_cycle(end_time, final_equity, final_price)
            self.trading_cycles.append(cycle_obj)
            
            summary = cycle_obj.get_summary()
            
            # [V5.1] PnL도 전달받은 final_equity 기준으로 계산
            pnl_amount = final_equity - cycle_obj.entry_balance
            
            print(f"   [Engine] ✅ Cycle {summary['cycle_id']} ({summary['mode']}) ended by {reason}. "
                  f"Return: {summary['return_pct']:.2f}%, "
                  f"PnL: ${pnl_amount:+.2f} USDT, "
                  # [V5.2] 이제 이 MDD가 0.00%가 아닌 정확한 값을 출력해야 합니다.
                  f"MDD: {summary['max_drawdown']:.2f}%") 
            
        except Exception as e:
            print(f"   [Engine] ❌ Error finalizing cycle {cycle_obj.cycle_id}: {e}")

    def _calculate_performance_metrics(self) -> Dict:
        """[V4.5.3] 성과 계산 (수정 없음)"""
        try:
            metrics_calculator = PerformanceMetrics(
                self.trade_history, 
                self.equity_curve, 
                self.initial_balance
            )
            metrics = metrics_calculator.calculate_all_metrics()
            
            metrics['initial_balance'] = self.initial_balance
            metrics['final_equity'] = self.total_equity
            metrics['final_cash'] = self.current_balance
            
            return metrics
        except Exception as e:
            print(f"❌ Performance calculation error: {e}")
            return {}

    def _extract_strategy_name(self, strategy):
        if hasattr(strategy, 'name') and strategy.name:
            self.strategy_name = strategy.name
        else: self.strategy_name = strategy.__class__.__name__

    def _calculate_actual_backtest_period(self, df, start_date, end_date):
        try:
            actual_start = df['timestamp'].min()
            actual_end = df['timestamp'].max()
            self.actual_backtest_period = f"{actual_start.strftime('%Y-%m-%d')} to {actual_end.strftime('%Y-%m-%d')}"
        except Exception: self.actual_backtest_period = f"{start_date} to {end_date}"
        
    def _get_config_dict(self) -> Dict:
        return {
            'initial_balance': self.initial_balance,
            'commission': self.commission,
            'slippage': self.slippage,
            'risk_per_trade_total': self.risk_per_trade_total,
            'max_leverage': self.max_leverage,
            'max_open_entries': self.max_open_entries,
            'language': self.language
        }