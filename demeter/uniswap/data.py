from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict

import pandas as pd
from pandas import _typing as pd_typing

from ..broker import Rule, RowData

DEFAULT_AGG_METHOD = "first"
EMPTY_RULE = Rule(None, None, None)


@dataclass
class UniLPDataRaw:
    """
    data types in csv file saved by download module
    """
    timestamp: datetime = None
    netAmount0: int = None
    netAmount1: int = None
    closeTick: int = None
    openTick: int = None
    lowestTick: int = None
    highestTick: int = None
    inAmount0: int = None
    inAmount1: int = None
    currentLiquidity: int = None


@dataclass
class UniLPData(RowData):
    """
    data type used in back test, extended from  UniLPDataRaw
    """
    netAmount0: int = None
    netAmount1: int = None
    closeTick: int = None
    openTick: int = None
    lowestTick: int = None
    highestTick: int = None
    inAmount0: int = None
    inAmount1: int = None
    currentLiquidity: int = None
    open: Decimal = None
    price: Decimal = None
    low: Decimal = None
    high: Decimal = None
    volume0: Decimal = None
    volume1: Decimal = None


class LineTypeEnum(Enum):
    """
    predefined column, used to define fillna method.
    """
    timestamp = 1
    netAmount0 = 2
    netAmount1 = 3
    closeTick = 4
    openTick = 5
    lowestTick = 6
    highestTick = 7
    inAmount0 = 8
    inAmount1 = 9
    currentLiquidity = 10
    other = 100


LINE_RULES = {
    LineTypeEnum.timestamp.name: EMPTY_RULE,
    LineTypeEnum.netAmount0.name: Rule("sum", None, 0),
    LineTypeEnum.netAmount1.name: Rule("sum", None, 0),
    LineTypeEnum.closeTick.name: Rule("last", "ffill", None),
    LineTypeEnum.openTick.name: Rule("first", "ffill", None),
    LineTypeEnum.lowestTick.name: Rule("min", "ffill", None),
    LineTypeEnum.highestTick.name: Rule("max", "ffill", None),
    LineTypeEnum.inAmount0.name: Rule("sum", None, 0),
    LineTypeEnum.inAmount1.name: Rule("sum", None, 0),
    LineTypeEnum.currentLiquidity.name: Rule("sum", "ffill", None),
}


def get_line_rules_safe(key: str) -> Rule:
    if key in LINE_RULES:
        return LINE_RULES[key]
    else:
        return EMPTY_RULE


def resample(df: pd.DataFrame,
             rule,
             axis=0,
             closed: str | None = None,
             label: str | None = None,
             convention: str = "start",
             kind: str | None = None,
             loffset=None,
             base: int | None = None,
             on=None,
             level=None,
             origin: str | pd_typing.TimestampConvertibleTypes = "start_day",
             offset: pd_typing.TimedeltaConvertibleTypes | None = None,
             agg: Dict[str, str] = None) -> pd.DataFrame:
    """
    resample data
    :param df: data in dataframe
    :param rule: resample rule, see Dataframe.resample doc
    :param axis: resample axis, see Dataframe.resample doc
    :param closed: resample closed, see Dataframe.resample doc
    :param label: resample label, see Dataframe.resample doc
    :param convention: resample convention, see Dataframe.resample doc
    :param kind: resample kind, see Dataframe.resample doc
    :param loffset: resample loffset, see Dataframe.resample doc
    :param base: resample base, see Dataframe.resample doc
    :param on: resample on, see Dataframe.resample doc
    :param level: resample level, see Dataframe.resample doc
    :param origin: resample origin, see Dataframe.resample doc
    :param offset: resample offset, see Dataframe.resample doc
    :param agg: aggregate method
    :return: aggregated dataframe
    """
    agg = agg if agg else {}
    resampler = df.resample(rule, axis, closed, label, convention, kind, loffset, base, on, level, origin, offset)
    agg_dict = {}
    for column_name in df.columns:
        rule = get_line_rules_safe(column_name)
        agg_method = rule.agg
        if agg_method is None:
            if column_name in agg:
                agg_method = agg[column_name]
            else:
                agg_method = DEFAULT_AGG_METHOD
        agg_dict[column_name] = agg_method
    df_new = resampler.agg(agg_dict)
    return df_new


def fillna(
        df: pd.DataFrame,
        value: object | pd_typing.ArrayLike | None = None,
        method: pd_typing.FillnaOptions | None = None,
        axis: pd_typing.Axis | None = None,
        inplace: bool = False,
        limit=None,
        downcast=None) -> pd.DataFrame | None:
    """
    fill empty item. param is the same to pandas.Series.fillna

    if column name is predefined, method and value will be omitted, and data will be filled as predefined

    """
    new_df = df.copy(False)

    # fill close tick first, it will be used later.
    if LineTypeEnum.closeTick.name in new_df.columns:
        new_df[LineTypeEnum.closeTick.name] = \
            new_df[LineTypeEnum.closeTick.name].fillna(value=None,
                                                       method=get_line_rules_safe(
                                                           LineTypeEnum.closeTick.name).fillna_method,
                                                       axis=axis,
                                                       inplace=inplace,
                                                       limit=limit,
                                                       downcast=downcast)
    for column_name in new_df.columns:
        if column_name == LineTypeEnum.closeTick.name:
            continue
        rule = get_line_rules_safe(column_name)
        if not rule.fillna_method and rule.fillna_value is None:
            new_df[column_name] = new_df[column_name].fillna(value, method, axis, inplace, limit, downcast)
        else:
            current_method = rule.fillna_method if rule.fillna_method else method
            current_value = rule.fillna_value if rule.fillna_value is not None else value
            # all tick related field will be filled with close_tick.
            if column_name in [LineTypeEnum.openTick.name,
                               LineTypeEnum.highestTick.name,
                               LineTypeEnum.lowestTick.name] and LineTypeEnum.closeTick.name in new_df.columns:
                current_method = None
                current_value = new_df[LineTypeEnum.closeTick.name]
            new_df[column_name] = new_df[column_name].fillna(value=current_value, method=current_method, axis=axis,
                                                             inplace=inplace,
                                                             limit=limit,
                                                             downcast=downcast)
    return new_df
