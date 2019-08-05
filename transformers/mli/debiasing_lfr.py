from h2oaicore.transformer_utils import CustomTransformer
from h2oaicore.systemutils import config

import datatable as dt
import numpy as np


class LfrDebiasingTransformer(CustomTransformer):
    _regression = False
    _multiclass = False

    _numeric_output = False

    _modules_needed_by_name = ['aif360']

    _display_name = "LrfDebiasingTransformer"

    @staticmethod
    def get_default_properties():
        return dict(
            col_type="all",
            min_cols="all",
            max_cols="all",
            relative_importance=1,
            num_default_instances=1,
        )

    def fit(self, X: dt.Frame, y: np.array = None):
        from aif360.datasets import BinaryLabelDataset
        from aif360.algorithms.preprocessing.lfr import LFR

        self._validate_input()
        privileged_groups = config.privileged_groups
        unprivileged_groups = config.unprivileged_groups
        favorable_label = config.favorable_label
        unfaborable_label = config.unfavorable_label
        protected_attribute_names = config.protected_attribute_names

        label_names = np.unique(y)

        self.lfr = LFR(
            unprivileged_groups=unprivileged_groups,
            privileged_groups=privileged_groups,
            verbose=0,
        )

        self.lfr.fit(
            BinaryLabelDataset(
                favorable_label=favorable_label,
                unfavorable_label=unfaborable_label,
                df=X.to_pandas(),
                label_names=label_names,
                protected_attribute_names=protected_attribute_names,
            )
        )

    def fit_transform(self, X: dt.Frame, y: np.array = None):
        self.fit(X, y)
        return self.transform(X)

    def transform(self, X: dt.Frame):
        from aif360.datasets import BinaryLabelDataset
        transformed_X: BinaryLabelDataset = self.lfr.transform(X.to_pandas())
        return transformed_X.features

    def _validate_input(self):
        if "privileged_groups" not in config:
            raise ValueError("Privileged groups missing from config!")
        if "unprivileged_groups" not in config:
            raise ValueError("Unprivileged groups missing from config!")
        if "favorable_label" not in config:
            raise ValueError("Favorable label missing from config!")
        if "unfavorable_label" not in config:
            raise ValueError("Unfavorable label missing from config!")
        if "protected_attribute_names" not in config:
            raise ValueError("Protected attribute names missing from config!")
