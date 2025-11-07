import logging
import sys
from datetime import datetime
import os
import numpy as np
from typing import List

DEFAULT_LOG_LEVEL = 'INFO'

def setup_logger(name: str, level: str = DEFAULT_LOG_LEVEL, log_file: bool = True) -> logging.Logger:
   """
   로거 설정 (파일 핸들러만 사용)
   """
   log_dir = './logs'
   os.makedirs(log_dir, exist_ok=True)
  
   logger = logging.getLogger(name)
   logger.setLevel(getattr(logging, level.upper()))
  
   # 기존 핸들러 제거 (중복 로깅 방지)
   for handler in logger.handlers[:]:
       logger.removeHandler(handler)
       handler.close()
  
   formatter = logging.Formatter(
       '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
       datefmt='%Y-%m-%d %H:%M:%S'
   )
  
   if log_file:
       log_filename = f"{log_dir}/trading_{datetime.now().strftime('%Y%m%d')}.log"
       try:
           # 파일 핸들러 (UTF-8 인코딩)
           file_handler = logging.FileHandler(log_filename, mode='a', encoding='utf-8')
           file_handler.setFormatter(formatter)
           logger.addHandler(file_handler)
       except Exception as e:
           # 파일 로깅 실패 시 콘솔로 대체
           print(f"Error setting up file logger: {e}")
           temp_console_handler = logging.StreamHandler(sys.stdout)
           temp_console_handler.setFormatter(formatter)
           logger.addHandler(temp_console_handler)
           logger.error("File logging failed. Logging to console instead.")
   
   # 로그 전파 방지
   logger.propagate = False
  
   return logger

class TradingLogger:
   """
   트레이딩 전용 로거 (메모리 로깅 추가)
   V4.5.2 원본
   """
  
   def __init__(self, name: str = 'Trading'):
       self.logger = setup_logger(name)
       self.trade_count = 0
       self.log_records = []
       self.log_records.append(f"--- Log Session Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

   def _log_and_record(self, level, message):
       """내부 함수: 로깅 및 리스트 기록 동시 처리"""
       timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
       formatted_message = f"{timestamp} - {level.upper()} - {message}"
      
       log_func = getattr(self.logger, level.lower(), self.logger.info)
       log_func(message)
      
       # 메모리 로그에 추가
       self.log_records.append(formatted_message)

   def log_trade(self, action: str, symbol: str, price: float,
                quantity: float, pnl: float = 0):
       """거래 로그 기록"""
       self.trade_count += 1
       message = (
           f"#{self.trade_count} {action} | {symbol} | "
           f"Price: {price:.4f} | Qty: {quantity:.4f} | PnL: {pnl:.2f}"
       )
       self._log_and_record('info', message)

   def log_signal(self, strategy: str, signal: str, confidence: float, details: dict):
       """신호 로깅 - 딕셔너리 안전 처리"""
       try:
           # NumPy 타입을 Python 기본 타입으로 변환
           safe_details = {}
           for key, value in details.items():
               if isinstance(value, np.bool_): safe_details[key] = bool(value)
               elif isinstance(value, np.number): safe_details[key] = round(float(value), 4)
               else: safe_details[key] = value
          
           details_str = " | ".join([f"{k}:{v}" for k, v in safe_details.items()])
           message = f"🔔 {strategy} {signal} | Confidence: {confidence:.2f} | {details_str}"
           self._log_and_record('info', message)
          
       except Exception as e:
           warning_message = f"Signal logging error: {e} | Strategy: {strategy}"
           self._log_and_record('warning', warning_message)
          
   def log_performance(self, metrics: dict):
       """성과 지표 로그 기록"""
       try:
           safe_metrics = {}
           for k, v in metrics.items():
               if isinstance(v, np.number): safe_metrics[k] = round(float(v), 4)
               else: safe_metrics[k] = v
              
           metrics_str = ' | '.join([f"{k}: {v}" for k, v in safe_metrics.items()])
           message = f"📈 Performance | {metrics_str}"
           self._log_and_record('info', message)
       except Exception as e:
           warning_message = f"Performance logging error: {e}"
           self._log_and_record('warning', warning_message)

   def log_error(self, error_msg: str, context: dict = None):
       """에러 로그 기록"""
       message = error_msg
       if context:
           context_str = ' | '.join([f"{k}: {v}" for k, v in context.items()])
           message += f" | Context: {context_str}"
       self._log_and_record('error', message)
  
   def log_warning(self, warning_msg: str, context: dict = None):
       """경고 로그 기록"""
       message = warning_msg
       if context:
           context_str = ' | '.join([f"{k}: {v}" for k, v in context.items()])
           message += f" | Context: {context_str}"
       self._log_and_record('warning', message)

   def log_info(self, info_msg: str):
        """일반 정보 로그"""
        self._log_and_record('info', info_msg)

   def get_log_records(self) -> List[str]:
       """저장된 로그 리스트 반환"""
       return self.log_records

# 글로벌 로거 인스턴스
trading_logger = TradingLogger()
