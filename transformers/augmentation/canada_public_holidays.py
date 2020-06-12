"""Flag for whether a date falls on a public holiday in Canada."""
from h2oaicore.transformer_utils import CustomTimeSeriesTransformer
from h2oaicore.mojo_transformers import MjT_FillNa, MjT_Replace, MjT_BinaryOp, MjT_ConstBinaryOp, \
    MjT_IntervalMap, MjT_Agg, MjT_ImputeNa, MjT_Datepart
from h2oaicore.mojo_transformers_utils import MergeTransformer, AsType, _mojo_min, _mojo_max, \
    _mojo_mean, _mojo_std, _mojo_skew, _mojo_kurtosis, _mojo_median, _mojo_sum
from h2oaicore.mojo import MojoWriter, MojoFrame, MojoColumn, MojoType
import datatable as dt
import numpy as np
import pandas as pd
import holidays
import datetime
from sklearn.preprocessing import LabelEncoder


# Add lead dates
def lead_dates(df, days, date_colname):
    leads = []
    for i in range(len(df)):
        for j in range(days+1):
            leads.append((df[date_colname][i],(pd.date_range(pd.to_datetime(df[date_colname][i]) + pd.Timedelta(days=-days), periods=(days+1), freq='D').to_list()[j].strftime("%Y-%m-%d"))))
    return pd.merge(df,pd.DataFrame(leads, columns=[date_colname,'Lead_Dates']), on=date_colname)


