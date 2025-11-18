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
support_trendlines, resistance_trendlines = TechnicalIndicators.find_trendlines(df, order=5, min_length=30)

# 3. 삼각 수렴 패턴 탐지 (현재 인덱스를 데이터의 마지막으로 가정)
current_idx = len(df) - 1
triangle_patterns = TechnicalIndicators.find_triangle_patterns(support_trendlines, resistance_trendlines, current_idx)

print(f"Found {len(triangle_patterns)} triangle patterns.")

# 4. 결과 출력 및 시각화
if triangle_patterns:
    # 가장 최근에 시작된 패턴을 기준으로 정렬
    latest_pattern = sorted(triangle_patterns, key=lambda x: x['start_index'], reverse=True)[0]
    
    print("\n--- Latest Triangle Pattern Found ---")
    print(f"Type: {latest_pattern['pattern_type']}")
    print(f"Starts at index: {latest_pattern['start_index']}")
    print(f"Apex Point (index, price): ({latest_pattern['apex_point'][0]:.0f}, {latest_pattern['apex_point'][1]:.2f})")

    # 5. 플로팅
    df = df.set_index('timestamp')
    
    # 패턴을 형성하는 추세선
    res_line = latest_pattern['resistance_line']
    sup_line = latest_pattern['support_line']
    
    alines = [
        [(df.index[res_line[0][0]], res_line[0][1]), (df.index[res_line[1][0]], res_line[1][1])],
        [(df.index[sup_line[0][0]], sup_line[0][1]), (df.index[sup_line[1][0]], sup_line[1][1])]
    ]
    
    # 꼭짓점 표시
    apex_time = df.index[int(latest_pattern['apex_point'][0])] if latest_pattern['apex_point'][0] < len(df) else df.index[-1] + pd.Timedelta(days=(latest_pattern['apex_point'][0] - len(df)))
    
    mpf.plot(df,
             type='candle', style='yahoo',
             alines=dict(alines=alines, colors=['r', 'g']),
             title=f"Latest Pattern: {latest_pattern['pattern_type']}",
             volume=True,
             vlines=[apex_time], # 꼭짓점 수직선 표시
             savefig='triangle_pattern_test.png')
             
    print("\nChart for the latest pattern saved to triangle_pattern_test.png")

else:
    print("\nNo triangle patterns found.")
