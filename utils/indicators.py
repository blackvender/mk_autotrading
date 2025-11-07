import pandas as pd
import numpy as np
import ta
from typing import Dict, List, Optional
import warnings
from scipy.signal import argrelextrema # [신규] 극값 탐지를 위해 추가
import math # [신규] find_psychological_levels에서 사용

warnings.filterwarnings('ignore')

class TechnicalIndicators:
    """
    [V4.7 리팩토링]
    'calculate_all_indicators' 대신 개별 정적 메서드를 제공하여
    FeatureFactory가 동적으로 지표를 선택하여 계산할 수 있도록 합니다.
    """
    
    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """RSI 계산"""
        if 'close' not in df.columns or df['close'].isnull().all():
            return pd.Series(index=df.index, dtype=float)
        return ta.momentum.RSIIndicator(df['close'], window=period).rsi()

    @staticmethod
    def ema(df: pd.DataFrame, period: int) -> pd.Series:
        """EMA 계산"""
        if 'close' not in df.columns or df['close'].isnull().all():
            return pd.Series(index=df.index, dtype=float)
        return ta.trend.EMAIndicator(df['close'], window=period).ema_indicator()

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR 계산"""
        try:
            if not all(col in df.columns for col in ['high', 'low', 'close']):
                return pd.Series(index=df.index, dtype=float)
            return ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=period).average_true_range()
        except Exception as e:
            # print(f"Error calculating ATR: {e}")
            return pd.Series(index=df.index, dtype=float)

    @staticmethod
    def volume_avg(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """거래량 이동평균 계산"""
        if 'volume' not in df.columns:
            return pd.Series(index=df.index, dtype=float)
        return df['volume'].rolling(window=period, min_periods=1).mean()

    @staticmethod
    def bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> Dict[str, pd.Series]:
        """볼린저 밴드 계산"""
        if 'close' not in df.columns or df['close'].isnull().all():
            return {
                'bb_upper': pd.Series(index=df.index, dtype=float),
                'bb_middle': pd.Series(index=df.index, dtype=float),
                'bb_lower': pd.Series(index=df.index, dtype=float),
                'bb_width': pd.Series(index=df.index, dtype=float)
            }
        bb = ta.volatility.BollingerBands(df['close'], window=period, window_dev=std_dev)
        return {
            'bb_upper': bb.bollinger_hband(),
            'bb_middle': bb.bollinger_mavg(),
            'bb_lower': bb.bollinger_lband(),
            'bb_width': bb.bollinger_wband()
        }
# --- [Phase 3.2.1 신규 추가] ---
    @staticmethod
    def find_local_extrema(df: pd.DataFrame, order: int = 5) -> (pd.Series, pd.Series):
        """
        [v1.0] 국소 극대값(저항 후보)과 극소값(지지 후보)을 탐지합니다.
        scipy.signal.argrelextrema를 사용하여 'Fractals'와 유사한 극점을 찾습니다.
        """
        if 'high' not in df.columns or 'low' not in df.columns:
            return pd.Series(index=df.index, dtype=float), pd.Series(index=df.index, dtype=float)

        # 1. 극소값 (지지 후보) 찾기
        minima_indices = argrelextrema(df['low'].values, np.less, order=order)[0]
        support_levels = pd.Series(np.nan, index=df.index)
        support_levels.iloc[minima_indices] = df['low'].iloc[minima_indices]
        
        # 2. 극대값 (저항 후보) 찾기
        maxima_indices = argrelextrema(df['high'].values, np.greater, order=order)[0]
        # [수정] np.nan으로 초기화해야 합니다. (기존: pd.Series(index=df.index))
        resistance_levels = pd.Series(np.nan, index=df.index) 
        resistance_levels.iloc[maxima_indices] = df['high'].iloc[maxima_indices]
        
        return support_levels, resistance_levels

# --- [Phase 3.2.1 체크리스트 2: 신규 추가] ---
    @staticmethod
    def find_psychological_levels(current_price: float, symbol: str, n_levels_around: int = 3) -> Dict[str, List[float]]:
        """
        [v1.2] 현재 가격 주변의 "기준이 될 만한" 심리적 지지/저항선을 우선순위별로 찾습니다.
        (v1.1 수정: 'BTC'/'ETH' 하드코딩 대신, 가격의 자릿수에 기반한 동적 스텝 계산)
        
        Args:
            current_price (float): 현재 가격
            n_levels_around (int): 현재가 기준 상하 N개 레벨 탐색
            
        Returns:
            Dict[str, List[float]]: 우선순위별 S/R 레벨 딕셔너리 (major, medium, minor)
        """
        
        if current_price <= 0:
            return {'major': [], 'medium': [], 'minor': []}

        try:
            # 1. 가격의 자릿수(order of magnitude) 기반으로 스텝 결정
            # 예: current_price = 68500
            order_power = math.floor(math.log10(current_price)) # 4
            
            # 2. 우선순위별 스텝 정의 (1-5-10 원칙)
            # 예: 10000 (major), 5000 (medium), 1000 (minor)
            major_step = 10 ** order_power               # 10000
            medium_step = major_step / 2.0             # 5000
            minor_step = major_step / 10.0             # 1000
            
            # (ETH, 3450) -> major=1000, medium=500, minor=100
            # (XRP, 0.5) -> major=0.1, medium=0.05, minor=0.01

            steps_priority = [
                ('major', major_step),
                ('medium', medium_step),
                ('minor', minor_step)
            ]
            
            # 가격이 1.0 미만일 때 예외 처리
            if current_price < 1.0:
                 steps_priority = [
                    ('major', 0.5), ('medium', 0.1), ('minor', 0.05)
                 ]
            
        except Exception:
            steps_priority = [('major', 100), ('medium', 50), ('minor', 10)] # Fallback

        
        levels = {'major': set(), 'medium': set(), 'minor': set()}
        
        for priority, step in steps_priority:
            if step <= 0: continue
            
            base_level = round(math.floor(current_price / step) * step, 8)
            for i in range(-n_levels_around, n_levels_around + 1):
                level_to_add = round(base_level + (i * step), 8)
                if level_to_add > 0:
                    levels[priority].add(level_to_add)

        # 중복 제거 (하위 우선순위에서 상위 우선순위 레벨 제거)
        levels['medium'] = levels['medium'] - levels['major']
        levels['minor'] = levels['minor'] - levels['medium'] - levels['major']

        return {
            'major': sorted(list(levels['major'])),
            'medium': sorted(list(levels['medium'])),
            'minor': sorted(list(levels['minor'])),
        }
        # --- [Phase 3.2.3 v2.0 최종안: 신규 추가] ---

    @staticmethod
    def wma(df: pd.DataFrame, period: int) -> pd.Series:
        """가중 이동평균 (WMA) - HMA의 구성 요소"""
        if 'close' not in df.columns or df['close'].isnull().all():
            return pd.Series(index=df.index, dtype=float)
        return ta.trend.WMAIndicator(df['close'], window=period).wma()

    @staticmethod
    def calculate_hma(df: pd.DataFrame, period: int = 16) -> pd.Series:
        """Hull Moving Average (HMA) - 지연 최소화 이동평균"""
        # HMA(n) = WMA( 2*WMA(n/2) - WMA(n), sqrt(n) )
        half_period = int(period / 2)
        sqrt_period = int(np.sqrt(period))
        
        wma_half = __class__.wma(df, half_period)
        wma_full = __class__.wma(df, period)
        
        raw_hma = (2 * wma_half) - wma_full
        
        # raw_hma가 pd.Series이므로, df 대신 이걸로 새 TechnicalIndicators 인스턴스를 만들 수 없음.
        # 따라서 raw_hma를 임시 df로 만들어 wma를 재계산.
        hma_df = pd.DataFrame({'close': raw_hma})
        hma = __class__.wma(hma_df, sqrt_period)
        
        return hma

    @staticmethod
    def calculate_fractal_efficiency(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """프랙탈 효율성 (Fractal Efficiency)"""
        price_change = df['close'].diff(period)
        total_movement = abs(df['close'].diff()).rolling(period).sum()
        
        efficiency = price_change / (total_movement + 1e-10)
        return efficiency.clip(-1.0, 1.0) # -1.0 ~ +1.0

    @staticmethod
    def calculate_smi(df: pd.DataFrame, k_period: int = 13, d_period: int = 25, smooth: int = 9) -> pd.Series:
        """
        Stochastic Momentum Index (SMI) 오실레이터 
        [v1.3.1] ta.SMIIndicator 의존성 제거 (AttributeError 해결)
        다른 AI가 제안한 수동 계산 로직(오타 수정)을 사용합니다.
        """
        if not all(col in df.columns for col in ['high', 'low', 'close']):
            return pd.Series(index=df.index, dtype=float)

        # 1. k_period 동안의 최고/최저가
        highest_high = df['high'].rolling(k_period).max()
        lowest_low = df['low'].rolling(k_period).min()
        
        # 2. 중심 가격 및 가격/범위 차이
        median_price = (highest_high + lowest_low) / 2
        price_diff = df['close'] - median_price
        range_diff = highest_high - lowest_low
        
        # 3. SMI 계산
        # [수정] 원본 AI 코드 의 (range_diff / 2 * 100)는 오타로 보임.
        # 100 * (price_diff / (range_diff / 2))가 표준 스토캐스틱 계산.
        smi_base = 100 * (price_diff / (range_diff / 2 + 1e-10))
        
        # 4. 스무딩 (제안 AI의 rolling().mean() 방식 적용)
        smi_raw = smi_base.rolling(smooth).mean()
        smi_signal = smi_raw.rolling(d_period).mean()
        
        return (smi_raw - smi_signal).fillna(0) # 오실레이터 형태

    @staticmethod
    def calculate_keltner_channel(df: pd.DataFrame, period: int = 20, multiplier: float = 2.0) -> Dict[str, pd.Series]:
        """Keltner Channel (Squeeze 감지용)"""
        # 'ta' 라이브러리의 KeltnerChannel 사용
        kc = ta.volatility.KeltnerChannel(
            high=df['high'], 
            low=df['low'], 
            close=df['close'], 
            window=period, 
            window_atr=period, # ATR 주기도 동일하게
            multiplier=multiplier
        )
        return {
            'upper': kc.keltner_channel_hband(),
            'middle': kc.keltner_channel_mband(),
            'lower': kc.keltner_channel_lband()
        }

    @staticmethod
    def is_volatility_squeeze(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """볼린저/켈트너 채널 기반 변동성 스퀴즈 감지"""
        # 1. 켈트너 채널 계산
        kc = __class__.calculate_keltner_channel(df, period, 2.0)
        kc_width = (kc['upper'] - kc['lower']) / (kc['middle'] + 1e-10)
        
        # 2. 볼린저 밴드 계산
        bb = __class__.bollinger_bands(df, period, 2.0)
        bb_width = bb['bb_width'] # ta 라이브러리의 bb_width는 (hband-lband)/mavg 임
        
        # 3. Keltner Channel이 Bollinger Band 내부에 있는지 확인 (스퀴즈 상태)
        # [수정] 원본 로직(kc_width < bb_width)은 ta 라이브러리 호환성 문제로 (bb_width가 %가 아님)
        # ta 라이브러리의 KeltnerChannel / BollingerBands 로직을 직접 비교
        squeeze_on = (bb['bb_lower'] < kc['lower']) & (bb['bb_upper'] > kc['upper'])
        
        # 4. 스퀴즈 상태 + 채널 폭이 50일 기준 하위 30%로 좁아졌는지 확인
        is_low_volatility = kc_width < kc_width.rolling(50).quantile(0.3)
        
        return squeeze_on & is_low_volatility
    # --- [v2.0 지표 추가 완료] ---