class CanadaHolidayTransformer2(CustomTimeSeriesTransformer):
    _modules_needed_by_name = ['holidays']
    _display_name = 'CA_Holidays'


    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    def fit(self, X: dt.Frame, y: np.array = None):
        """Fit is used to keep the memory of Holidays"""
        # For holidays we only need the date
        X = X[:, self.time_column].to_pandas()
        # Transform to pandas date time
        X[self.time_column] = pd.to_datetime(X[self.time_column])
        # Compute min and max year to decide the number of years in adavnce we keep
        mn_year = X[self.time_column].dt.year.min()
        mx_year = X[self.time_column].dt.year.max()
        if np.isnan(mn_year) or np.isnan(mx_year):
            years = []
        else:
            # Start at min year and end at 2*max_year - min_year + 1
            # If min year is 2016, max year 2018
            # then we keep dates until 2021
            # As a reminder np.arange(1, 3) returns [1, 2]
            years = np.arange(int(mn_year), int(mx_year + mx_year - mn_year + 2))

        ### PLEASE CONFIGURE ###
        lookback_days = 14

        self.memos = {}
        
        # General first
        ca_holidays = holidays.CA()
        for year in list(years):
            ca_holidays._populate(year)
        ca_holidays.observed = False
        hdays = [date for date, name in sorted(ca_holidays.items())]
        holidays_df = lead_dates(pd.DataFrame(hdays, columns=[self.time_column], dtype='datetime64[ns]'), lookback_days, self.time_column) 
        holidays_df['year'] = holidays_df[self.time_column].dt.year
        holidays_df['doy'] = holidays_df[self.time_column].dt.dayofyear
        holidays_df.sort_values(by=['year', 'doy']).drop_duplicates(subset=['year'], keep='first').reset_index(
            drop=True)
        holidays_df.drop(self.time_column, axis=1, inplace=True)
        self.memos['country'] = holidays_df

        # Now do province in the same manner
        for prov in ['AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YU']:
            ca_holidays = holidays.CA(prov=prov)
            for year in list(years):
                ca_holidays._populate(year)
            ca_holidays.observed = False
            hdays = [date for date, name in sorted(ca_holidays.items())]
            holidays_df = lead_dates(pd.DataFrame(hdays, columns=[self.time_column], dtype='datetime64[ns]'), lookback_days, self.time_column)
            holidays_df['year'] = holidays_df[self.time_column].dt.year
            holidays_df['doy'] = holidays_df[self.time_column].dt.dayofyear
            holidays_df.sort_values(by=['year', 'doy']).drop_duplicates(subset=['year'], keep='first').reset_index(
                drop=True)
            holidays_df.drop(self.time_column, axis=1, inplace=True)
            self.memos[prov] = holidays_df

    def fit_transform(self, X: dt.Frame, y: np.array = None):
        # create the list of holidays for Canada
        self.fit(X, y)
        # Transform the date
        return self.transform(X)

    def transform(self, X: dt.Frame):
        # Keep date only
        X = X[:, self.time_column].to_pandas()
        # Transform to pandas date time
        X[self.time_column] = pd.to_datetime(X[self.time_column])
        # Create Year and day of year so that we can merge with stored holidays
        X['year'] = X[self.time_column].dt.year
        X['doy'] = X[self.time_column].dt.dayofyear

        # General first
        holi_df = self.memos['country']
        holi_df['is_CA_holiday_country'] = 1
        X["is_CA_holiday_country"] = X.merge(
            self.memos['country'], on=['year', 'doy'], how='left'
        ).fillna(0)['is_CA_holiday_country']

        for prov in ['AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YU']:
            holi_df = self.memos[prov]
            holi_df[f'is_CA_holiday_{prov}'] = 1
            X[f'is_CA_holiday_{prov}'] = X.merge(
                holi_df, on=['year', 'doy'], how='left'
            ).fillna(0)[f'is_CA_holiday_{prov}']

        X.drop([self.time_column, 'year', 'doy'], axis=1, inplace=True)

        features = [
            f'is_CA_holiday_{prov}'
            for prov in ['country', 'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YU']
        ]
        self._output_feature_names = list(features)
        self._feature_desc = list(features)

        return X


    def write_to_mojo(self, mojo: MojoWriter, iframe: MojoFrame, group_uuid=None, group_name=None):
        import uuid
        group_uuid = str(uuid.uuid4())
        group_name = self.__class__.__name__

        iframe = iframe[self.time_column]
        icol = iframe.get_column(0)
        if icol.type != MojoType.STR:
            iframe = AsType("int").write_to_mojo(mojo, iframe, group_uuid=group_uuid, group_name=group_name)
            iframe = AsType("str").write_to_mojo(mojo, iframe, group_uuid=group_uuid, group_name=group_name)
            icol = iframe.get_column(0)

        # We have to add each holiday to the MOJO
        oframe = MojoFrame()
        for prov in ['country', 'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YU']:
            tmpframe = iframe.duplicate()
            mojo += MjT_Replace(iframe=iframe, oframe=tmpframe,
                                group_uuid=group_uuid, group_name=group_name,
                                map=[('None', None), ('', None)])
            tcol = tmpframe.get_column(0)
            datetime_format = self.datetime_formats[self.time_column]
            if datetime_format is not None:
                mojo.set_datetime_format_str(tcol, datetime_format)
            iframe = tmpframe
            tframe = AsType("datetime64").write_to_mojo(mojo, iframe,
                                                        group_uuid=group_uuid,
                                                        group_name=group_name)
            year_col = MojoColumn(name="year", dtype="int")
            doy_col = MojoColumn(name="doy", dtype="int")
            mojo += MjT_Datepart(iframe=tframe, oframe=MojoFrame(columns=[year_col]),
                                 group_uuid=group_uuid, group_name=group_name,
                                 fn="year")
            mojo += MjT_Datepart(iframe=tframe, oframe=MojoFrame(columns=[doy_col]),
                                 group_uuid=group_uuid, group_name=group_name,
                                 fn="dayofyear")
            dates_frame = MojoFrame(columns=[year_col, doy_col])
            feat = f'is_DE_holiday_{prov}'
            holi_df = self.memos[prov]
            holi_df[feat] = 1
            mout = MergeTransformer.from_frame(
                holi_df, ['year', 'doy']).write_to_mojo(mojo, dates_frame,
                                                        group_uuid=group_uuid,
                                                        group_name=group_name)
            holi_df.drop(feat, axis=1, inplace=True)

            mlag = mout[feat]
            mlag.names = [feat]
            olag = mlag.get_column(0).duplicate()
            mojo += MjT_FillNa(iframe=mlag, oframe=MojoFrame(columns=[olag]),
                               group_uuid=group_uuid, group_name=group_name,
                               repl=olag.pytype(0))
            oframe += olag

        # print(oframe.names)
        oframe = AsType("int").write_to_mojo(mojo, oframe,
                                             group_uuid=group_uuid,
                                             group_name=group_name)
        # print(oframe.names)
        return oframe
