import pandas as pd
import numpy as np
import os
import time
from datetime import datetime, timedelta
from binance.client import Client
from typing import Dict, List, Optional, Tuple
import requests
import json

class AdvancedDataManager:
    def __init__(self):
        self.data_path = './data'
        self.setup_directories()
        
        # Binance API용 타임프레임 맵
        self.TIMEFRAME_MAP_BINANCE = {
            '1m': Client.KLINE_INTERVAL_1MINUTE, '5m': Client.KLINE_INTERVAL_5MINUTE,
            '15m': Client.KLINE_INTERVAL_15MINUTE, '1h': Client.KLINE_INTERVAL_1HOUR,
            '4h': Client.KLINE_INTERVAL_4HOUR, '1d': Client.KLINE_INTERVAL_1DAY
        }
        # Pandas Resample용 타임프레임 맵
        self.TIMEFRAME_MAP_PANDAS = {
            '1m': '1T', '5m': '5T', '15m': '15T',
            '1h': '1H', '4h': '4H', '1d': '1D',
        }
        
    def setup_directories(self):
        """필요한 디렉토리 생성"""
        directories = ['raw/csv', 'raw/database', 'processed', 'historical/csv', 'backtest_results']
        for dir_name in directories:
            os.makedirs(os.path.join(self.data_path, dir_name), exist_ok=True)
    
    def get_csv_filename(self, symbol: str, timeframe: str) -> str:
        """CSV 파일명 생성"""
        return os.path.join(self.data_path, 'historical', 'csv', f"{symbol}_{timeframe}.csv")
    
    def get_metadata_filename(self, symbol: str, timeframe: str) -> str:
        """메타데이터 파일명 생성"""
        return os.path.join(self.data_path, 'historical', 'csv', f"{symbol}_{timeframe}_metadata.json")
    
    def _validate_and_remediate(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        [V4.6 신규] 데이터 검증 및 수정(Remediation) 함수
        'Golden Source'(1m 또는 5m) 데이터의 갭을 채우는 데 사용됩니다.
        """
        if df.empty:
            return df
            
        print(f"   [Validation] Validating and remediating '{timeframe}' data ({len(df)} rows)...")
        
        # 1. 중복 제거 및 시간순 정렬
        df = df.drop_duplicates(subset=['timestamp'], keep='last')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # 2. 타임스탬프 갭(Gap) 채우기
        freq = self.TIMEFRAME_MAP_PANDAS.get(timeframe)
        if freq:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp')
            
            # .asfreq()로 누락된 타임스탬프에 NaN 행 생성
            df = df.asfreq(freq)
            
            # 3. 데이터 보정 (Remediation)
            # 3a. Volume: 갭(NaN)은 거래가 없었음을 의미하므로 0으로 채움
            df['volume'] = df['volume'].fillna(0)
            
            # 3b. OHLC: 갭(NaN)은 가격 변동이 없었음을 의미하므로 직전 값으로 채움 (ffill)
            ohlc_cols = ['open', 'high', 'low', 'close']
            df[ohlc_cols] = df[ohlc_cols].ffill()
            
            # 3c. 가격 오류 수정 (High/Low 강제 조정)
            df['high'] = df[ohlc_cols].max(axis=1)
            df['low'] = df[ohlc_cols].min(axis=1)
            
            # 3d. ffill 후에도 남은 NaN 제거 (데이터 시작 부분)
            df = df.dropna(subset=['close'])
            
            df = df.reset_index()
            print(f"   [Validation] Remediation complete. Final rows: {len(df)}")
            
        else:
            print(f"   [Validation] ⚠️ Unknown timeframe '{timeframe}'. Skipping gap filling.")
            
        return df

    def save_to_csv(self, df: pd.DataFrame, symbol: str, timeframe: str):
        """
        [수정] 데이터를 CSV로 저장 (검증 및 수정 로직 추가)
        """
        csv_file = self.get_csv_filename(symbol, timeframe)
        metadata_file = self.get_metadata_filename(symbol, timeframe)
        
        existing_data = self.load_from_csv(symbol, timeframe, skip_logging=True)
        
        if existing_data is not None and len(existing_data) > 0:
            combined_df = pd.concat([existing_data, df])
        else:
            combined_df = df
        
        # [핵심] 저장하기 전에 검증 및 수정 함수 호출
        clean_df = self._validate_and_remediate(combined_df, timeframe)
        
        if clean_df.empty:
            print(f"⚠️ No data to save for {symbol} {timeframe} after cleaning.")
            return None
        
        clean_df.to_csv(csv_file, index=False)
        
        metadata = {
            'last_updated': datetime.now().isoformat(), 'total_rows': len(clean_df),
            'date_range': {
                'start': clean_df['timestamp'].min().strftime('%Y-%m-%d %H:%M:%S'),
                'end': clean_df['timestamp'].max().strftime('%Y-%m-%d %H:%M:%S')
            },
            'symbol': symbol, 'timeframe': timeframe
        }
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"💾 Clean data saved: {csv_file} ({len(clean_df)} rows)")
        return clean_df
        
    def load_from_csv(self, symbol: str, timeframe: str, 
                     start_date: str = None, end_date: str = None, 
                     skip_logging: bool = False) -> Optional[pd.DataFrame]:
        """CSV에서 특정 기간 데이터 로드"""
        csv_file = self.get_csv_filename(symbol, timeframe)
        
        if not os.path.exists(csv_file):
            if not skip_logging:
                print(f"   [Data] ⚠️ {csv_file} not found.")
            return None
        
        try:
            df = pd.read_csv(csv_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if start_date: df = df[df['timestamp'] >= pd.to_datetime(start_date)]
            if end_date: df = df[df['timestamp'] <= pd.to_datetime(end_date)]
            df = df.sort_values('timestamp').reset_index(drop=True)
            if not skip_logging and not df.empty:
                print(f"📂 {symbol} {timeframe} data loaded: {len(df)} rows")
            return df
        except Exception as e:
            if not skip_logging: print(f"❌ Data loading failed {csv_file}: {e}")
            return None
    
    def get_missing_data_periods(self, symbol: str, timeframe: str, 
                                target_end_date: str = None) -> List[Tuple[str, str]]:
        """누락된 데이터 기간 찾기"""
        if target_end_date is None: target_end_date = datetime.now().strftime('%Y-%m-%d')
        existing_data = self.load_from_csv(symbol, timeframe, skip_logging=True)
        if existing_data is None or existing_data.empty:
            return [('2020-01-01', target_end_date)]
        
        last_timestamp = existing_data['timestamp'].max()
        target_end_dt = pd.to_datetime(target_end_date)
        if last_timestamp >= target_end_dt: return []
        
        time_delta = pd.to_timedelta(self.TIMEFRAME_MAP_PANDAS.get(timeframe, '1T'))
        missing_start = (last_timestamp + time_delta).strftime('%Y-%m-%d %H:%M:%S')
        missing_end = target_end_dt.strftime('%Y-%m-%d %H:%M:%S')
        return [(missing_start, missing_end)]
    
    def incremental_update(self, symbol: str, timeframe: str, 
                          target_end_date: str = None) -> pd.DataFrame:
        """증분 업데이트"""
        if target_end_date is None: target_end_date = datetime.now().strftime('%Y-%m-%d')
        print(f"🔄 {symbol} {timeframe} incremental update started...")
        missing_periods = self.get_missing_data_periods(symbol, timeframe, target_end_date)
        
        if not missing_periods:
            print(f"✅ {symbol} {timeframe} data is already up-to-date.")
            return self.load_from_csv(symbol, timeframe)
        
        all_new_data = []
        for start_date, end_date in missing_periods:
            print(f"📥 Fetching {symbol} {timeframe}: {start_date} to {end_date}")
            new_data = self.fetch_historical_data(symbol, timeframe, start_date, end_date)
            if new_data is not None and len(new_data) > 0:
                all_new_data.append(new_data)
        
        if all_new_data:
            combined_new_data = pd.concat(all_new_data, ignore_index=True)
            # save_to_csv가 병합, 검증, 수정을 모두 처리
            updated_data = self.save_to_csv(combined_new_data, symbol, timeframe)
            print(f"✅ {symbol} {timeframe} update complete.")
            return updated_data
        else:
            print(f"⚠️ {symbol} {timeframe} no new data found.")
            return self.load_from_csv(symbol, timeframe)
    
    def fetch_historical_data(self, symbol: str, timeframe: str, 
                            start_date: str, end_date: str, 
                            source: str = 'binance') -> Optional[pd.DataFrame]:
        """API를 통해 데이터 수집"""
        try:
            if source == 'binance':
                return self._fetch_from_binance(symbol, timeframe, start_date, end_date)
            else: raise ValueError(f"Unsupported data source: {source}")
        except Exception as e:
            print(f"Data fetch failed {symbol}-{timeframe}: {e}")
            return None
    
    def _fetch_from_binance(self, symbol: str, timeframe: str, 
                        start_date: str, end_date: str) -> pd.DataFrame:
        """Binance API에서 데이터 수집"""
        try:
            client = Client()
            binance_symbol = symbol.replace('_UMCBL', '')
            binance_timeframe = self.TIMEFRAME_MAP_BINANCE.get(timeframe)
            if binance_timeframe is None: raise ValueError(f"Invalid timeframe: {timeframe}")

            klines = client.get_historical_klines(binance_symbol, binance_timeframe, start_date, end_date)
            if not klines: return pd.DataFrame()
            
            columns = [
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base_volume', 
                'taker_buy_quote_volume', 'ignore'
            ]
            df = pd.DataFrame(klines, columns=columns)
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_columns] = df[numeric_columns].astype(float)
            # Naive Timestamp (UTC 기준)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            return df.sort_values('timestamp').reset_index(drop=True)
        except Exception as e:
            print(f"❌ Binance fetch error: {e}")
            return pd.DataFrame()

    def safe_data_load(self, symbol: str, timeframe: str, 
                       start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """
        [V4.6] 데이터를 안전하게 로드합니다.
        CSV 로드 또는 API 증분 업데이트만 수행합니다. (변환 로직 제거)
        """
        try:
            df = self.load_from_csv(symbol, timeframe, start_date, end_date)
            
            if df is not None and not df.empty:
                # 데이터가 최신인지 간단히 확인
                if end_date and df['timestamp'].max() < (pd.to_datetime(end_date) - pd.Timedelta(days=1)):
                     print(f"   [Data] {symbol} {timeframe} is outdated. Running update...")
                     return self.incremental_update(symbol, timeframe, end_date)
                else:
                    return df # 데이터가 존재하고 최신임
            
            # 데이터가 없는 경우, 증분 업데이트(전체 다운로드) 시도
            print(f"🔄 {symbol} {timeframe} data not found. Fetching from API...")
            return self.incremental_update(symbol, timeframe, end_date)

        except Exception as e:
            print(f"❌ Data loading failed {symbol}-{timeframe}: {e}")
            return None
