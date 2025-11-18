import pandas as pd
import mplfinance as mpf
from utils.indicators import TechnicalIndicators
from data.data_manager import AdvancedDataManager

# 1. 데이터 로드
data_manager = AdvancedDataManager()
df = data_manager.safe_data_load('BTCUSDT', '1d', '2021-01-01', '2022-12-31')

if df is None or df.empty:
    print("Error: Could not load 1D data for BTCUSDT.")
    exit()

# 2. 추세선 탐지
support_trendlines, resistance_trendlines = TechnicalIndicators.find_trendlines(df, order=5, min_length=5) # 플래그는 짧으므로 min_length를 줄임

# 3. 플래그 패턴 탐지
flag_patterns = TechnicalIndicators.find_flag_patterns(df, support_trendlines, resistance_trendlines, flagpole_threshold=0.2, flagpole_period=10)

print(f"Found {len(flag_patterns)} flag patterns.")

# 4. 결과 출력 및 시각화
if flag_patterns:
    # 가장 최근에 시작된 패턴을 기준으로 정렬
    latest_pattern = sorted(flag_patterns, key=lambda x: x['flagpole'][1], reverse=True)[0]
    
    print("\n--- Latest Flag Pattern Found ---")
    print(f"Type: {latest_pattern['pattern_type']}")
    print(f"Flagpole ends at index: {latest_pattern['flagpole'][1]}")

    # 5. 플로팅
    df = df.set_index('timestamp')
    
    # 패턴을 형성하는 채널
    r_tl = latest_pattern['channel'][0]
    s_tl = latest_pattern['channel'][1]
    
    res_line = r_tl['points']
    sup_line = s_tl['points']
    
    alines = [
        [(df.index[res_line[0][0]], res_line[0][1]), (df.index[res_line[1][0]], res_line[1][1])],
        [(df.index[sup_line[0][0]], sup_line[0][1]), (df.index[sup_line[1][0]], sup_line[1][1])]
    ]
    
    # 깃대 라인
    fp_start_idx = latest_pattern['flagpole'][0]
    fp_end_idx = latest_pattern['flagpole'][1]
    flagpole_line = [(df.index[fp_start_idx], df['low'].iloc[fp_start_idx]), (df.index[fp_end_idx], df['high'].iloc[fp_end_idx])]
    alines.append(flagpole_line)
    
    plot_start_idx = max(0, fp_start_idx - 10)

    mpf.plot(df.iloc[plot_start_idx:],
             type='candle', style='yahoo',
             alines=dict(alines=alines, colors=['r', 'g', 'b']),
             title=f"Latest Pattern: {latest_pattern['pattern_type']}",
             volume=True,
             savefig='flag_pattern_test.png')
             
    print("\nChart for the latest pattern saved to flag_pattern_test.png")

else:
    print("\nNo flag patterns found.")
