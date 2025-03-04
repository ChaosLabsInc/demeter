from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict

import pandas as pd

from .._typing import TokenInfo, DemeterError, UnitDecimal, PositionInfo
from ..broker import BaseAction, ActionTypeEnum, MarketBalance, MarketStatus
from ..utils import get_formatted_from_dict


class UniV3Pool(object):
    """
    pool information, corresponding with definition in pool contract.

    :param token0: First token in  pool contract.
    :type token0:  TokenInfo
    :param token1: Second token in  pool contract.
    :type token1: TokenInfo
    :param fee: fee rate of this pool, should be among [0.05, 0.3, 1]
    :type fee: float, 0.05
    :param base_token: which token will be considered as base token. eg: to a token pair of USDT/BTC, if you want price unit to be like 10000 usdt/btc, you should set usdt as base token, otherwise if price unit is 0.00001 btc/usdt, you should set btc as base token
    :type base_token: TokenInfo
    """

    def __init__(self, token0: TokenInfo, token1: TokenInfo, fee: float, base_token: TokenInfo):
        fee = Decimal(str(fee))
        self.token0 = token0
        self.token1 = token1
        self.is_token0_base = (base_token == token0)
        self.base_token = base_token
        self.tickSpacing = int(fee * 200)
        self.fee: Decimal = fee * Decimal(10000)
        self.fee_rate: Decimal = Decimal(fee) / Decimal(100)

    def __str__(self):
        """
        get string
        :return:
        :rtype:
        """
        return "PoolBaseInfo(Token0: {},".format(self.token0) + \
            "Token1: {},".format(self.token1) + \
            "fee: {},".format(self.fee_rate * Decimal(100)) + \
            "base token: {})".format(self.token0.name if self.is_token0_base else self.token1.name)


@dataclass
class UniLpBalance(MarketBalance):
    """
    current status of broker

    :param timestamp: timestamp
    :type timestamp: datetime
    :param base_uncollected: base token uncollect fee in all the positions.
    :type base_uncollected: UnitDecimal
    :param quote_uncollected: quote token uncollect fee in all the positions.
    :type quote_uncollected: UnitDecimal
    :param base_in_position: base token amount deposited in positions, calculated according to current price
    :type base_in_position: UnitDecimal
    :param quote_in_position: quote token amount deposited in positions, calculated according to current price
    :type quote_in_position: UnitDecimal
    :param pool_net_value: 按照池子base/quote关系的净值. 不是broker层面的(which 通常是对u的).
    :type pool_net_value: UnitDecimal
    :param price: current price
    :type price: UnitDecimal

    """
    base_uncollected: UnitDecimal
    quote_uncollected: UnitDecimal
    base_in_position: UnitDecimal
    quote_in_position: UnitDecimal
    position_count: int

    def get_output_str(self) -> str:
        """
        get colored and formatted string to output in console
        :return: formatted string
        :rtype: str
        """
        return get_formatted_from_dict({
            "total capital": self.pool_net_value.to_str(),
            "uncollect fee": f"{self.base_uncollected.to_str()},{self.quote_uncollected.to_str()}",
            "in position amount": f"{self.base_in_position.to_str()},{self.quote_in_position.to_str()}",
            "position count": self.position_count.to_str()
        })

    def to_array(self):
        return [
            self.base_uncollected,
            self.quote_uncollected,
            self.base_in_position,
            self.quote_in_position,
            self.position_count
        ]


@DeprecationWarning
class BrokerAsset(object):
    """
    Wallet of broker, manage balance of an asset.
    It will prevent excess usage on asset.
    """

    def __init__(self, token: TokenInfo, init_amount=Decimal(0)):
        self.token_info = token
        self.name = token.name
        self.decimal = token.decimal
        self.balance = init_amount

    def __str__(self):
        return f"{self.balance} {self.name}"

    def add(self, amount=Decimal(0)):
        """
        add amount to balance
        :param amount: amount to add
        :type amount: Decimal
        :return: entity itself
        :rtype: BrokerAsset
        """
        self.balance += amount
        return self

    def sub(self, amount=Decimal(0), allow_negative_balance=False):
        """
        subtract amount from balance. if balance is not enough, an error will be raised.

        :param amount: amount to subtract
        :type amount: Decimal
        :param allow_negative_balance: allow balance is negative
        :type allow_negative_balance: bool
        :return:
        :rtype:
        """
        base = self.balance if self.balance != Decimal(0) else Decimal(amount)

        if base == Decimal(0):  # amount and balance is both 0
            return self
        if allow_negative_balance:
            self.balance -= amount
        else:
            # if difference between amount and balance is below 0.01%, will deduct all the balance
            # That's because, the amount calculated by v3_core, has some acceptable error.
            if abs((self.balance - amount) / base) < 0.00001:
                self.balance = Decimal(0)
            elif self.balance - amount < Decimal(0):
                raise DemeterError(f"Insufficient balance, balance is {self.balance}{self.name}, "
                                   f"but sub amount is {amount}{self.name}")
            else:
                self.balance -= amount

        return self

    def amount_in_wei(self):
        return self.balance * Decimal(10 ** self.decimal)


