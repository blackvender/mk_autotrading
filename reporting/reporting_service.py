import pandas as pd
import numpy as np
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reporting.report_models import BacktestResult, TradingCycle
from utils.data_converter import DataConverter # [V4.6] Resample 함수 사용

# [V4.6] mplfinance는 이제 리포팅 모듈만 의존합니다.
try:
    import mplfinance as mpf
    MPLFINANCE_AVAILABLE = True
except ImportError:
    MPLFINANCE_AVAILABLE = False
    print("⚠️ mplfinance not found. Chart generation will be skipped.")
    print("Please install: pip install mplfinance")

class ReportingService:
    """
    [V5.9] Pandas '.date' attribute 오류 해결
    [V5.8] Pandas 'Grouper' 및 'first()' 오류 근본적 해결
    """
    def __init__(self, language: str = 'en'):
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.base_dir = os.path.abspath(f'./backtest_results/session_{self.session_id}')
        self.charts_dir = os.path.join(self.base_dir, 'cycle_charts')
        os.makedirs(self.charts_dir, exist_ok=True)
        
        self.language = language
        self.cycle_charts: List[Dict[str, Any]] = [] # 생성된 차트 정보
        self.report_data: Dict[str, Any] = {}
        self.config: Dict[str, Any] = {} 
        
        # [V4.11] V4.5.3 레이아웃 복원을 위한 번역어 추가
        self.LANGUAGE_MAP = {
            'ko': {
                'Backtest Report': '백테스트 리포트', 'Strategy': '전략', 'Period': '기간',
                'Generated Time': '생성 시간', 'Key Performance Metrics': '주요 성과 지표',
                'Final Balance': '최종 잔고', 'Total Return': '총 수익률',
                'Annual Return': '연간 수익률', 'Win Rate': '승률',
                'Max Drawdown': '최대 낙폭', 'Sharpe Ratio': '샤프 지수',
                'Mode Performance Analysis': '모드별 성과 분석',
                'Momentum Trading': '모멘텀 트레이딩', 'Reversal Trading': '되돌림 트레이딩',
                'Trades': '거래', 'Detailed Performance Metrics': '상세 성과 지표',
                'Profit Factor': '수익 팩터', 'Average Trade': '평균 거래',
                'Average Winning Trade': '평균 수익 거래', 'Average Losing Trade': '평균 손실 거래',
                'Largest Winning Trade': '최대 수익 거래', 'Largest Losing Trade': '최대 손실 거래',
                'Recent Trade History (Last 20)': '최근 거래 내역 (최근 20건)',
                'Entry Time': '진입 시간', 'Exit Time': '청산 시간',
                'Entry Price': '진입 가격', 'Exit Price': '청산 가격', 'Mode': '모드', 'Reason': '사유',
                'Overall Backtest Performance': '전체 백테스트 성과',
                'Market Regime Color Coding': '시장 레짐 색상 코딩',
                'Bull Regime': '상승 레짐', 'Bear Regime': '하락 레짐', 'Sideways Regime': '횡보 레짐',
                'Volatile Regime': '고변동성 레짐', 'Stable Regime': '안정 레짐',
                'Complete Trading Cycle Analysis': '전체 트레이딩 사이클 분석',
                'Cycle Performance Summary': '사이클 성과 요약',
                'Cycle #': '사이클 #', 'Duration': '기간(h)', 'Entries': '진입',
                'Net Position': '순포지션', 'Max Position': '최대 포지션', 'Leverage': '레버리지',
                'Return': '수익률', 'Max DD': '최대 DD', 'DD Duration': 'DD 기간(h)', 'Recovery': '회복',
                'Performance by Market Regime': '시장 레짐별 성과',
                'Cycles': '사이클', 'Avg Return': '평균 수익률',
                'Position Details': '포지션 상세', 'Type': '유형', 'Price': '가격', 'Size': '크기',
                'Chart Explanation': '차트 해설', 'Yellow Highlighted Area': '노란색 하이라이트 영역',
                'Green Triangle (▲)': '녹색 삼각형 (▲)', 'Red Triangle (▼)': '빨간색 삼각형 (▼)',
                '5-minute Candlesticks': '5분봉 캔들스틱',
                'Risk Analysis': '리스크 분석', 'DD Amount': '손실폭', 'Recovery Status': '회복 상태',
                'Market Regime': '시장 레짐',
                
                # [V4.11] PnL, 평단가, 총 투자금 번역
                'Maximum Drawdown Analysis': '최대 낙폭 상세 분석',
                'Peak Equity': '최고 자산 (진입 시점)', # [V4.11] MDD 기준점 명시
                'Trough Equity': '최저 자산',
                'Peak Time': '최고점 시간',
                'Trough Time': '최저점 시간',
                'Cycle Period': '사이클 기간',
                'Position Summary': '포지션 요약',
                'Performance': '성과',
                'Avg. Entry Price': '평균 진입가',
                'Total Entries': '총 진입',
                'Total Investment': '총 투자금',
                'PnL': '순손익',
                'Net Position Size': '순 포지션',
                'Max Open Position': '최대 오픈 포지션',
                'Cycle Performance Statistics': '사이클 성과 통계',
                'Average Cycle Return': '평균 사이클 손익', # [V4.10] PnL($) 기준으로 변경됨
                'Average Max DD': '평균 최대 DD',
                'Profitability Rate': '수익 사이클 비율',
                'Worst DD': '최악의 DD',

                'unknown': '알수없음', 'momentum': '모멘텀', 'reversal': '되돌림',
                'RSI_Simple': '단순 RSI', 'DCA_RSI': 'DCA RSI',
                '상승_강세': '상승_강세', '상승_약세': '상승_약세', '상승_횡보': '상승_횡보',
                '하락_강세': '하락_강세', '하락_약세': '하락_약세', '하락_횡보': '하락_횡보',
                
                # [v2.0] 8대 레짐 라벨 번역어
                'Uptrend-Impulse': '상승-임펄스',
                'Uptrend-Normal': '상승-일반',
                'Uptrend-Consolidation': '상승-조정',
                'Downtrend-Impulse': '하락-임펄스',
                'Downtrend-Normal': '하락-일반',
                'Downtrend-Consolidation': '하락-조정',
                'Full-Consolidation': '완전횡보',
                'Transition': '전환기',
                
                'Unknown': '알수없음',
                # [V4.11] 동적 번역어 추가
                'Recovered in': '회복(h)', 'Not recovered': '미회복', 'Active': '진행중',
                'No drawdown data': 'DD 데이터 없음', 'Data unavailable': '데이터 없음',
            }
        }
        
        print(f"📁 ReportingService initialized. Session folder: {self.base_dir}")

    def _t(self, text: str) -> str:
        """[V4.11] 텍스트 번역 (회복 메시지 추가)"""
        if self.language == 'ko':
            # "Recovered in 12.3h" 같은 동적 문자열 번역
            if isinstance(text, str) and text.startswith('Recovered in'):
                try:
                    hours = text.split(' ')[2]
                    return f"회복 ({hours})"
                except:
                    pass # 아래에서 기본 번역 처리
            
            if text in self.LANGUAGE_MAP.get('ko', {}):
                 return self.LANGUAGE_MAP.get('ko', {}).get(text, text)
            return text
        
        # 영어일 경우, 'momentum' -> 'Momentum'
        if text in ['momentum', 'reversal', 'unknown', 'RSI_Simple', 'DCA_RSI']:
            return text.replace('_', ' ').title()
            
        return text

    def generate_report(self, result: BacktestResult):
        """
        [V4.6] 백테스트 결과를 받아 모든 리포트 파일(HTML, 차트, 요약)을 생성합니다.
        """
        try:
            self.config = result.config
            
            self.report_data = {
                'strategy_name': result.strategy_name,
                'backtest_period': result.backtest_period,
                'total_trades': len(result.trades),
                'final_balance': result.metrics.get('final_equity', 0),
                'initial_balance': result.metrics.get('initial_balance', 0),
                'total_return': result.metrics.get('total_return', 0),
                'annual_return': result.metrics.get('annual_return', 0),
                'win_rate': result.metrics.get('win_rate', 0),
                'max_drawdown': result.metrics.get('max_drawdown', 0),
                'sharpe_ratio': result.metrics.get('sharpe_ratio', 0),
                'profit_factor': result.metrics.get('profit_factor', 0),
                'cycle_count': len(result.trading_cycles),
                'generation_time': datetime.now().strftime('%Y%m%d_%H%M%S'),
                'session_directory': self.base_dir,
                'max_leverage': result.config.get('max_leverage', 8)
            }
            
            self._generate_trading_cycle_charts(
                result.trading_cycles, 
                result.featured_dataframe, 
                result.regime_data
            )
            
            self._create_overall_backtest_chart(
                result.featured_dataframe, 
                result.trades
            )

            html_filepath = self._generate_html_report_internal(
                result.metrics, 
                result.trades
            )
            
            self._create_session_summary(result.config)
            self._create_session_info(result)
            
            print(f"🎉 Report generation complete: {html_filepath}")

        except Exception as e:
            print(f"❌ Report generation failed: {e}")
            import traceback
            traceback.print_exc()

    def _generate_html_report_internal(self, metrics: Dict, trades: List[Dict]) -> str:
        """[V4.6] HTML 리포트 생성 로직 (V4.5.3에서 이동)"""
        
        mode_stats = self._calculate_mode_stats(trades)
        
        cycle_charts_section = self._create_cycle_charts_section()
        
        overall_chart_section = ""
        overall_chart_path = os.path.join(self.base_dir, 'overall_backtest_chart.png')
        if os.path.exists(overall_chart_path):
            overall_chart_section = f"""
            <div class="section">
                <h2>📈 {self._t('Overall Backtest Performance')}</h2>
                <img src="overall_backtest_chart.png" alt="Overall Backtest Chart"
                     style="width: 100%; border: 1px solid #ccc; border-radius: 5px;"
                     onclick="toggleZoom(this)">
            </div>
            """
        
        # [V4.9] V4.5.3 레이아웃 복원
        regime_explanation_html = self._create_regime_explanation_html()
        
        html_content = self._create_html_content(
            metrics, mode_stats, trades, 
            overall_chart_section, 
            regime_explanation_html, # [V4.9] 레짐 설명 추가
            cycle_charts_section
        )
        
        filename = os.path.join(self.base_dir, f"backtest_report_{self.session_id}.html")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return filename
        
    # [V4.9] V4.5.3의 레짐 설명 섹션 헬퍼
    def _create_regime_explanation_html(self) -> str:
        """[v2.0 수정] v2.0 8대 레짐 라벨을 표시하도록 수정"""
        return f"""
        <div class="section">
            <h2>🎨 {self._t('Market Regime Color Coding')} (v2.0)</h2>
            <div class="info-grid">
                <div class="info-card" style="border-left-color: #28a745; background: #f0fff4;">
                    <strong>🟢 {self._t('Uptrend-Impulse')} / {self._t('Uptrend-Normal')}</strong><br>
                    <span>{self._t('상승-임펄스')} / {self._t('상승-일반')} / {self._t('상승-조정')}</span>
                </div>
                <div class="info-card" style="border-left-color: #dc3545; background: #fff0f1;">
                    <strong>🔴 {self._t('Downtrend-Impulse')} / {self._t('Downtrend-Normal')}</strong><br>
                    <span>{self._t('하락-임펄스')} / {self._t('하락-일반')} / {self._t('하락-조정')}</span>
                </div>
                <div class="info-card" style="border-left-color: #ffc107; background: #fffaf0;">
                    <strong>🟡 {self._t('Full-Consolidation')} / {self._t('Transition')}</strong><br>
                    <span>{self._t('완전횡보')} / {self._t('전환기')}</span>
                </div>
                <div class="info-card" style="border-left-color: #6c757d; background: #f8f9fa;">
                    <strong>⚪ {self._t('Unknown')}</strong><br>
                    <span>{self._t('Market Regime')} {self._t('unknown')}</span>
                </div>
            </div>
        </div>
        """

    def _generate_trading_cycle_charts(self, trading_cycles: List[TradingCycle], 
                                     df: pd.DataFrame, df_regime: Optional[pd.DataFrame]):
        """[V4.6] 모든 사이클 차트 생성 (V4.5.3에서 이동, df_24h -> df_regime)"""
        if not MPLFINANCE_AVAILABLE:
            print("⚠️ mplfinance not found. Skipping chart generation.")
            return

        print(f"📈 Generating TradingCycle charts: {len(trading_cycles)} cycles")
        
        successful_charts = 0
        for i, cycle_obj in enumerate(trading_cycles):
            try:
                cycle_data = cycle_obj.get_chart_cycle_data()
                position_details = cycle_obj.get_position_details_for_chart()
                
                if not cycle_data:
                    print(f"⚠️ Cycle #{i+1} has no chart data")
                    continue
                
                success, _ = self._create_detailed_cycle_chart(
                    cycle_data, i, df, df_regime,
                    self.base_dir, self.charts_dir
                )
                
                if success:
                    chart_info = self._create_chart_info_from_trading_cycle(
                        cycle_obj, i, self.charts_dir, position_details, df_regime
                    )
                    self.cycle_charts.append(chart_info)
                    successful_charts += 1
                else:
                    print(f"⚠️ TradingCycle #{i+1} chart creation failed")
                    
            except Exception as e:
                print(f"❌ TradingCycle #{i+1} chart creation error: {e}")
                continue
        
        print(f"🎉 Total {successful_charts} TradingCycle charts created")

    def _create_detailed_cycle_chart(self, cycle_data: List[Dict], cycle_num: int, df: pd.DataFrame, 
                                   df_regime: Optional[pd.DataFrame], base_dir: str, charts_dir: str):
        """[V4.6] 개별 사이클 차트 생성 (V4.5.3에서 이동, df_24h -> df_regime)"""
        try:
            cycle_start = cycle_data[0]['timestamp']
            cycle_end = cycle_data[-1]['timestamp']
            
            # [V5.2] Mode Switch 시 cycle_data[0]에 신호가 없을 수 있음.
            # cycle_obj에서 직접 모드를 가져오는 것이 더 안전하나, 여기서는 편의상
            # position_details에서 첫 번째 'buy' 신호의 모드를 찾습니다.
            cycle_mode = 'Unknown'
            pos_details_for_mode = [d for d in cycle_data if d.get('signals') for s in d['signals'] if s.get('action') == 'buy']
            if pos_details_for_mode:
                cycle_mode = pos_details_for_mode[0]['signals'][0].get('trade_mode', 'Unknown')

            regime_info = self._get_cycle_regime_info(cycle_start, cycle_end, df_regime)
            regime_color = regime_info['color']
            
            regime_text_for_title = self._t(regime_info['regime'])
            chart_title = (f'Cycle #{cycle_num + 1} - 5min Candlestick | Mode: {self._t(cycle_mode)} | Regime: {regime_text_for_title}\n'
                           f'{cycle_start.strftime("%Y-%m-%d %H:%M")} to {cycle_end.strftime("%Y-%m-%d %H:%M")}')

            data_start = cycle_start - timedelta(hours=2)
            data_end = cycle_end + timedelta(hours=2)
            chart_data = df[(df['timestamp'] >= data_start) & (df['timestamp'] <= data_end)].copy()
            if len(chart_data) < 5:
                chart_data = df[(df['timestamp'] >= cycle_start) & (df['timestamp'] <= cycle_end)].copy()
                if len(chart_data) < 5: return False, []
            
            df_plot = chart_data.set_index('timestamp').copy()
            
            buy_signals = pd.Series(index=df_plot.index, dtype=float)
            close_signals = pd.Series(index=df_plot.index, dtype=float)
            position_details = []
            
            # [V5.2] (버그 #1 수정 확인)
            # engine.py가 수정되어 cycle_data에 'close' 신호가 포함되므로
            # 이 코드는 이제 'SELL' 신호도 올바르게 처리합니다.
            for data_point in cycle_data:
                timestamp = data_point['timestamp']
                if data_point['signals']:
                    for signal in data_point['signals']:
                        action = signal.get('action')
                        detail = {
                            'time': timestamp, 'price': data_point['price'],
                            'size': signal.get('size_pct', signal.get('percent', 0)),
                            'mode': signal.get('trade_mode', 'unknown'),
                            'reason': signal.get('reason', '')
                        }
                        if action == 'buy':
                            if timestamp in buy_signals.index: buy_signals[timestamp] = data_point['price']
                            detail.update({'type': 'BUY', 'action': 'entry'})
                            position_details.append(detail)
                        elif action == 'close':
                            if timestamp in close_signals.index: close_signals[timestamp] = data_point['price']
                            detail.update({'type': 'SELL', 'action': 'exit'})
                            position_details.append(detail)

            apds = []
            if buy_signals.notna().any():
                apds.append(mpf.make_addplot(buy_signals, type='scatter', markersize=100, marker='^', color='green'))
            if close_signals.notna().any():
                apds.append(mpf.make_addplot(close_signals, type='scatter', markersize=100, marker='v', color='red'))
            
            fig, axes = mpf.plot(
                df_plot, type='candle', style='charles',
                addplot=apds, volume=False, figsize=(20, 10),
                returnfig=True, show_nontrading=True,
                datetime_format='%m/%d %H:%M',
                title=chart_title,
                xlim=(df_plot.index[0], df_plot.index[-1])
            )
            
            ax1 = axes[0]
            start_mpl = mdates.date2num(cycle_start)
            end_mpl = mdates.date2num(cycle_end)
            ax1.axvspan(start_mpl, end_mpl, alpha=0.15, color=regime_color)
            
            plt.tight_layout()
            filename = f'cycle_{cycle_num + 1}_candlestick.png'
            filepath = os.path.join(charts_dir, filename)
            
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig) 
            
            return True, position_details
            
        except Exception as e:
            print(f"❌ Detailed chart creation failed (Cycle {cycle_num+1}): {e}")
            if 'fig' in locals(): plt.close(fig)
            return False, []

    # --- [FIX V5.8] 'Grouper' 오류 근본 해결 ---
    def _get_cycle_regime_info(self, cycle_start, cycle_end, df_regime):
        """
        [V5.8] 'Grouper' 오류 근본 해결:
        Pandas `resample()`을 사용하지 않고,
        5분봉 `df_regime`을 사이클 기간으로 직접 필터링하여
        최빈값(dominant regime)을 찾습니다.
        """
        try:
            regime_info = {'regime': 'Unknown', 'text': f"{self._t('Mode')}: {self._t('unknown')}", 'color': 'gray'}
            
            regime_col = 'regime_1d' 
            if df_regime is None or df_regime.empty or regime_col not in df_regime.columns:
                return regime_info

            # [FIX V5.8] 1. `resample` 대신 5분봉 타임스탬프로 직접 필터링
            cycle_regime_data = df_regime[
                (df_regime['timestamp'] >= cycle_start) &
                (df_regime['timestamp'] <= cycle_end)
            ]
            
            if cycle_regime_data.empty:
                return regime_info

            # [FIX V5.8] 2. 필터링된 5분봉 데이터에서 최빈값(regime_1d) 찾기
            regime_series = cycle_regime_data[regime_col].dropna()
            if regime_series.empty:
                return regime_info
            
            regime_counts = regime_series.value_counts()
            dominant_regime = regime_counts.index[0]
            
            # [FIX V5.8] 3. 백분율도 5분봉 캔들 수 기준으로 계산
            regime_percentage = (regime_counts.iloc[0] / len(regime_series)) * 100
                
            # [v2.0 수정] 8대 레짐 색상
            regime_colors = {
                'Uptrend-Impulse': '#28a745', 'Uptrend-Normal': '#20c997', 'Uptrend-Consolidation': '#17a2b8',
                'Downtrend-Impulse': '#dc3545', 'Downtrend-Normal': '#fd7e14', 'Downtrend-Consolidation': '#ffc107',
                'Full-Consolidation': '#ffc107', 'Transition': '#6f42c1',
                'Unknown': '#6c757d'
            }
            
            # [V4.9] V4.5.3 스타일 텍스트
            regime_text = f"Regime: {dominant_regime} ({regime_percentage:.1f}%)"
            if len(regime_counts) > 1:
                 regime_text = f"Mixed Regime: {dominant_regime} ({regime_percentage:.1f}%)"

            
            regime_info = {
                'regime': dominant_regime,
                'text': regime_text, 
                'color': regime_colors.get(dominant_regime, '#6c757d')
            }
        except Exception as e:
            # [V5.2] 더 구체적인 오류 로그
            print(f"   ⚠️ Error in regime analysis (cycle {cycle_start}): {e}")
        return regime_info
    # --- [FIX V5.8] 수정 완료 ---

    def _create_chart_info_from_trading_cycle(self, cycle_obj: TradingCycle, cycle_num: int, charts_dir: str, 
                                            position_details: List, df_regime: Optional[pd.DataFrame]):
        """[V4.11 수정] TradingCycle에서 차트 정보 생성 (PnL, 평단가, 총 투자금 추가)"""
        
        regime_info = self._get_cycle_regime_info(
            cycle_obj.start_time,
            getattr(cycle_obj, 'end_time', cycle_obj.start_time),
            df_regime
        )
        mdd_analysis = cycle_obj.get_mdd_analysis()
        cycle_summary = cycle_obj.get_summary()
        
        # [V4.I'll] get_summary()에서 계산된 정확한 값 사용
        total_return_pct = cycle_summary.get('return_pct', 0)
        cycle_pnl = cycle_summary.get('cycle_pnl', 0)
        avg_price = cycle_summary.get('avg_entry_price', 0)
        total_investment = cycle_summary.get('total_invested', 0)
        
        # 포지션 통계
        net_position_size = 0
        max_open_position = 0
        current_pos = 0
        for pos in sorted(position_details, key=lambda x: x['time']):
            if pos['action'] == 'entry': current_pos += pos['size']
            elif pos['action'] == 'exit': current_pos *= (1 - pos['size']) # [V4.10] 부분청산 로직 수정
            max_open_position = max(max_open_position, current_pos)
        
        # [V4.10] 사이클 종료 시 순포지션은 0
        if not cycle_obj.is_active:
            net_position_size = 0
        else:
            net_position_size = current_pos


        chart_info = {
            'filepath': os.path.join(charts_dir, f'cycle_{cycle_num + 1}_candlestick.png'),
            'filename': f'cycle_{cycle_num + 1}_candlestick.png',
            'relative_path': f'cycle_charts/cycle_{cycle_num + 1}_candlestick.png',
            'cycle_num': cycle_num + 1,
            'start_time': cycle_obj.start_time,
            'end_time': getattr(cycle_obj, 'end_time', cycle_obj.start_time),
            'position_count': len([p for p in position_details if p['action'] == 'entry']),
            
            # [V4.11 수정]
            'total_investment': total_investment, # 총 투자금 (USDT)
            'avg_price': avg_price,               # 평단가 (USDT)
            'total_return_pct': total_return_pct, # 수익률 (%)
            'cycle_pnl': cycle_pnl,               # 순손익 (USDT)
            
            'net_position_size': net_position_size, # 순포지션 (%)
            'max_open_position': max_open_position, # 최대포지션 (%)
            'actual_leverage': max_open_position * self.report_data.get('max_leverage', self.config.get('max_leverage', 8)),
            'position_details': position_details,
            'regime': regime_info['regime'],
            
            # [V5.2] (버그 #2 수정 확인)
            # engine.py 수정으로 MDD 데이터가 올바르게 흘러 들어옴
            'max_drawdown_pct': mdd_analysis['max_drawdown_pct'],
            'max_drawdown_amount': mdd_analysis['max_drawdown_amount'],
            'peak_equity': mdd_analysis['peak_equity'],
            'trough_equity': mdd_analysis['trough_equity'],
            'peak_time': mdd_analysis['peak_time'],
            'trough_time': mdd_analysis['trough_time'],
            'recovery_info': mdd_analysis['recovery_info'],
            'drawdown_duration_hours': mdd_analysis['drawdown_duration_hours'],
            
            'cycle_summary': cycle_summary,
        }
        return chart_info 

    def _create_overall_backtest_chart(self, df: pd.DataFrame, trades: List[Dict]):
        """[V5.9] '.date' attribute 오류 근본 해결"""
        if not MPLFINANCE_AVAILABLE: return None
        
        try:
            print("📊 Creating simplified overall backtest chart (Daily)...")
            
            df_for_resample = df.set_index('timestamp')
            
            # --- [FIX V5.8] 'first'/'last' 문자열 대신 lambda 함수 사용 ---
            ohlc_dict = {
                'open': lambda x: x.iloc[0],  # 'first' -> lambda
                'high': 'max',
                'low': 'min',
                'close': lambda x: x.iloc[-1], # 'last' -> lambda
                'volume': 'sum'
            }
            # --- [FIX V5.8] 수정 완료 ---
            
            df_plot = df_for_resample.resample('1D').agg(ohlc_dict).dropna()
            
            if df_plot.empty:
                print("⚠️ Overall chart failed: No 1D data to plot.")
                return None

            daily_entries = {}
            daily_exits = {}
            for trade in trades:
                entry_date = pd.to_datetime(trade['entry_time']).date()
                if entry_date not in daily_entries: daily_entries[entry_date] = []
                daily_entries[entry_date].append(trade['entry_price'])
                
                exit_date = pd.to_datetime(trade['exit_time']).date()
                if exit_date not in daily_exits: daily_exits[exit_date] = []
                daily_exits[exit_date].append(trade['exit_price'])

            entry_signals = pd.Series(index=df_plot.index, dtype=float)
            exit_signals = pd.Series(index=df_plot.index, dtype=float)
            
            # --- [FIX V5.9] '.date' attribute 오류 해결 ---
            # Pandas 2.x에서 DatetimeIndex의 .date 속성이 모호해짐에 따라,
            # .to_series().dt.date로 명시적으로 변환하여 비교합니다.
            df_plot_index_dates = df_plot.index.to_series().dt.date
            
            for date, prices in daily_entries.items():
                # [FIX V5.9] (df_plot.index.date == date)
                target_idx_list = df_plot.index[df_plot_index_dates == date]
                if not target_idx_list.empty:
                    entry_signals[target_idx_list[0]] = np.mean(prices)
                    
            for date, prices in daily_exits.items():
                # [FIX V5.9] (df_plot.index.date == date)
                target_idx_list = df_plot.index[df_plot_index_dates == date]
                if not target_idx_list.empty:
                    exit_signals[target_idx_list[0]] = np.mean(prices)
            # --- [FIX V5.9] 수정 완료 ---

            apds = []
            if entry_signals.notna().any():
                apds.append(mpf.make_addplot(entry_signals, type='scatter', markersize=80, marker='^', color='green'))
            if exit_signals.notna().any():
                apds.append(mpf.make_addplot(exit_signals, type='scatter', markersize=88, marker='v', color='red'))
            
            title = self._t('Overall Backtest Performance')
            
            fig, axes = mpf.plot(
                df_plot, type='candle', style='charles',
                addplot=apds, volume=False, figsize=(14, 8),
                datetime_format='%Y-%m-%d', xrotation=45,
                title=title, returnfig=True
            )
            
            filepath = os.path.join(self.base_dir, 'overall_backtest_chart.png')
            plt.savefig(filepath, dpi=120, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            
            print(f"✅ Simplified overall chart created: {filepath}")
            return filepath
        except Exception as e:
            # [V5.1] 더 구체적인 오류 로그
            print(f"❌ Simplified overall chart failed: {e}")
            if 'fig' in locals(): plt.close(fig)
            return None

    def _calculate_mode_stats(self, trades: List[Dict]) -> Dict:
        """모드별 통계 계산"""
        mode_stats = {}
        all_modes = set(t.get('trade_mode', 'unknown') for t in trades)
        
        for mode in all_modes:
            mode_trades = [t for t in trades if t.get('trade_mode') == mode]
            if not mode_trades: continue
            
            total_pnl = sum(t['pnl'] for t in mode_trades)
            win_rate = len([t for t in mode_trades if t['pnl'] > 0]) / len(mode_trades) if mode_trades else 0
            mode_stats[mode] = {
                'count': len(mode_trades),
                'total_pnl': total_pnl,
                'win_rate': win_rate
            }
        return mode_stats

    def _create_session_summary(self, config: Dict):
        """[V4.6] 세션 요약 텍스트 파일 생성 (V4.5.3에서 이동)"""
        try:
            summary_file = os.path.join(self.base_dir, 'session_summary.txt')
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write("=== Backtest Session Summary ===\n\n")
                f.write(f"Session ID: {self.session_id}\n")
                f.write(f"Generated: {self.report_data['generation_time']}\n")
                f.write(f"Period: {self.report_data['backtest_period']}\n")
                f.write(f"Strategy: {self.report_data['strategy_name']}\n\n")
                
                f.write("--- Performance ---\n")
                f.write(f"Initial Balance: ${self.report_data['initial_balance']:,.2f}\n")
                f.write(f"Final Balance: ${self.report_data['final_balance']:,.2f}\n")
                f.write(f"Total Return: {self.report_data['total_return']*100:+.2f}%\n")
                f.write(f"Total Trades: {self.report_data['total_trades']}\n")
                f.write(f"Win Rate: {self.report_data['win_rate']*100:.2f}%\n")
                f.write(f"Max Drawdown: {self.report_data['max_drawdown']*100:.2f}%\n")
                f.write(f"Sharpe Ratio: {self.report_data['sharpe_ratio']:.2f}\n")
                f.write(f"Profit Factor: {self.report_data['profit_factor']:.2f}\n")
                
                if self.cycle_charts:
                    f.write(f"Total Cycles: {len(self.cycle_charts)}\n")
                
                f.write("\n--- Backtest Configuration ---\n")
                f.write(f"Initial Balance: ${config.get('initial_balance'):,.2f}\n")
                f.write(f"Commission: {config.get('commission')}\n")
                f.write(f"Max Leverage: {config.get('max_leverage')}x\n")
                f.write(f"Max Open Entries: {config.get('max_open_entries')}\n")

            print(f"📋 Session summary created: {summary_file}")
        except Exception as e:
            print(f"⚠️ Error creating session summary: {e}")

    def _create_session_info(self, result: BacktestResult):
        """[V4.6] 세션 정보 JSON 파일 생성 (V4.5.3에서 이동)"""
        try:
            session_info = {
                'session_id': self.session_id, 'backtest_version': 'V5.9', # 버전 업데이트
                'session_time': self.report_data['generation_time'],
                'strategy_name': result.strategy_name,
                'backtest_period': result.backtest_period,
                'total_cycles': len(result.trading_cycles),
                'total_trades': len(result.trades),
                'performance': result.metrics,
                'configuration': result.config,
                'folder_structure': {
                    'base_directory': self.base_dir,
                    'cycle_charts/': 'All cycle charts for this session',
                    'overall_backtest_chart.png': 'Overall performance chart',
                    'backtest_report.html': 'HTML report for this session',
                    'session_info.json': 'This file',
                    'session_summary.txt': 'Text summary file'
                }
            }
            info_file = os.path.join(self.base_dir, 'session_info.json')
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(session_info, f, indent=2, default=str)
            print(f"📁 Session info created: {info_file}")
        except Exception as e:
            print(f"⚠️ Error creating session info: {e}")

    # --- [V4.9] V4.5.3 레이아웃 복원 ---
    
    def _create_cycle_charts_section(self) -> str:
        """[V4.11 수정] HTML 사이클 차트 섹션 (V4.5.3 레이아웃 복원 + PnL, TotalInvestment 추가)"""
        
        if not self.cycle_charts:
            return f"<div class='section'><h2>{self._t('Complete Trading Cycle Analysis')}</h2><p>No trading cycles generated.</p></div>"
            
        # 1. 레짐별 성과 분석
        regime_performance = {}
        for chart_info in self.cycle_charts:
            regime = chart_info.get('regime', 'Unknown')
            if regime not in regime_performance:
                regime_performance[regime] = {'count': 0, 'total_return': 0, 'profitable': 0, 'total_pnl': 0}
            
            stats = regime_performance[regime]
            stats['count'] += 1
            stats['total_return'] += chart_info['total_return_pct']
            stats['total_pnl'] += chart_info['cycle_pnl']
            if chart_info['cycle_pnl'] > 0: # [V4.10] PnL 기준으로 수익/손실 판단
                stats['profitable'] += 1
        
        regime_performance_html = ""
        for regime, stats in regime_performance.items():
            # [V4.10] PnL 기반으로 수익률 계산 (더 정확)
            # avg_return = stats['total_return'] / stats['count'] if stats['count'] > 0 else 0
            win_rate = (stats['profitable'] / stats['count']) * 100 if stats['count'] > 0 else 0
            regime_color = self._get_regime_color(regime)
            
            regime_performance_html += f"""
                <div class="info-card" style="border-left-color: {regime_color};">
                    <strong>{self._t(regime)}</strong><br>
                    {self._t('Cycles')}: {stats['count']}<br>
                    {self._t('PnL')}: <span class="{'positive' if stats['total_pnl'] > 0 else 'negative'} bold">${stats['total_pnl']:,.2f}</span><br>
                    {self._t('Win Rate')}: {win_rate:.1f}%
                </div>
            """
        
        # 2. 사이클 요약 테이블 [V4.11 수정] PnL, Total Investment 추가
        table_html = f"""
            <h3>📋 {self._t('Cycle Performance Summary')}</h3>
            <div style="overflow-x: auto; margin: 20px 0;">
                <table style="min-width: 1000px;">
                    <thead><tr>
                        <th>{self._t('Cycle #')}</th> <th>{self._t('Period')}</th> <th>{self._t('Duration')}</th>
                        <th>{self._t('Entries')}</th> <th>{self._t('Total Investment')}</th> 
                        <th>{self._t('PnL')}</th> <th>{self._t('Return')}</th> <th>{self._t('Max DD')}</th>
                        <th>{self._t('DD Duration')}</th> <th>{self._t('Recovery')}</th>
                    </tr></thead>
                    <tbody>
        """
        for chart_info in self.cycle_charts:
            cycle_duration = (chart_info['end_time'] - chart_info['start_time']).total_seconds() / 3600
            return_class = "positive" if chart_info['total_return_pct'] > 0 else "negative"
            pnl_class = "positive" if chart_info['cycle_pnl'] > 0 else "negative"
            table_html += f"""
                <tr>
                    <td>#{chart_info['cycle_num']}</td>
                    <td>{chart_info['start_time'].strftime('%m/%d %H:%M')}<br>to<br>{chart_info['end_time'].strftime('%m/%d %H:%M')}</td>
                    <td>{cycle_duration:.1f}h</td>
                    <td>{chart_info['position_count']}</td>
                    <td>${chart_info['total_investment']:,.2f}</td>
                    <td class="{pnl_class} bold">${chart_info['cycle_pnl']:,.2f}</td>
                    <td class="{return_class}">{chart_info['total_return_pct']:+.2f}%</td>
                    <td class="negative">{chart_info['max_drawdown_pct']:.2f}%</td>
                    <td>{chart_info['drawdown_duration_hours']:.1f}h</td>
                    <td>{self._t(chart_info['recovery_info'])}</td>
                </tr>
            """
        table_html += "</tbody></table></div>"

        # 3. [V4.9] V4.5.3의 'Cycle Performance Statistics' 섹션 추가
        stats_html = ""
        if self.cycle_charts:
            total_pnl = sum(c['cycle_pnl'] for c in self.cycle_charts)
            total_mdd = sum(c['max_drawdown_pct'] for c in self.cycle_charts)
            profitable_cycles = sum(1 for c in self.cycle_charts if c['cycle_pnl'] > 0)
            
            avg_pnl = total_pnl / len(self.cycle_charts) if self.cycle_charts else 0
            avg_mdd = total_mdd / len(self.cycle_charts) if self.cycle_charts else 0
            profitability_rate = (profitable_cycles / len(self.cycle_charts)) * 100 if self.cycle_charts else 0
            max_mdd_cycle = max(self.cycle_charts, key=lambda x: x['max_drawdown_pct']) if self.cycle_charts else {}
            
            stats_html = f"""
            <div style="background: #f0f4f8; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 5px solid #007bff;">
                <h4 style="margin-top: 0; font-size: 1.3em;">{self._t('Cycle Performance Statistics')}</h4>
                <div class="info-grid">
                    <div class="info-card" style="border-left-color: {'#28a745' if avg_pnl > 0 else '#dc3545'};">
                        <strong>{self._t('Average Cycle Return')}:</strong><br>
                        <span style="font-size: 24px; font-weight: bold;">${avg_pnl:,.2f}</span>
                    </div>
                    <div class="info-card" style="border-left-color: #dc3545;">
                        <strong>{self._t('Average Max DD')}:</strong><br>
                        <span style="font-size: 24px; font-weight: bold;">{avg_mdd:.2f}%</span>
                    </div>
                    <div class="info-card" style="border-left-color: #17a2b8;">
                        <strong>{self._t('Profitability Rate')}:</strong><br>
                        <span style="font-size: 24px; font-weight: bold;">{profitability_rate:.1f}%</span>
                        <div style="font-size: 14px; color: #6c757d; margin-top: 5px;">
                            ({profitable_cycles}/{len(self.cycle_charts)} cycles)
                        </div>
                    </div>
                    <div class="info-card" style="border-left-color: #fd7e14;">
                        <strong>{self._t('Worst DD')} (Cycle #{max_mdd_cycle.get('cycle_num', 'N/A')}):</strong><br>
                        <span style="font-size: 24px; font-weight: bold; color: #dc3545;">{max_mdd_cycle.get('max_drawdown_pct', 0):.2f}%</span>
                        <div style="font-size: 14px; color: #6c757d; margin-top: 5px;">
                            {self._t(max_mdd_cycle.get('recovery_info', 'N/A'))}
                        </div>
                    </div>
                </div>
            </div>
            """

        # 4. 개별 사이클 상세 (V4.5.3 레이아웃 복원) [V4.11] PnL, TotalInvestment, AvgPrice 표시
        details_html = ""
        for chart_info in self.cycle_charts:
            regime_color = self._get_regime_color(chart_info['regime'])
            
            details_html += f"""
            <div class="cycle-section">
                <h3>🔹 Cycle #{chart_info['cycle_num']} - {self._t('Detailed Performance Metrics')}</h3>
                
                <div class="info-grid">
                    <div class="info-card" style="border-left-color: #28a745;">
                        <strong>📅 {self._t('Cycle Period')}:</strong><br>
                        <div style="margin-top: 8px; font-size: 1.1em;">
                            {chart_info['start_time'].strftime('%Y-%m-%d %H:%M')}<br>
                            to<br>
                            {chart_info['end_time'].strftime('%Y-%m-%d %H:%M')}
                        </div>
                    </div>
                    <div class="info-card" style="border-left-color: #007bff;">
                        <strong>📊 {self._t('Position Summary')}:</strong><br>
                        <div style="margin-top: 8px; font-size: 1.1em;">
                            {self._t('Total Entries')}: {chart_info['position_count']}<br>
                            {self._t('Total Investment')}: ${chart_info['total_investment']:,.2f}<br>
                    
                            {self._t('Leverage')}: {chart_info['actual_leverage']:.1f}x
                        </div>
                    </div>
                    <div class="info-card" style="border-left-color: #ffc107;">
                        <strong>💰 {self._t('Performance')}:</strong><br>
                        <div style="margin-top: 8px; font-size: 1.1em;">
                            {self._t('Avg. Entry Price')}: ${chart_info['avg_price']:.2f}<br>
                            {self._t('PnL')}: <span class="{'positive' if chart_info['cycle_pnl'] > 0 else 'negative'} bold">${chart_info['cycle_pnl']:,.2f}</span><br>
                            {self._t('Return')}: <span class="{'positive' if chart_info['total_return_pct'] > 0 else 'negative'}">{chart_info['total_return_pct']:+.2f}%</span>
                        </div>
                    </div>
                    <div class="info-card" style="border-left-color: #dc3545;">
                        <strong>📉 {self._t('Risk Analysis')}:</strong><br>
                        <div style="margin-top: 8px; font-size: 1.1em;">
                            {self._t('Max DD')}: <span class="negative">{chart_info['max_drawdown_pct']:.2f}%</span><br>
                            {self._t('DD Duration')}: {chart_info['drawdown_duration_hours']:.1f}h
                        </div>
                    </div>
                </div>
                
                <div class="mdd-analysis-card">
                    <h4>📊 {self._t('Maximum Drawdown Analysis')}</h4>
                    <div class="info-grid">
                        <div>
                            <strong>🏔️ {self._t('Peak Equity')}:</strong><br>
                            <span style="color: #28a745; font-weight: bold;">${chart_info['peak_equity']:.2f}</span><br>
                            <small style="color: #6c757d;">({self._t('Peak Time')}: {chart_info['peak_time'].strftime('%m/%d %H:%M')})</small>
                        </div>
                        <div>
                            <strong>🕳️ {self._t('Trough Equity')}:</strong><br>
                            <span style="color: #dc3545; font-weight: bold;">${chart_info['trough_equity']:.2f}</span><br>
                            <small style="color: #6c757d;">({self._t('Trough Time')}: {chart_info['trough_time'].strftime('%m/%d %H:%M')})</small>
                        </div>
                        <div>
                            <strong>📉 {self._t('DD Amount')}:</strong><br>
                            <span style="color: #dc3545; font-weight: bold;">-${chart_info['max_drawdown_amount']:.2f}</span><br>
                            <small style="color: #6c757d;">({chart_info['max_drawdown_pct']:.2f}% from peak)</small>
                        </div>
                        <div>
                            <strong>⏱️ {self._t('Recovery Status')}:</strong><br>
                            <span style="color: {'#28a745' if 'Recovered' in chart_info.get('recovery_info', '') else '#dc3545'}; font-weight: bold;">
                                {self._t(chart_info.get('recovery_info', 'N/A'))}
                            </span>
                        </div>
                    </div>
                </div>

                {self._create_position_details_table(chart_info['position_details'], chart_info['cycle_num'])}
                
                <div class="chart-container">
                    <img src="{chart_info['relative_path']}" alt="Trading Cycle {chart_info['cycle_num']}"
                         class="cycle-chart" onclick="toggleZoom(this)">
                </div>
            </div>
            """
            
        return f"""
        <div class="section">
            <h2>🔄 {self._t('Complete Trading Cycle Analysis')}</h2>
            <div style="background: #f0f4f8; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                <h4 style="margin-top: 0;">{self._t('Performance by Market Regime')}</h4>
                <div class="info-grid">
                    {regime_performance_html if regime_performance_html else "<div>No regime data available</div>"}
                </div>
            </div>
            {table_html}
            {stats_html}  {details_html}
            
            <div class="section" style="background: #fff3cd; border-left: 4px solid #ffc107;">
                <h4>{self._t('Chart Explanation')}</h4>
                <div class="info-grid">
                    <div><strong>{self._t('Yellow Highlighted Area')}</strong><br>{self._t('Actual trading period')}</div>
                    <div><strong>{self._t('Green Triangle (▲)')}</strong><br>{self._t('Buy entry signals')}</div>
                    <div><strong>{self._t('Red Triangle (▼)')}</strong><br>{self._t('Sell exit signals')}</div>
                    <div><strong>{self._t('5-minute Candlesticks')}</strong><br>{self._t('Price movements')}</div>
                </div>
            </div>
        </div>
        """
        
    def _create_position_details_table(self, position_details: List[Dict], cycle_num: int) -> str:
        """[V5.2] (버그 #1 수정 확인) 이제 position_details에 SELL이 포함됩니다."""
        if not position_details: return ""
        
        buy_actions = [p for p in position_details if p.get('type') == 'BUY']
        sell_actions = [p for p in position_details if p.get('type') == 'SELL']

        table_html = f"""
        <div style="margin-top: 20px;">
            <h4 style="margin-top:0;">📋 {self._t('Position Details')} - Cycle #{cycle_num}</h4>
             <div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                <strong>Summary:</strong> 
                {len(buy_actions)} Buys, {len(sell_actions)} Sells, 
                Total {len(position_details)} Actions
            </div>
            <table style="font-size: 12px; margin-top:0;">
                <thead><tr>
                    <th>{self._t('Time')}</th> <th>{self._t('Type')}</th> <th>{self._t('Price')}</th>
                    <th>{self._t('Size')}</th> <th>{self._t('Mode')}</th> <th>{self._t('Reason')}</th>
                </tr></thead>
                <tbody>
        """
        for pos in position_details:
            action_type = pos.get('type', 'UNKNOWN')
            action_color = "#28a745" if action_type == 'BUY' else "#dc3545" if action_type == 'SELL' else "#6c757d"
            size_display = f"{pos['size']:.1%}"
            
            table_html += f"""
                <tr>
                    <td>{pos['time'].strftime('%m/%d %H:%M')}</td>
                    <td style="color: {action_color}; font-weight: bold;">{action_type}</td>
                    <td>${pos['price']:.2f}</td>
                    <td>{size_display}</td>
                    <td>{self._t(pos['mode'])}</td>
                    <td>{pos['reason']}</td>
                </tr>
            """
        table_html += "</tbody></table></div>"
        return table_html

    def _get_regime_color(self, regime: str) -> str:
        """[v2.0 수정] 8대 레짐 색상 반환"""
        regime_colors = {
            'Uptrend-Impulse': '#28a745', 'Uptrend-Normal': '#20c997', 'Uptrend-Consolidation': '#17a2b8',
            'Downtrend-Impulse': '#dc3545', 'Downtrend-Normal': '#fd7e14', 'Downtrend-Consolidation': '#ffc107',
            'Full-Consolidation': '#ffc107', 'Transition': '#6f42c1',
            'Unknown': '#6c757d'
        }
        return regime_colors.get(regime, '#6c757d')

    def _create_html_content(self, metrics: Dict, mode_stats: Dict, trades: List[Dict], 
                           overall_chart_section: str = "", 
                           regime_explanation_html: str = "", # [V4.9] 추가
                           cycle_charts_section: str = "") -> str:
        """[V4.11 수정] 최종 HTML 문자열 생성 (V4.5.3 레이아웃)"""
        
        # 최근 거래 내역
        trade_rows = ""
        for trade in trades[-20:]:
            pnl_class = "positive" if trade['pnl'] > 0 else "negative"
            trade_rows += f"""
            <tr>
                <td>{pd.to_datetime(trade['entry_time']).strftime('%m/%d %H:%M')}</td>
                <td>{pd.to_datetime(trade['exit_time']).strftime('%m/%d %H:%M')}</td>
                <td>${trade['entry_price']:.2f}</td>
                <td>${trade['exit_price']:.2f}</td>
                <td class="{pnl_class}">{trade['pnl']:+.2f}</td>
                <td>{self._t(trade.get('trade_mode', 'N/A'))}</td>
                <td>{trade.get('reason', 'N/A')}</td>
            </tr>
            """
        
        # 모드별 성과
        mode_stats_html = ""
        for mode, stats in mode_stats.items():
            mode_stats_html += f"""
            <div class="mode-card">
                <h3>{self._t(mode)}</h3>
                <div class="metric-value {'positive' if stats['total_pnl'] > 0 else 'negative'}">
                    {stats['total_pnl']:+.2f} USDT
                </div>
                <div>{self._t('Trades')}: {stats['count']}</div>
                <div>{self._t('Win Rate')}: {stats['win_rate']*100:.1f}%</div>
            </div>
            """
        
        # HTML 템플릿
        html = f"""
        <!DOCTYPE html>
        <html lang="{self.language}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{self._t('Backtest Report')} V5.9</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 1800px; margin: 0 auto; background: white; padding: 25px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }}
                .section {{ margin-bottom: 35px; padding: 25px; border: 1px solid #ddd; border-radius: 8px; width: 100%; overflow: hidden; }}
                .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; }}
                .metric-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
                .metric-value {{ font-size: 28px; font-weight: bold; margin: 10px 0; }}
                .positive {{ color: #28a745; }}
                .negative {{ color: #dc3545; }}
                .bold {{ font-weight: bold; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }}
                th, td {{ padding: 14px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f8f9fa; font-weight: bold; }}
                .mode-stats {{ display: flex; justify-content: space-around; flex-wrap: wrap; gap: 15px; }}
                .mode-card {{ flex: 1; min-width: 200px; padding: 20px; background: #f8f9fa; border-radius: 8px; text-align: center; }}
                .chart-container {{ width: 100%; overflow: hidden; margin: 20px 0; }}
                .cycle-chart {{ width: 100%; max-width: 100%; height: auto; border: 1px solid #ccc; border-radius: 5px; cursor: pointer; }}
                .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.95); padding: 20px; box-sizing: border-box; overflow: auto; }}
                .modal-content {{ margin: auto; display: block; max-width: 95%; max-height: 95%; }}
                .close {{ position: fixed; top: 20px; right: 35px; color: #fff; font-size: 40px; font-weight: bold; cursor: pointer; }}
                .cycle-section {{ border: 1px solid #e9ecef; border-radius: 12px; padding: 25px; margin: 30px 0; background: #fff; }}
                
                /* [V4.9] V4.5.3의 4-Grid 레이아웃 강제 */
                .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin: 20px 0; }}
                .info-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #007bff; }}
                
                /* [V4.9] V4.5.3의 노란색 MDD 분석 카드 스타일 */
                .mdd-analysis-card {{
                    background: #fffaf0; 
                    padding: 15px; 
                    border-radius: 8px; 
                    margin: 20px 0; 
                    border-left: 4px solid #fd7e14;
                }}
                .mdd-analysis-card h4 {{
                    margin-top: 0; 
                    color: #856404;
                }}
                /* [V4.11] MDD 카드 내부 그리드 스타일 수정 */
                .mdd-analysis-card .info-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); /* 좁은 공간에 맞게 */
                    gap: 15px;
                    margin: 10px 0 0 0; /* 위쪽 마진 축소 */
                }}
                .mdd-analysis-card .info-grid > div {{ /* MDD 카드 내부 아이템 스타일 */
                    background: #fff;
                    padding: 10px;
                    border-radius: 5px;
                    border: 1px solid #eee;
                }}

            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{self._t('Backtest Report')} V5.9</h1>
                    <p>{self._t('Strategy')}: {self.report_data['strategy_name']}</p>
                    <p>{self._t('Period')}: {self.report_data['backtest_period']}</p>
                    <p>{self._t('Generated Time')}: {self.report_data['generation_time']}</p>
                </div>
                
                {overall_chart_section}
                {regime_explanation_html}
                
                <div class="section">
                    <h2>📊 {self._t('Key Performance Metrics')}</h2>
                    <div class="metric-grid">
                        <div class="metric-card">
                            <div>{self._t('Final Balance')}</div>
                            <div class="metric-value">{self.report_data['final_balance']:,.2f} USDT</div>
                        </div>
                        <div class="metric-card">
                            <div>{self._t('Total Return')}</div>
                            <div class="metric-value {'positive' if self.report_data['total_return'] > 0 else 'negative'}">
                                {self.report_data['total_return']*100:+.2f}%
                            </div>
                        </div>
                        <div class="metric-card">
                            <div>{self._t('Win Rate')}</div>
                            <div class="metric-value">{self.report_data['win_rate']*100:.2f}%</div>
                        </div>
                        <div class="metric-card">
                            <div>{self._t('Max Drawdown')}</div>
                            <div class="metric-value negative">{self.report_data['max_drawdown']*100:.2f}%</div>
                        </div>
                        <div class="metric-card">
                            <div>{self._t('Sharpe Ratio')}</div>
                            <div class="metric-value {'positive' if self.report_data['sharpe_ratio'] > 0 else 'negative'}">
                                {self.report_data['sharpe_ratio']:.2f}
                            </div>
                        </div>
                        <div class="metric-card">
                            <div>{self._t('Profit Factor')}</div>
                            <div class="metric-value {'positive' if self.report_data['profit_factor'] > 1 else 'negative'}">
                                {self.report_data['profit_factor']:.2f}
                            </div>
                        </div>
                    </div>
                </div>
                
                {cycle_charts_section}
                
                <div class="section">
                    <h2>🎯 {self._t('Mode Performance Analysis')}</h2>
                    <div class="mode-stats">
                        {mode_stats_html}
                    </div>
                </div>
                
                <div class="section">
                    <h2>📈 {self._t('Detailed Performance Metrics')}</h2>
                    <table>
                        <thead>
                            <tr><th>{self._t('Metric')}</th><th>Value</th></tr>
                        </thead>
                        <tbody>
                            <tr><td>{self._t('Total Trades')}</td><td>{metrics.get('total_trades', 0)}</td></tr>
                            <tr><td>{self._t('Profit Factor')}</td><td>{metrics.get('profit_factor', 0):.2f}</td></tr>
                            <tr><td>{self._t('Average Trade')}</td><td>{metrics.get('avg_trade', 0):.2f} USDT</td></tr>
                            <tr><td>{self._t('Average Winning Trade')}</td><td>{metrics.get('avg_winning_trade', 0):.2f} USDT</td></tr>
                            <tr><td>{self._t('Average Losing Trade')}</td><td>{metrics.get('avg_losing_trade', 0):.2f} USDT</td></tr>
                            <tr><td>{self._t('Largest Winning Trade')}</td><td>{metrics.get('largest_winning_trade', 0):.2f} USDT</td></tr>
                            <tr><td>{self._t('Largest Losing Trade')}</td><td>{metrics.get('largest_losing_trade', 0):.2f} USDT</td></tr>
                        </tbody>
                    </table>
                </div>
                
                <div class="section">
                    <h2>📋 {self._t('Recent Trade History (Last 20)')}</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>{self._t('Entry Time')}</th> <th>{self._t('Exit Time')}</th>
                                <th>{self._t('Entry Price')}</th> <th>{self._t('Exit Price')}</th> <th>PnL</th>
                                <th>{self._t('Mode')}</th> <th>{self._t('Reason')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {trade_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            <div id="imageModal" class="modal"><span class="close" onclick="closeModal()">&times;</span><img class="modal-content" id="modalImage"></div>
            <script>
                function toggleZoom(img) {{ var modal = document.getElementById("imageModal"); modal.style.display = "block"; document.getElementById("modalImage").src = img.src; }}
                function closeModal() {{ document.getElementById("imageModal").style.display = "none"; }}
                document.getElementById('imageModal').addEventListener('click', function(e) {{ if (e.target === this) closeModal(); }});
                document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeModal(); }});
            </script>
        </body>
        </html>
        """
        return html