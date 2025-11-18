import pandas as pd
import mplfinance as mpf
from utils.indicators import TechnicalIndicators
from data.data_manager import AdvancedDataManager

# 1. 데이터 로드 (기본 정수 인덱스 유지)
data_manager = AdvancedDataManager()
df = data_manager.load_from_csv('BTCUSDT', '5m', '2022-03-01', '2022-03-10')

# 2. 추세선 탐지 (정수 인덱스 기반으로 실행)
support_trendlines, resistance_trendlines = TechnicalIndicators.find_trendlines(df, order=5)

print(f"Found {len(support_trendlines)} support trendlines.")
print(f"Found {len(resistance_trendlines)} resistance trendlines.")

# 3. 플로팅을 위해 timestamp를 인덱스로 설정
df = df.set_index('timestamp')

# 4. 차트 생성 및 추세선 그리기
alines = []
try:
    for sl in support_trendlines:
        # find_trendlines는 iloc 기반 정수 인덱스를 반환함
        p1_idx = df.index[sl[0][0]]
        p2_idx = df.index[sl[1][0]]
        alines.append([(p1_idx, sl[0][1]), (p2_idx, sl[1][1])])

    for rl in resistance_trendlines:
        p1_idx = df.index[rl[0][0]]
        p2_idx = df.index[rl[1][0]]
        alines.append([(p1_idx, rl[0][1]), (p2_idx, rl[1][1])])

    mpf.plot(df, type='candle', style='yahoo',
             alines=dict(alines=alines, colors=['g' for _ in support_trendlines] + ['r' for _ in resistance_trendlines]),
             title='BTCUSDT with Trendlines',
             volume=True,
             savefig='trendline_test.png') # 파일로 저장하여 확인
    print("Chart saved to trendline_test.png")

except Exception as e:
    print(f"Error during plotting: {e}")
    if support_trendlines:
        print("Sample support trendline:", support_trendlines[0])
        print("p1 index:", support_trendlines[0][0][0], type(support_trendlines[0][0][0]))
        print("df.index type:", type(df.index))
