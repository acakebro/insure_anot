from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class PersonProfile:
    date_of_birth: date
    projection_start_date: date
    currency: str = "SGD"


@dataclass
class PremiumBand:
    age_from: int
    age_to: int
    gsh_total: float
    gsh_cash: float
    gtc_total: float
    gtc_cash: float
    ghc_total: float
    ghc_cash: float


@dataclass
class CarePathParameters:
    name: str
    deductible: float
    coinsurance_rate: float
    rider_deductible_coverage_rate: float
    rider_coinsurance_coverage_rate: float
    rider_loss_limit: Optional[float]


@dataclass
class PolicySetup:
    setup_name: str
    gsh_plan_name: str
    gtc_plan_name: str
    ghc_plan_name: str
    include_gtc: bool
    include_ghc: bool
    premium_bands: List[PremiumBand] = field(default_factory=list)
    care_paths: Dict[str, CarePathParameters] = field(default_factory=dict)


@dataclass
class ClaimScenario:
    bill_amount: float
    care_path_key: str


@dataclass
class ProjectionAssumptions:
    end_age: int
    return_base: float
    return_low: float
    return_high: float
    carry_forward_last_band: bool = True


@dataclass
class ComparisonResult:
    ages: List[int]
    premiums_total_a: List[float]
    premiums_total_b: List[float]
    premiums_cash_a: List[float]
    premiums_cash_b: List[float]
    cumulative_total_a: List[float]
    cumulative_total_b: List[float]
    cumulative_cash_a: List[float]
    cumulative_cash_b: List[float]
    invest_cash_base: List[float]
    invest_cash_low: List[float]
    invest_cash_high: List[float]
    invest_total_base: List[float]
    invest_total_low: List[float]
    invest_total_high: List[float]
    carry_forward_warning_a: bool
    carry_forward_warning_b: bool
