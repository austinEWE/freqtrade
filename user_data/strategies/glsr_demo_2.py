# SuperTrend strategy using pandas_ta for Freqtrade
# Save as supertrend_pandasta_strategy.py in user_data/strategies/

from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, stoploss_from_absolute
from freqtrade.persistence import Trade
from pandas import DataFrame
import pandas_ta as pta
from typing import Dict, Any
#import talib.abstract as ta
import talib as ta
import datetime

import ta as ta_2
import pandas as pd

class GLSRDemo_2(IStrategy):
    # Enable custom stoploss
    use_custom_stoploss = False
    can_short = True
    """
    SuperTrend-based freqtrade strategy using pandas_ta implementation.

    Uses:
      - pandas_ta.supertrend() to compute SuperTrend bands and trend.
      - Buy on SuperTrend flip to uptrend.
      - Sell on SuperTrend flip to downtrend.
    """

    timeframe = '1h'


    # stoploss = -0.05
    # minimal_roi = {
    #     "0": 0.05 * 2.0  # Exit immediately when 10% profit is reached
    # }
    # trailing_stop = False

    stoploss = -0.04 # Initial stoploss (e.g., -10%)
    trailing_stop = True
    trailing_stop_positive = 0.04 # 3% trailing stop


    # Hyperopt parameters
    atr_period = IntParameter(7, 21, default=10, space="buy")
    atr_multiplier = DecimalParameter(1.0, 4.0, default=2.0, decimals=2, space="buy")
    adx_threshold = IntParameter(15, 40, default=22, space="buy")

    startup_candle_count = 50

    def populate_indicators(self, dataframe: DataFrame, metadata: Dict[str, Any]) -> DataFrame:
        if dataframe.empty:
            return dataframe
        print(metadata)

        # MACD
        dataframe['MACD'], dataframe['MACD_signal'], dataframe['MACD_hist'] = ta.MACD(dataframe['close'],
                                                                    fastperiod=12,
                                                                    slowperiod=26,
                                                                    signalperiod=9)
        print(dataframe)

        dataframe['open_count'].fillna(0, inplace=True)
        dataframe['high_count'].fillna(0, inplace=True)
        dataframe['low_count'].fillna(0, inplace=True)
        dataframe['close_count'].fillna(0, inplace=True)
        dataframe['max_count'].fillna(0, inplace=True)

        dataframe['create_time'] = dataframe['date'].dt.tz_localize(None)

        core_pair = metadata['pair'].split(':')[0]

        pair_ = core_pair.replace('/', '')
        print(pair_)
        # pair_ = 'DOGEUSDC'

        metrics_data = pd.read_hdf('/Users/austin/BN_hdf_Metrics/' + pair_ + '/' + f'BN_Perp_{pair_}_5min_Metrics_202510.h5', key="df", mode="r")
        metrics_data = metrics_data.drop('symbol', axis=1)
        metrics_data.rename(columns={'sum_open_interest_value': 'oi_value', 'count_long_short_ratio': 'global_ls_ratio',
                                     'count_toptrader_long_short_ratio': 'toptrader_lsr_account',
                                     'sum_toptrader_long_short_ratio': 'toptrader_lsr_position',
                                     'sum_taker_long_short_vol_ratio': 'sum_taker_long_short_vol_ratio'}, inplace=True)
        '''Resample Metrics Data'''
        metrics_data = metrics_data.resample('60min').last()
        metrics_data = metrics_data.apply(pd.to_numeric)
        metrics_data = metrics_data.reset_index()
        dataframe = pd.merge(dataframe, metrics_data, on='create_time', how='left')
        dataframe.dropna(inplace=True)

        print(dataframe)

        ma_len = 6
      #  ma_len = 8
        bb_p1 = 2.4
        dataframe['oi_bb_u1'] = ta.EMA(dataframe['oi_value'], ma_len) + bb_p1 * dataframe['oi_value'].rolling(ma_len).std()
        dataframe['oi_bb_d1'] = ta.EMA(dataframe['oi_value'], ma_len) - bb_p1 * dataframe['oi_value'].rolling(ma_len).std()
        dataframe['oi_ma'] = ta.EMA(dataframe['oi_value'], ma_len)
        dataframe['ls_ratio_u1'] = ta.EMA(dataframe['global_ls_ratio'], ma_len) + bb_p1 * dataframe['global_ls_ratio'].rolling(ma_len).std()
        dataframe['ls_ratio_d1'] = ta.EMA(dataframe['global_ls_ratio'], ma_len) - bb_p1 * dataframe['global_ls_ratio'].rolling(ma_len).std()
        dataframe = dataframe.fillna(0)

        # dataframe["atr"] = ta.ATR(dataframe, timeperiod=5)


       # adx = ta.adx(dataframe['high'], dataframe['low'], dataframe['close'], length = 20)
        adx = ta_2.trend.ADXIndicator(dataframe['high'], dataframe['low'], dataframe['close'], window=20)
        print(adx)
        dataframe['adx'] = adx.adx()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict[str, Any]) -> DataFrame:
        dataframe['buy'] = 0

        bull_condition = (dataframe['global_ls_ratio'] < dataframe['ls_ratio_d1']) & (dataframe['global_ls_ratio'].shift(1) > dataframe['ls_ratio_d1'].shift(1)) & (dataframe['MACD_hist'] > 0)
       # cond_oi = (dataframe['oi_value'] > dataframe['oi_ma'])
        cond_oi = (dataframe['oi_value'] > dataframe['oi_bb_d1'])

        dataframe.loc[bull_condition & cond_oi, 'enter_long'] = 1

        bear_condition =  (dataframe['global_ls_ratio'] > dataframe['ls_ratio_u1']) & (dataframe['global_ls_ratio'].shift(1) < dataframe['ls_ratio_u1'].shift(1)) & (dataframe['MACD_hist'] < 0)
        dataframe.loc[bear_condition & cond_oi, 'enter_short'] = 1

        return dataframe

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        candle = dataframe.iloc[-1].squeeze()

        # For long trades: stoploss 3 ATR below current price
        # For short trades: stoploss 3 ATR above current price
        side = 1 if trade.is_short else -1

        return stoploss_from_absolute(
            current_rate + (side * candle["atr"] * 3),
            current_rate=current_rate,
            is_short=trade.is_short,
            leverage=trade.leverage
        )
    # def custom_stoploss(self, pair: str, trade, current_time, current_rate, current_profit, **kwargs):
    #     """3×ATR trailing stop loss"""
    #     df = kwargs.get('dataframe')
    #     if df is None or df.empty:
    #         return 1  # no change
    #
    #     # last row
    #     row = df.iloc[-1]
    #     atr = row.get('atr', None)
    #     if atr is None:
    #         return 1
    #
    #     # 3 ATR trailing stop
    #     stop_price = current_rate - (2 * atr)
    #     if current_rate <= stop_price:
    #         return 0.001  # trigger exit
    #
    #     return 1

    # ---- LONG EXIT ----
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict[str, Any]) -> DataFrame:
        dataframe['sell'] = 0

        bear_condition =  (dataframe['global_ls_ratio'] > dataframe['ls_ratio_u1']) & (dataframe['global_ls_ratio'].shift(1) < dataframe['ls_ratio_u1'].shift(1)) & (dataframe['MACD_hist'] < 0)
       # cond_oi = (dataframe['oi_value'] > dataframe['oi_ma'])
        cond_oi = (dataframe['oi_value'] > dataframe['oi_bb_d1'])
        dataframe.loc[bear_condition & cond_oi, 'exit_long'] = 1

        bull_condition = (dataframe['global_ls_ratio'] < dataframe['ls_ratio_d1']) & (dataframe['global_ls_ratio'].shift(1) > dataframe['ls_ratio_d1'].shift(1)) & (dataframe['MACD_hist'] > 0)
        dataframe.loc[bull_condition & cond_oi, 'exit_short'] = 1

        return dataframe