@dataclass
class Position(object):
    """
    variables for position
    """

    pending_amount0: Decimal
    pending_amount1: Decimal
    liquidity: int


def position_dict_to_dataframe(positions: Dict[PositionInfo, Position]) -> pd.DataFrame:
    pos_dict = {
        "lower_tick": [],
        "upper_tick": [],
        "pending0": [],
        "pending1": [],
        "liquidity": []
    }
    for k, v in positions.items():
        pos_dict["lower_tick"].append(k.lower_tick)
        pos_dict["upper_tick"].append(k.upper_tick)
        pos_dict["pending0"].append(v.pending_amount0)
        pos_dict["pending1"].append(v.pending_amount1)
        pos_dict["liquidity"].append(v.liquidity)
    return pd.DataFrame(pos_dict)


@dataclass
class UniV3PoolStatus(MarketStatus):
    """
    current status of a pool, actuators can notify current status to broker by filling this entity
    """
    current_tick: int
    current_liquidity: int
    in_amount0: int
    in_amount1: int
    price: Decimal
    # tick of last minute(previous minute), to compatible with old version, keep default as None
    # note: I have to make it compatible, as someone would check out their private version,
    # Please fill this paameter as much as possible to improve accuracy
    last_tick: int | None = None


@dataclass
class UniLpBaseAction(BaseAction):
    """
    Parent class of broker actions,

    :param base_balance_after: after action balance of base token
    :type base_balance_after: UnitDecimal
    :param quote_balance_after: after action balance of quote token
    :type quote_balance_after: UnitDecimal
    """

    base_balance_after: UnitDecimal
    quote_balance_after: UnitDecimal

    def get_output_str(self):
        return str(self)


@dataclass
class AddLiquidityAction(UniLpBaseAction):
    """
    Add Liquidity

    :param base_amount_max: inputted base token amount, also the max amount to deposit
    :type base_amount_max: ActionTypeEnum
    :param quote_amount_max: inputted base token amount, also the max amount to deposit
    :type quote_amount_max: datetime
    :param lower_quote_price: lower price base on quote token.
    :type lower_quote_price: UnitDecimal
    :param upper_quote_price: upper price base on quote token.
    :type upper_quote_price: UnitDecimal
    :param base_amount_actual: actual used base token
    :type base_amount_actual: UnitDecimal
    :param quote_amount_actual: actual used quote token
    :type quote_amount_actual: UnitDecimal
    :param position: generated position
    :type position: PositionInfo
    :param liquidity: liquidity added
    :type liquidity: int
    """
    base_amount_max: UnitDecimal
    quote_amount_max: UnitDecimal
    lower_quote_price: UnitDecimal
    upper_quote_price: UnitDecimal
    base_amount_actual: UnitDecimal
    quote_amount_actual: UnitDecimal
    position: PositionInfo
    liquidity: int

    def set_type(self):
        self.action_type = ActionTypeEnum.uni_lp_add_liquidity

    def get_output_str(self) -> str:
        """
        get colored and formatted string to output in console
        :return: formatted string
        :rtype: str
        """
        return f"""\033[1;31m{"Add liquidity":<20}\033[0m""" + \
            get_formatted_from_dict({
                "max amount": f"{self.base_amount_max.to_str()},{self.quote_amount_max.to_str()}",
                "price": f"{self.lower_quote_price.to_str()},{self.upper_quote_price.to_str()}",
                "position": self.position,
                "liquidity": self.liquidity,
                "balance": f"{self.base_balance_after.to_str()}(-{self.base_amount_actual.to_str()}), {self.quote_balance_after.to_str()}(-{self.quote_amount_actual.to_str()})"
            })


