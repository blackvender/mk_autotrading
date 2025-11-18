import pandas as pd
import mplfinance as mpf
from utils.indicators import TechnicalIndicators
from data.data_manager import AdvancedDataManager
import os

# 0. 저장할 디렉토리 확인
output_dir = 'wedge_patterns_all'
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# 1. 데이터 로드
data_manager = AdvancedDataManager()
df = data_manager.safe_data_load('BTCUSDT', '4h', '2022-10-01', '2022-12-31')

if df is None or df.empty:
    print('Error: Could not load 4h data for BTCUSDT.')
    exit()

# 2. 추세선 탐지
support_trendlines, resistance_trendlines = TechnicalIndicators.find_trendlines(df, order=5, min_length=12)

# 3. 쐐기형 패턴 탐지
current_idx = len(df) - 1
wedge_patterns = TechnicalIndicators.find_wedge_patterns(df, support_trendlines, resistance_trendlines, current_idx)

print(f"Found {len(wedge_patterns)} wedge patterns. Saving all to '{output_dir}' directory...")

# 4. 모든 패턴을 반복하며 차트 저장
if wedge_patterns:
    # 터치 수 기준으로 정렬하여 더 의미있는 패턴부터 확인
    sorted_patterns = sorted(wedge_patterns, key=lambda p: p['resistance_line']['touches'] + p['support_line']['touches'], reverse=True)
    
    # df의 인덱스를 DatetimeIndex로 설정 (mplfinance 요구사항)
    df = df.set_index('timestamp')
    
    # 시간 간격 계산 (미래 시간 계산용)
    time_interval = df.index[1] - df.index[0] if len(df) > 1 else pd.Timedelta(hours=4) # 기본 4시간봉

    # 모든 패턴의 최대 apex_idx를 찾아 df 확장 범위 결정
    max_apex_idx = 0
    for pattern in sorted_patterns:
        if pattern['apex_point'][0] > max_apex_idx:
            max_apex_idx = pattern['apex_point'][0]
    
    # [수정] df를 max_apex_idx까지 확장
    # 확장된 인덱스의 마지막 타임스탬프 계산
    last_original_timestamp = df.index[-1]
    if max_apex_idx >= len(df):
        max_extended_timestamp = last_original_timestamp + time_interval * (max_apex_idx - (len(df) - 1))
    else:
        max_extended_timestamp = last_original_timestamp # max_apex_idx가 원본 df 범위 내에 있으면 확장 불필요

    extended_index = pd.date_range(start=df.index[0], end=max_extended_timestamp, freq=time_interval)
    df_extended = df.reindex(extended_index)
    
    # mplfinance는 volume 컬럼이 필요하므로 NaN으로 채워줌
    if 'volume' not in df_extended.columns:
        df_extended['volume'] = 0.0
    df_extended['volume'] = df_extended['volume'].fillna(0.0)


    for i, pattern in enumerate(sorted_patterns):
        
        apex_idx_val = pattern['apex_point'][0]
        apex_price_val = pattern['apex_point'][1]
        pattern_type = pattern['pattern_type']
        print(f"Pattern {i+1}: Type={pattern_type}, Apex(x={apex_idx_val:.0f}, y={apex_price_val:.2f})")

        r_tl = pattern['resistance_line']
        s_tl = pattern['support_line']
        
        r_slope = r_tl['slope']
        s_slope = s_tl['slope']
        
        r_intercept = r_tl['points'][0][1] - r_slope * r_tl['points'][0][0]
        s_intercept = s_tl['points'][0][1] - s_slope * s_tl['points'][0][0]

        pattern_start_idx = pattern['start_index']
        
        # [수정] apex_timestamp를 df_extended.index에서 직접 가져옴
        # apex_idx_val이 df_extended의 유효한 인덱스 범위 내에 있다고 가정
        apex_timestamp = df_extended.index[int(apex_idx_val)]


        res_start_price = r_slope * pattern_start_idx + r_intercept
        res_end_price = r_slope * apex_idx_val + r_intercept
        
        sup_start_price = s_slope * pattern_start_idx + s_intercept
        sup_end_price = s_slope * apex_idx_val + s_intercept

        alines = [
            [(df.index[pattern_start_idx], res_start_price), (apex_timestamp, res_end_price)],
            [(df.index[pattern_start_idx], sup_start_price), (apex_timestamp, sup_end_price)]
        ]
        
        chart_title = f"Wedge {i+1}: {pattern['pattern_type']} (Touches: {r_tl['touches'] + s_tl['touches']})"
        save_path = os.path.join(output_dir, f'wedge_pattern_{i+1}.png')
        
        mpf.plot(df_extended, # 확장된 df 사용
                 type='candle', style='yahoo',
                 alines=dict(alines=alines, colors=['r', 'g']),
                 title=chart_title,
                 volume=True,
                 savefig=save_path)

    print(f"\nSuccessfully saved {len(sorted_patterns)} charts to '{output_dir}'.")

else:
    print("\nNo wedge patterns found in this period.")
