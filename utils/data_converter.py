import pandas as pd
import numpy as np
from typing import Optional
import os

class DataConverter:
    """
    [V4.6 신규]
    데이터 변환 유틸리티.
    'Golden Source'(예: 5m) 데이터를 받아 상위 타임프레임(1h, 4h 등)을
    정합성이 보장된(gap-filled) 상태로 생성(resample)합니다.
    """
    
    @staticmethod
    def resample_dataframe(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """
        [V4.6 신규] 공통 리샘플링 로직
        12:00 -> 14:00 갭이 있더라도, 13:00 행을 생성(NaN)하고 보정합니다.
        """
        if df.empty:
            return pd.DataFrame()
            
        df = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp')
        
        # 리샘플링 규칙 정의
        logic = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        # .resample().agg()는 갭을 NaN으로 채워서 생성합니다.
        resampled_df = df.resample(rule).agg(logic)
        
        # 갭(Gap) 보정 (DataManager의 _validate_and_remediate와 유사)
        # 1. Volume: 0으로 채움
        resampled_df['volume'] = resampled_df['volume'].fillna(0)
        # 2. OHLC: 직전 값으로 채움
        ohlc_cols = ['open', 'high', 'low', 'close']
        resampled_df[ohlc_cols] = resampled_df[ohlc_cols].ffill()
        # 3. 가격 오류 수정
        resampled_df['high'] = resampled_df[ohlc_cols].max(axis=1)
        resampled_df['low'] = resampled_df[ohlc_cols].min(axis=1)
        # 4. 맨 앞 NaN 제거
        resampled_df = resampled_df.dropna(subset=['close'])
        
        return resampled_df.reset_index()

    @staticmethod
    def resample_to_15m(df_5m: pd.DataFrame) -> pd.DataFrame:
        """5분봉 -> 15분봉 변환"""
        print("   [Convert] Resampling 5m -> 15m...")
        return DataConverter.resample_dataframe(df_5m, '15T')

    @staticmethod
    def resample_to_1h(df_5m: pd.DataFrame) -> pd.DataFrame:
        """5분봉 -> 1시간봉 변환"""
        print("   [Convert] Resampling 5m -> 1h...")
        return DataConverter.resample_dataframe(df_5m, '1H')

    @staticmethod
    def resample_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
        """1시간봉 -> 4시간봉 변환"""
        print("   [Convert] Resampling 1h -> 4h...")
        return DataConverter.resample_dataframe(df_1h, '4H')

    @staticmethod
    def resample_to_1d(df_4h: pd.DataFrame) -> pd.DataFrame:
        """4시간봉 -> 1일봉 변환"""
        print("   [Convert] Resampling 4h -> 1d...")
        # 1일봉은 UTC 00:00 기준으로 리샘플링
        return DataConverter.resample_dataframe(df_4h, '1D')


