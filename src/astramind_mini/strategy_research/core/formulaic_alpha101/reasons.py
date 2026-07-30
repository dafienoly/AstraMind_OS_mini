"""Stable failure codes for Formulaic Alpha101 raw values."""

from enum import StrEnum


class Alpha101Reason(StrEnum):
    INPUT_MISSING = "alpha101_input_missing"
    WINDOW_INCOMPLETE = "alpha101_window_incomplete"
    NO_LEGAL_BAR = "alpha101_no_legal_bar"
    ZERO_DENOMINATOR = "alpha101_zero_denominator"
    ZERO_VARIANCE = "alpha101_zero_variance"
    LOG_DOMAIN = "alpha101_log_domain"
    POWER_DOMAIN = "alpha101_power_domain"
    SCALE_ZERO_NORM = "alpha101_scale_zero_norm"
    CROSS_SECTION_TOO_SMALL = "alpha101_cross_section_too_small"
    NONFINITE = "alpha101_nonfinite"
    SW_L1_NOT_POINT_IN_TIME = "alpha101_sw_l1_not_point_in_time"
    SW_L2_NOT_POINT_IN_TIME = "alpha101_sw_l2_not_point_in_time"
    SW_L3_UNAVAILABLE = "alpha101_sw_l3_unavailable"


class Alpha101Failure(ValueError):
    def __init__(self, reason: Alpha101Reason) -> None:
        super().__init__(reason.value)
        self.reason = reason


__all__ = ["Alpha101Failure", "Alpha101Reason"]
