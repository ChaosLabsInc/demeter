import math
from datetime import date, timedelta

import pandas as pd

from demeter import TokenInfo, UniV3Pool, Actuator, Strategy, ChainType, PeriodTrigger, realized_volatility, \
    simple_moving_average, MarketInfo, UniLpMarket, MarketDict, RowData

pd.options.display.max_columns = None
pd.set_option('display.width', 5000)
c = 2


class AddByVolatility(Strategy):
    """
    We will provide liquidity inside the Bollinger Bands.
    These bands are made up of a lower band BOLL = pa − c · v
    and an upper band BOLU = pa + c · v.
    The liquidity position will be [pa − v · c, pa + v · c].

    * pa is simple moving average
    * c is a constant value, =2
    * v is volatility

    we will adjust liquidity every 4 hours, by remove all the liquidity, then even split all the capital into two assets,
    and provide liquidity by the rules above.

    """

    def initialize(self):
        self._add_column(market_key, "sma_1_day", simple_moving_average(self.data[market_key].price, timedelta(days=1)))
        self._add_column(market_key, "volatility", realized_volatility(self.data[market_key].price,
                                                                       timedelta(days=1),
                                                                       timedelta(days=1)))
        self.triggers.append(PeriodTrigger(time_delta=timedelta(hours=4),
                                           trigger_immediately=True,
                                           do=self.work))
        self.markets.default.even_rebalance(self.data[market_key].price[0])

    def work(self, row_data: MarketDict[RowData]):
        lp_market: UniLpMarket = self.broker.markets[market_key]
        lp_row_data = row_data[market_key]
        if len(lp_market.positions) > 0:
            lp_market.remove_all_liquidity()
            lp_market.even_rebalance(lp_row_data.price)
        if math.isnan(lp_row_data.volatility):
            return
        limit = c * float(lp_row_data.price) * lp_row_data.volatility
        lp_market.add_liquidity(lp_row_data.sma_1_day - limit,
                                lp_row_data.sma_1_day + limit)


if __name__ == "__main__":
    usdc = TokenInfo(name="usdc", decimal=6)  # declare  token0
    eth = TokenInfo(name="eth", decimal=18)  # declare token1
    pool = UniV3Pool(usdc, eth, 0.05, usdc)  # declare pool
    market_key = MarketInfo("uni_market")

    actuator = Actuator()  # declare actuator
    broker = actuator.broker
    market = UniLpMarket(market_key, pool)

    broker.add_market(market)
    broker.set_balance(usdc, 5000)
    broker.set_balance(eth, 0)

    actuator.strategy = AddByVolatility()

    market.data_path = "../data"
    market.load_data(ChainType.Polygon.name,
                     "0x45dda9cb7c25131df268515131f647d726f50608",
                     date(2022, 8, 5),
                     date(2022, 8, 10))
    actuator.set_price(market.get_price_from_data())
    actuator.run()  # run test
