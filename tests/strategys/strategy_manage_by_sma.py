from datetime import date, datetime
from typing import Union
import demeter.indicator
from download import ChainType
from demeter import TokenInfo, PoolBaseInfo, Runner, Strategy, Asset, BarStatus, BuyAction, SellAction, RowData
import pandas as pd


class AddLpByMa(Strategy):
    price_width = 100

    def initialize(self):
        prices = self.data.closeTick.map(lambda x: self.broker.tick_to_price(x))
        self._add_column("ma5", demeter.indicator.simple_moving_average(prices, 5))

    def rebalance(self, price):
        status: BarStatus = self.broker.get_status(price)
        base_amount = status.capital.number / 2
        quote_amount_diff = base_amount / price - status.quote_balance.number
        if quote_amount_diff > 0:
            self.buy(quote_amount_diff)
        elif quote_amount_diff < 0:
            self.sell(0 - quote_amount_diff)

    def next(self, time: datetime, row_data: Union[RowData, pd.Series]):
        if time.minute != 0:
            return
        if len(self.broker.positions) > 0:
            keys = list(self.broker.positions.keys())
            for k in keys:
                self.remove_liquidity(k)
            self.rebalance(row_data.price)
        ma_price = row_data.ma5 if row_data.ma5 > 0 else row_data.price
        self.add_liquidity(self.broker.base_asset.balance,
                           self.broker.quote_asset.balance,
                           ma_price - AddLpByMa.price_width,
                           ma_price + AddLpByMa.price_width)

    def notify_buy(self, action: BuyAction):
        print(action.get_output_str(), action.base_balance_after.number / action.quote_balance_after.number)

    def notify_sell(self, action: SellAction):
        print(action.get_output_str(), action.base_balance_after.number / action.quote_balance_after.number)


if __name__ == "__main__":
    eth = TokenInfo(name="eth", decimal=18)
    usdc = TokenInfo(name="usdc", decimal=6)
    pool = PoolBaseInfo(usdc, eth, 0.05, usdc)

    runner_instance = Runner(pool)
    runner_instance.strategy = AddLpByMa()
    runner_instance.set_assets([Asset(usdc, 1835), Asset(eth, 1)])
    runner_instance.data_path = "../../data"
    runner_instance.load_data(ChainType.Polygon.name,
                              "0x45dda9cb7c25131df268515131f647d726f50608",
                              date(2022, 8, 19),
                              date(2022, 8, 20))
    runner_instance.run()
    runner_instance.output()
