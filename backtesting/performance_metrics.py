import pandas as pd
import numpy as np
from scipy import stats
from typing import List, Dict
import warnings
warnings.filterwarnings('ignore')

class PerformanceMetrics:
    """
    V4.5.2 Performance Metrics Calculator
    (V4.5.2 원본 코드)
    """
  
    def __init__(self, trades: List[Dict], equity_curve: List[float], initial_balance: float):
        self.trades = trades
        self.equity_curve = equity_curve
        self.initial_balance = initial_balance
        self.final_balance = equity_curve[-1] if len(equity_curve) > 0 else initial_balance
      
    def calculate_all_metrics(self) -> Dict:
        """Calculate all performance metrics"""
        try:
            if not self.trades:
                return self._get_empty_metrics()
            
            # 기본 통계 계산
            total_trades = len(self.trades)
            winning_trades = [t for t in self.trades if t.get('pnl', 0) > 0]
            losing_trades = [t for t in self.trades if t.get('pnl', 0) < 0]
            
            # 총 수익률 계산 (자산 곡선 기반)
            total_return = (self.final_balance - self.initial_balance) / self.initial_balance
            
            win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
            
            max_drawdown = self.calculate_max_drawdown()
            sharpe_ratio = self.calculate_sharpe_ratio()
            
            gross_profit = sum(t.get('pnl', 0) for t in winning_trades)
            gross_loss = abs(sum(t.get('pnl', 0) for t in losing_trades))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            
            total_pnl = sum(t.get('pnl', 0) for t in self.trades)
            avg_trade = total_pnl / total_trades if total_trades > 0 else 0
            avg_winning_trade = sum(t.get('pnl', 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_losing_trade = sum(t.get('pnl', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            largest_winning_trade = max((t.get('pnl', 0) for t in winning_trades), default=0)
            largest_losing_trade = min((t.get('pnl', 0) for t in losing_trades), default=0)
            
            # 연율화 수익률
            annual_return = 0
            if self.trades:
                try:
                    entry_times = [pd.to_datetime(t.get('entry_time')) for t in self.trades if t.get('entry_time')]
                    exit_times = [pd.to_datetime(t.get('exit_time')) for t in self.trades if t.get('exit_time')]
                    
                    if entry_times and exit_times:
                        start_date = min(entry_times)
                        end_date = max(exit_times)
                        days = (end_date - start_date).days
                        if days > 0:
                            annual_return = ((1 + total_return) ** (365 / days)) - 1
                        else:
                            annual_return = total_return * 365
                    else: annual_return = total_return * 6
                except: annual_return = total_return * 6
            
            metrics = {
                'total_return': total_return,
                'annual_return': annual_return,
                'win_rate': win_rate,
                'max_drawdown': max_drawdown,
                'sharpe_ratio': sharpe_ratio,
                'profit_factor': profit_factor,
                'total_trades': total_trades,
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'avg_trade': avg_trade,
                'avg_winning_trade': avg_winning_trade,
                'avg_losing_trade': avg_losing_trade,
                'largest_winning_trade': largest_winning_trade,
                'largest_losing_trade': largest_losing_trade
            }
            
            return metrics
            
        except Exception as e:
            print(f"❌ Performance metrics calculation error: {e}")
            return self._get_empty_metrics()
    
    def calculate_max_drawdown(self):
        """Calculate maximum drawdown"""
        if len(self.equity_curve) < 2: return 0
        peak = self.equity_curve[0]
        max_dd = 0
        for equity in self.equity_curve:
            if equity > peak: peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            if dd > max_dd: max_dd = dd
        return max_dd
    
    def calculate_sharpe_ratio(self, risk_free_rate=0.02):
        """Calculate Sharpe ratio"""
        if len(self.equity_curve) < 2: return 0
        
        returns = []
        for i in range(1, len(self.equity_curve)):
            if self.equity_curve[i-1] > 0:
                ret = (self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
                returns.append(ret)
        
        if not returns: return 0
        
        excess_returns = [r - risk_free_rate/365 for r in returns]
        avg_excess_return = np.mean(excess_returns)
        std_dev = np.std(excess_returns)
        
        if std_dev == 0: return 0
        
        return avg_excess_return / std_dev * (365 ** 0.5)
    
    def _get_empty_metrics(self) -> Dict:
        """Return empty metrics when calculation fails"""
        return {
            'total_return': 0, 'annual_return': 0, 'win_rate': 0,
            'max_drawdown': 0, 'sharpe_ratio': 0, 'profit_factor': 0,
            'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
            'avg_trade': 0, 'avg_winning_trade': 0, 'avg_losing_trade': 0,
            'largest_winning_trade': 0, 'largest_losing_trade': 0
        }