@dataclass
class CollectFeeAction(UniLpBaseAction):
    """
    collect fee

    :param position: position to operate
    :type position: PositionInfo
    :param base_amount: fee collected in base token
    :type base_amount: UnitDecimal
    :param quote_amount: fee collected in quote token
    :type quote_amount: UnitDecimal

    """
    position: PositionInfo
    base_amount: UnitDecimal
    quote_amount: UnitDecimal

    def set_type(self):
        self.action_type = ActionTypeEnum.uni_lp_collect

    def get_output_str(self) -> str:
        """
        get colored and formatted string to output in console
        :return: formatted string
        :rtype: str
        """
        return f"""\033[1;33m{"Collect fee":<20}\033[0m""" + \
            get_formatted_from_dict({
                "position": self.position,
                "balance": f"{self.base_balance_after.to_str()}(+{self.base_amount.to_str()}), {self.quote_balance_after.to_str()}(+{self.quote_amount.to_str()})"
            })


@dataclass
class RemoveLiquidityAction(UniLpBaseAction):
    """
    remove position

    :param position: position to operate
    :type position: PositionInfo
    :param base_amount: base token amount collected
    :type base_amount: UnitDecimal
    :param quote_amount: quote token amount collected
    :type quote_amount: UnitDecimal
    :param removed_liquidity: liquidity number has removed
    :type removed_liquidity: int
    :param remain_liquidity: liquidity number left in position
    :type remain_liquidity: int

    """
    position: PositionInfo
    base_amount: UnitDecimal
    quote_amount: UnitDecimal
    removed_liquidity: int
    remain_liquidity: int

    def set_type(self):
        self.action_type = ActionTypeEnum.uni_lp_remove_liquidity

    def get_output_str(self) -> str:
        """
        get colored and formatted string to output in console
        :return: formatted string
        :rtype: str
        """
        return f"""\033[1;32m{"Remove liquidity":<20}\033[0m""" + \
            get_formatted_from_dict({
                "position": self.position,
                "balance": f"{self.base_balance_after.to_str()}(+0), {self.quote_balance_after.to_str()}(+0)",
                "token_got": f"{self.base_amount.to_str()},{self.quote_amount.to_str()}",
                "removed liquidity": self.removed_liquidity,
                "remain liquidity": self.remain_liquidity
            })


@dataclass
class BuyAction(UniLpBaseAction):
    """
    buy token, swap from base token to quote token.

    :param amount: amount to buy(in quote token)
    :type amount: UnitDecimal
    :param price: price,
    :type price: UnitDecimal
    :param fee: fee paid (in base token)
    :type fee: UnitDecimal
    :param base_change: base token amount changed
    :type base_change: PositionInfo
    :param quote_change: quote token amount changed
    :type quote_change: UnitDecimal

    """
    amount: UnitDecimal
    price: UnitDecimal
    fee: UnitDecimal
    base_change: UnitDecimal
    quote_change: UnitDecimal

    def set_type(self):
        self.action_type = ActionTypeEnum.uni_lp_buy

    def get_output_str(self) -> str:
        """
        get colored and formatted string to output in console
        :return: formatted string
        :rtype: str
        """
        return f"""\033[1;36m{"Buy":<20}\033[0m""" + \
            get_formatted_from_dict({
                "price": self.price.to_str(),
                "fee": self.fee.to_str(),
                "balance": f"{self.base_balance_after.to_str()}(-{self.base_change.to_str()}), {self.quote_balance_after.to_str()}(+{self.quote_change.to_str()})"
            })


@dataclass
class SellAction(UniLpBaseAction):
    """
    sell token, swap from quote token to base token.

    :param amount: amount to sell(in quote token)
    :type amount: UnitDecimal
    :param price: price,
    :type price: UnitDecimal
    :param fee: fee paid (in quote token)
    :type fee: UnitDecimal
    :param base_change: base token amount changed
    :type base_change: PositionInfo
    :param quote_change: quote token amount changed
    :type quote_change: UnitDecimal

    """
    amount: UnitDecimal
    price: UnitDecimal
    fee: UnitDecimal
    base_change: UnitDecimal
    quote_change: UnitDecimal

    def set_type(self):
        self.action_type = ActionTypeEnum.uni_lp_sell

    def get_output_str(self):
        return f"""\033[1;37m{"Sell":<20}\033[0m""" + \
            get_formatted_from_dict({
                "price": self.price.to_str(),
                "fee": self.fee.to_str(),
                "balance": f"{self.base_balance_after.to_str()}(+{self.base_change.to_str()}), {self.quote_balance_after.to_str()}(-{self.quote_change.to_str()})"
            })
