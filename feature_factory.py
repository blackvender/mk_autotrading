import pandas as pd
import numpy as np
import ta
from typing import Dict, List, Optional
from data.data_manager import AdvancedDataManager
from utils.indicators import TechnicalIndicators
from utils.data_converter import DataConverter
from sklearn.cluster import DBSCAN # [신규] S/R 클러스터링을 위해 추가

class FeatureFactory:
    """
    [V4.7 리팩토링]
    'requirements' 딕셔너리를 기반으로 필요한 지표만 동적으로 계산합니다.
    더 이상 특정 전략('DynamicVolatilityStrategy')에 종속되지 않습니다.
    """
    
    def __init__(self, data_manager: AdvancedDataManager):
        self.dm = data_manager
        self.ti = TechnicalIndicators
        self.dc = DataConverter()
        
        # [V4.7 신규] '어떻게' 지표를 계산하는지 정의하는 레지스트리
        # 'regime'과 같은 특수 지표는 별도 처리
        self.feature_calculators = {
            # '요청 이름': (계산 함수, {파라미터})
            'rsi': (self.ti.rsi, {'period': 14}),
            'atr': (self.ti.atr, {'period': 14}),
            'atr_ma_20': (lambda df, p=14: self.ti.atr(df, p).rolling(20, min_periods=1).mean(), {}),
            'volume_avg_20': (self.ti.volume_avg, {'period': 20}),
            'volume_ma_20': (self.ti.volume_avg, {'period': 20}), # Alias
            'bb_upper': (lambda df, p=20: self.ti.bollinger_bands(df, p)['bb_upper'], {}),
            'ema_20': (lambda df, p=20: self.ti.ema(df, p), {}),
            'ema_14': (lambda df, p=14: self.ti.ema(df, p), {}),
            'ema_50': (lambda df, p=50: self.ti.ema(df, p), {}),
        }
        print("✅ Dynamic FeatureFactory v4.7 Initialized (Requirements-Based).")

    def create_featured_dataframe(self, symbol: str, start_date: str, end_date: str, 
                                main_tf: str = '5m', 
                                requirements: Dict[str, List[str]] = {}) -> pd.DataFrame:
        """
        [V4.7 수정]
        전략의 'requirements'를 인자로 받아 동적으로 지표를 생성합니다.
        
        [v2.0 수정]
        - S/R Zone 계산을 레짐 계산 *앞으로* 이동 (S/R 압력 점수 계산을 위해)
        - _calculate_regime_1d (v0.1) 대신 _calculate_regime_v2_final (v2.0) 호출
        - v2.0의 5개 신규 컬럼(4점수 + 1라벨)을 병합 로직에 추가
        """
        
        # 1. Golden Source (5m) 로드 (V4.6과 동일)
        print(f"   [FF] Loading Golden Source data ({main_tf})...")
        df_main = self.dm.safe_data_load(symbol, main_tf, start_date, end_date)
        if df_main is None or df_main.empty:
            raise ValueError(f"Golden Source data ({main_tf}) could not be loaded.")

        # 2. 상위 타임프레임 생성 (V4.6과 동일)
        print("   [FF] Generating higher timeframes...")
        dfs = {
            main_tf: df_main,
            '15m': self.dc.resample_to_15m(df_main),
            '1h': self.dc.resample_to_1h(df_main),
        }
        dfs['4h'] = self.dc.resample_to_4h(dfs['1h'])
        dfs['1d'] = self.dc.resample_to_1d(dfs['4h'])

        # --- [Phase 3.2.1 수정] ---
        # 1D POC 계산
        if 'poc' in requirements.get('1d', []):
            poc_1d_series = self._calculate_daily_poc(
                dfs[main_tf], dfs['1d']['timestamp'], symbol
            )
            dfs['1d']['poc_1d'] = poc_1d_series 
            
        # 1D 극값 계산 (S/R Zone 계산의 입력값으로 사용)
        support_raw, resistance_raw = self.ti.find_local_extrema(dfs['1d'], order=10)
        dfs['1d']['support_levels_raw'] = support_raw
        dfs['1d']['resistance_levels_raw'] = resistance_raw
        
        # --- [v2.0 수정] ---
        # 1D S/R Zone 및 Score 계산 (v1.0)
        # v2.0 레짐 엔진이 S/R 압력 점수를 사용하므로, 레짐 계산보다 *먼저* 실행되어야 함.
        print("   [FF] Calculating S/R Zones (v1.0.6) for Regime Engine...")
        dfs['1d'] = self._calculate_sr_zones(dfs['1d'], symbol, poc_col_name='poc_1d')

        # [v2.0 수정 / 버그 #1] v0.1의 'regime' 대신 v2.0의 'regime_label_1d'로 트리거 변경
        if 'regime_label_1d' in requirements.get('1d', []):
            print("   [FF] Calculating Regime v2.0 Final Engine...")
            # dfs['1d'] = self._calculate_regime_1d(dfs['1d']) # [v2.0] 폐기
            dfs['1d'] = self._calculate_regime_v2_final(dfs) # [v2.0] 새 함수 호출
        # --- [v2.0 수정 완료] ---

        print("   [FF] Calculating features based on strategy requirements...")
        
        # 3. [V4.7 수정] 동적 지표 계산
        merged_df = dfs[main_tf].copy()
        
        # 3a. Base(main_tf) 지표 계산
        base_features = requirements.get('base', [])
        if base_features:
            merged_df = self._calculate_features(merged_df, base_features, "")

        # 3b. 상위 TF 지표 계산 및 병합
        for tf in ['15m', '1h', '4h', '1d']:
            features = requirements.get(tf, [])
            if not features or dfs[tf] is None or dfs[tf].empty:
                continue
            
            df_higher = dfs[tf].copy()
            suffix = f"_{tf}"
            
            # --- [수정] 'poc', 'regime', 'sr_zone' 관련 지표는 이미 계산했으므로 건너뛰기 ---
            special_features = ['regime', 'poc', 'support_1d', 'resistance_1d', 
                                'support_score_1d', 'resistance_score_1d']
            
            # [v2.0] 5개 신규 컬럼도 건너뛰기 목록에 추가
            special_features.extend([
                'regime_trend_score', 'regime_energy_score', 
                'regime_reversion_score', 'regime_sr_pressure_score', 
                'regime_label_1d'
            ])
            
            features_to_calculate = [f for f in features if f not in special_features]

            # 레지스트리 기반 공통 지표 계산
            df_higher_featured = self._calculate_features(df_higher, features_to_calculate, suffix)
            
            # --- [v2.0 수정] 병합할 컬럼 리스트 생성  ---
            valid_features = [c for c in df_higher_featured.columns if c.endswith(suffix)]
            
            if tf == '1d':
                # (기존) poc_1d 추가
                if 'poc_1d' in df_higher.columns: valid_features.append('poc_1d')
                
                # S/R Zone 관련 컬럼 추가 (기존과 동일)
                sr_cols_to_add = ['support_1d', 'resistance_1d', 'support_score_1d', 'resistance_score_1d']
                for col in sr_cols_to_add:
                    if col in df_higher_featured.columns:
                        valid_features.append(col)

                # [v2.0 신규] 레짐 점수 및 라벨 컬럼 추가
                # 'regime_1d'는 'regime_label_1d'로 대체됨
                regime_v2_cols = [
                    'regime_trend_score', 'regime_energy_score', 
                    'regime_reversion_score', 'regime_sr_pressure_score', 
                    'regime_label_1d'
                ]
                for col in regime_v2_cols:
                    if col in df_higher_featured.columns:
                        valid_features.append(col)
            # --- [v2.0 수정 완료] ---

            if not valid_features: continue
                
            # 'timestamp' 컬럼이 df_higher_featured에 있는지 확인
            if 'timestamp' not in df_higher_featured.columns:
                df_higher_featured['timestamp'] = df_higher_featured.index
                
            # 병합 대상 컬럼만 추출하여 정렬
            merge_subset = df_higher_featured[['timestamp'] + valid_features].sort_values('timestamp')

            merged_df = pd.merge_asof(
                merged_df.sort_values('timestamp'),
                merge_subset,
                on='timestamp',
                direction='backward'
            )
        
        merged_df = merged_df.ffill().dropna()
        print("   [FF] Feature merging complete.")
        return merged_df.reset_index(drop=True)

    def _calculate_features(self, df: pd.DataFrame, features: List[str], suffix: str) -> pd.DataFrame:
        """[V4.7 신규] 레지스트리를 사용해 요청된 지표를 동적으로 계산"""
        for feat_name in features:
            if feat_name == 'regime': continue # 'regime'은 특수 처리
            
            calculator_tuple = self.feature_calculators.get(feat_name)
            if calculator_tuple:
                try:
                    calculator_func, params = calculator_tuple
                    df[f"{feat_name}{suffix}"] = calculator_func(df, **params)
                except Exception as e:
                    print(f"   [FF] ⚠️ Error calculating feature '{feat_name}{suffix}': {e}")
            else:
                print(f"   [FF] ⚠️ Unknown feature requested: '{feat_name}'")
        return df

    def _calculate_regime_1d(self, df: pd.DataFrame) -> pd.DataFrame:
        """[V4.7] 1일봉 레짐 계산 (V4.6 팩토리에서 가져옴) - [v2.0] 이 함수는 더 이상 사용되지 않음 (Deprecated)"""
        try:
            atr = self.ti.atr(df, 14)
            ema_14 = self.ti.ema(df, 14)
            if atr.isnull().all() or ema_14.isnull().all():
                raise ValueError("ATR or EMA14 calculation failed for 1d regime")

            high_14 = df['high'].rolling(14, min_periods=1).max()
            low_14 = df['low'].rolling(14, min_periods=1).min()
            mid_value = (high_14 + low_14) / 2
            vol_ratio = atr / df['close']
            
            threshold_coefficient = np.where(vol_ratio > 0.03, 1.3, np.where(vol_ratio < 0.01, 0.7, 1.0))
            up_band_width = (high_14 - mid_value) * threshold_coefficient
            down_band_width = (mid_value - low_14) * threshold_coefficient
            
            conditions = [
                (df['close'] > ema_14) & (df['close'] > (mid_value + up_band_width * 0.3)),
                (df['close'] > ema_14) & (df['close'] > mid_value),
                (df['close'] > ema_14),
                (df['close'] <= ema_14) & (df['close'] < (mid_value - down_band_width * 0.3)),
                (df['close'] <= ema_14) & (df['close'] < mid_value),
            ]
            choices = ["상승_강세", "상승_약세", "상승_횡보", "하락_강세", "하락_약세"]
            df['regime_1d'] = np.select(conditions, choices, default="하락_횡보")
        except Exception as e:
            print(f"   [FF] ⚠️ Error calculating 'regime_1d': {e}. Defaulting to '상승_횡보'.")
            df['regime_1d'] = "상승_횡보" # Fallback
        return df

    @staticmethod
    def _calculate_daily_poc(df_5m: pd.DataFrame, df_1d_timestamps: pd.Series, 
                           symbol: str) -> pd.Series:
        """
        [v1.0] 5m 데이터를 기반으로 일일 POC(Point of Control)를 계산합니다.
        """
        print("   [FF] Calculating 1D Point of Control (POC) from 5m data...")
        if df_5m.empty or 'close' not in df_5m or 'volume' not in df_5m:
            return pd.Series(index=df_1d_timestamps.index, dtype=float)

        df_5m_copy = df_5m.copy()
        
        # 1. 가격을 'bin'으로 그룹화 (정밀도 설정)
        price_precision = 0 # 기본값 (예: $1 단위)
        if 'BTC' in symbol:
            price_precision = 0 # BTC: $1 단위 (예: 68500.7 -> 68501)
        elif 'ETH' in symbol:
            price_precision = 1 # ETH: $0.1 단위 (예: 3450.78 -> 3450.8)
        
        df_5m_copy['price_bin'] = df_5m_copy['close'].round(price_precision)
        
        # 2. 5m 데이터를 날짜(D)와 가격(bin)으로 그룹화하여 거래량 합산
        volume_by_day_price = df_5m_copy.groupby(
            [pd.Grouper(key='timestamp', freq='1D'), 'price_bin']
        )['volume'].sum().reset_index()

        # 3. 각 날짜(timestamp)별로 거래량이 가장 많은(idxmax) 가격(price_bin)을 찾음
        poc_series_indices = volume_by_day_price.groupby(
            pd.Grouper(key='timestamp', freq='1D')
        )['volume'].idxmax()
        poc_series = volume_by_day_price.loc[poc_series_indices]

        # 4. 1D DataFrame과 병합할 수 있도록 준비
        poc_series = poc_series.set_index('timestamp')['price_bin']
        
        # 5. df_1d의 타임스탬프에 맞게 리인덱싱 및 ffill (휴일 등 데이터 없는 날 보정)
        poc_series_aligned = poc_series.reindex(df_1d_timestamps, method='ffill')
        
        return poc_series_aligned.values # 원본 1D DataFrame과 동일한 순서의 값 반환


    # --- [Phase 3.2.1 체크리스트 4: v1.0.6 (스냅 반경 분리)] ---
    @staticmethod
    def _calculate_sr_zones(df_1d: pd.DataFrame, symbol: str, 
                            poc_col_name: str = 'poc_1d') -> pd.DataFrame:
        """
        [v1.0.6] S/R 후보를 클러스터링하고 우선순위 스냅 및 점수화를 적용합니다.
        """
        print("   [FF] Clustering S/R levels and calculating scores (v1.0.6)...")
        
        # 0a. 컬럼 미리 생성 (KeyError 방지)
        df_1d['support_1d'] = np.nan
        df_1d['support_score_1d'] = 0.0
        df_1d['resistance_1d'] = np.nan
        df_1d['resistance_score_1d'] = 0.0
        
        # 0b. 반경(Radius) 설정
        avg_price = df_1d['close'].mean()
        relative_eps = 0.005 # 0.5% (클러스터링용)
        
        if 'BTC' in symbol: relative_eps = 0.005
        elif 'ETH' in symbol: relative_eps = 0.01
            
        eps = avg_price * relative_eps # 클러스터링(DBSCAN) 반경
        
        snap_radius_multiplier = 2
        snap_radius = eps * snap_radius_multiplier 

        if eps == 0 or np.isnan(eps): 
            eps = avg_price * 0.005 if not np.isnan(avg_price) else 100 # Fallback
            snap_radius = eps * snap_radius_multiplier

        # 1. 모든 S/R 후보 포인트 수집
        supports = df_1d['support_levels_raw'].dropna().values.reshape(-1, 1)
        resistances = df_1d['resistance_levels_raw'].dropna().values.reshape(-1, 1)
        if poc_col_name in df_1d.columns:
            pocs = df_1d[poc_col_name].dropna().values.reshape(-1, 1)
        else:
            pocs = np.array([]).reshape(-1, 1)

        support_zones = []
        resistance_zones = []

        # 2. 지지(Support) 클러스터링 및 점수화
        if len(supports) > 1:
            db_supports = DBSCAN(eps=eps, min_samples=2).fit(supports) # 클러스터링은 eps 사용
            support_data = pd.DataFrame({'level': supports.flatten(), 'cluster_id': db_supports.labels_})
            
            for cluster_id in np.unique(db_supports.labels_):
                if cluster_id == -1: continue 
                
                zone_points_levels = support_data[support_data['cluster_id'] == cluster_id]['level'].values
                zone_center_raw = zone_points_levels.mean()
                score = len(zone_points_levels) 
                
                poc_nearby = pocs[(pocs > (zone_center_raw - eps)) & (pocs < (zone_center_raw + eps))]
                score += len(poc_nearby) * 10 
                
                final_zone_level = zone_center_raw
                snapped = False
                psych_levels_dict = TechnicalIndicators.find_psychological_levels(zone_center_raw, symbol)
                
                for p_lvl in psych_levels_dict.get('major', []):
                    if abs(zone_center_raw - p_lvl) < (snap_radius * 2.0): 
                        final_zone_level = p_lvl 
                        score += 10 
                        snapped = True
                        break
                if not snapped:
                    for p_lvl in psych_levels_dict.get('medium', []):
                        if abs(zone_center_raw - p_lvl) < snap_radius:
                            final_zone_level = p_lvl
                            score += 5
                            snapped = True
                            break
                if not snapped:
                    for p_lvl in psych_levels_dict.get('minor', []):
                        if abs(zone_center_raw - p_lvl) < snap_radius:
                            final_zone_level = p_lvl
                            score += 2
                            snapped = True
                            break 

                support_zones.append({'level': final_zone_level, 'score': score})
        
        # 3. 저항(Resistance) 클러스터링 및 점수화 (동일한 스냅 로직 적용)
        if len(resistances) > 1:
            db_resistances = DBSCAN(eps=eps, min_samples=2).fit(resistances)
            resistance_data = pd.DataFrame({'level': resistances.flatten(), 'cluster_id': db_resistances.labels_})
            
            for cluster_id in np.unique(db_resistances.labels_):
                if cluster_id == -1: continue
                
                zone_points_levels = resistance_data[resistance_data['cluster_id'] == cluster_id]['level'].values
                zone_center_raw = zone_points_levels.mean()
                score = len(zone_points_levels)
                
                poc_nearby = pocs[(pocs > (zone_center_raw - eps)) & (pocs < (zone_center_raw + eps))]
                score += len(poc_nearby) * 10
                
                final_zone_level = zone_center_raw
                snapped = False
                psych_levels_dict = TechnicalIndicators.find_psychological_levels(zone_center_raw, symbol)
                
                for p_lvl in psych_levels_dict.get('major', []):
                    if abs(zone_center_raw - p_lvl) < (snap_radius * 2.0):
                        final_zone_level = p_lvl
                        score += 10
                        snapped = True
                        break
                if not snapped:
                    for p_lvl in psych_levels_dict.get('medium', []):
                        if abs(zone_center_raw - p_lvl) < snap_radius:
                            final_zone_level = p_lvl
                            score += 5
                            snapped = True
                            break
                if not snapped:
                    for p_lvl in psych_levels_dict.get('minor', []):
                        if abs(zone_center_raw - p_lvl) < snap_radius:
                            final_zone_level = p_lvl
                            score += 2
                            snapped = True
                            break
                
                resistance_zones.append({'level': final_zone_level, 'score': score})
        
        # 4. 각 캔들(행)에 가장 가까운 지지/저항 및 점수 할당
        def find_nearest_sr(row, zones, zone_type):
            price = row['close']
            nearest_level = np.nan
            nearest_score = 0
            
            if zone_type == 'support':
                relevant_zones = [z for z in zones if z['level'] < price]
                if relevant_zones:
                    nearest = min(relevant_zones, key=lambda z: abs(z['level'] - price))
                    nearest_level = nearest['level']
                    nearest_score = nearest['score']
            elif zone_type == 'resistance':
                relevant_zones = [z for z in zones if z['level'] > price]
                if relevant_zones:
                    nearest = min(relevant_zones, key=lambda z: abs(z['level'] - price))
                    nearest_level = nearest['level']
                    nearest_score = nearest['score']
                    
            return pd.Series([nearest_level, nearest_score])

        if support_zones:
            sr_results = df_1d.apply(find_nearest_sr, axis=1, zones=support_zones, zone_type='support')
            df_1d[['support_1d', 'support_score_1d']] = sr_results

        if resistance_zones:
            sr_results = df_1d.apply(find_nearest_sr, axis=1, zones=resistance_zones, zone_type='resistance')
            df_1d[['resistance_1d', 'resistance_score_1d']] = sr_results

        # 원본 임시 컬럼들 정리
        df_1d = df_1d.drop(columns=['support_levels_raw', 'resistance_levels_raw'], errors='ignore')
        
        return df_1d
    
    # --- [Phase 3.2.3 v2.0 최종안: 신규 추가] ---

    @staticmethod
    def _normalize_series(series: pd.Series, lookback: int = 50) -> pd.Series:
        """[v2.0 Helper] 시리즈를 과거 N일 기준으로 -1.0 ~ +1.0 사이로 정규화 (Z-score 기반)"""
        mean = series.rolling(lookback).mean()
        std = series.rolling(lookback).std()
        
        # Z-score 계산 (표준편차의 2배를 벗어나면 1 또는 -1)
        z_score = (series - mean) / (std * 2 + 1e-10) 
        
        # -1.0과 1.0 사이로 클리핑
        return z_score.clip(-1.0, 1.0).fillna(0.0)

    def _calculate_regime_v2_final(self, dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        [v2.0 Final] 4대 핵심 점수와 8-레짐 라벨을 계산하는 하이브리드 엔진.
        [Checklist 2, 3, 4]를 구현합니다.
        
        이 함수는 _calculate_sr_zones가 실행된 *이후*에 호출되어야 합니다.
        """
        print("   [FF] Calculating Regime v2.0 Final (4 Scores + 1 Label)...")
        
        if '1d' not in dfs or '4h' not in dfs:
            print("   [FF] ⚠️ v2.0 Regime: 1D or 4H data is missing.")
            return dfs.get('1d', pd.DataFrame())

        df_1d = dfs['1d'].copy()
        df_4h = dfs['4h'].copy()

        # --- 0. 재료 준비: 각 TF별 핵심 지표 계산 ---
        # 1D 지표
        hma_1d = self.ti.calculate_hma(df_1d, 16)
        fe_1d = self.ti.calculate_fractal_efficiency(df_1d, 20)
        smi_1d = self.ti.calculate_smi(df_1d, 13, 25, 9)
        squeeze_1d = self.ti.is_volatility_squeeze(df_1d, 20)
        atr_ratio_1d = (self.ti.atr(df_1d, 14) / df_1d['close']).fillna(0)

        # 4H 지표 (1D와 병합 필요)
        hma_4h = self.ti.calculate_hma(df_4h, 16)
        smi_4h = self.ti.calculate_smi(df_4h, 13, 25, 9)
        
        # --- 1. 4H 지표를 1D로 병합 ---
        df_4h_for_merge = pd.DataFrame({
            'timestamp': df_4h['timestamp'],
            'hma_4h': hma_4h,
            'smi_4h': smi_4h
        }).sort_values('timestamp')

        merged = pd.merge_asof(
            df_1d.sort_values('timestamp'),
            df_4h_for_merge,
            on='timestamp',
            direction='backward'
        )
        merged.set_index(df_1d.index, inplace=True)
        df_1d = merged.copy() 

        # --- 2. [Checklist 3] 4대 핵심 점수 계산 ---

        # (A) regime_trend_score (추세 점수)
        hma_1d_slope = np.sign(hma_1d.diff().fillna(0))
        hma_4h_slope = np.sign(df_1d['hma_4h'].diff().fillna(0))
        # (가중치: HMA 4H=40%, HMA 1D=30%, FE 1D=30%)
        df_1d['regime_trend_score'] = (
            (hma_4h_slope * 0.4) +
            (hma_1d_slope * 0.3) +
            (fe_1d * 0.3)
        ).fillna(0.0)

        # (B) regime_energy_score (에너지 점수)
        # 0.0 (축적) ~ 1.0 (방출)
        atr_norm = (atr_ratio_1d - atr_ratio_1d.rolling(50).min()) / \
                   (atr_ratio_1d.rolling(50).max() - atr_ratio_1d.rolling(50).min() + 1e-10)
        atr_norm = atr_norm.clip(0, 1).fillna(0.5)
        df_1d['regime_energy_score'] = np.where(squeeze_1d, 0.0, atr_norm)

        # (C) regime_reversion_score (과열 점수)
        # -1.0 (과매도) ~ +1.0 (과매수)
        smi_1d_norm = self._normalize_series(smi_1d)
        smi_4h_norm = self._normalize_series(df_1d['smi_4h'])
        # (가중치: 1D=50%, 4H=50%)
        df_1d['regime_reversion_score'] = (
            (smi_1d_norm * 0.5) + (smi_4h_norm * 0.5)
        ).clip(-1.0, 1.0).fillna(0.0)

        # (D) regime_sr_pressure_score (S/R 압력 점수)
        # +1.0 (지지 압력) ~ -1.0 (저항 압력)
        support = df_1d['support_1d']
        resistance = df_1d['resistance_1d']
        price = df_1d['close']
        
        total_range = (resistance - support) + 1e-10
        price_pos_norm = (price - support) / total_range # 0 (지지) ~ 1 (저항)
        
        # 0~1 범위를 -1~+1 범위로 변환 (지지=+1, 저항=-1)
        pressure_score = (1 - (price_pos_norm * 2)).clip(-1.0, 1.0)
        
        df_1d['regime_sr_pressure_score'] = pressure_score.fillna(0.0)

        # --- 3. [Checklist 4] 점수 -> 라벨 변환 ---
        s_trend = df_1d['regime_trend_score']
        s_energy = df_1d['regime_energy_score']
        s_reversion = df_1d['regime_reversion_score']
        # s_pressure = df_1d['regime_sr_pressure_score'] # 라벨링에는 우선 미사용

        conditions = [
            # Impulse (강한 방출)
            (s_trend > 0.5) & (s_energy > 0.7),                      # Uptrend-Impulse
            (s_trend < -0.5) & (s_energy > 0.7),                     # Downtrend-Impulse
            
            # Normal (안정적 추세)
            (s_trend > 0.2) & (s_energy.between(0.3, 0.7)),         # Uptrend-Normal
            (s_trend < -0.2) & (s_energy.between(0.3, 0.7)),        # Downtrend-Normal
            
            # Consolidation (축적/횡보)
            (s_trend.between(-0.2, 0.2)) & (s_energy < 0.3),        # Full-Consolidation
            (s_trend > 0.1) & (s_energy < 0.3),                      # Uptrend-Consolidation
            (s_trend < -0.1) & (s_energy < 0.3),                     # Downtrend-Consolidation
            
            # Transition (과열/전환)
            (s_energy > 0.5) & (s_reversion.abs() > 0.8)             # Transition (과열)
        ]
        
        choices = [
            "Uptrend-Impulse", "Downtrend-Impulse",
            "Uptrend-Normal", "Downtrend-Normal",
            "Full-Consolidation", "Uptrend-Consolidation", "Downtrend-Consolidation",
            "Transition"
        ]
        
        df_1d['regime_label_1d'] = np.select(conditions, choices, default="Transition") # 기본값 Transition

        return df_1d
    # --- [v2.0 최종안 구현 완료] ---