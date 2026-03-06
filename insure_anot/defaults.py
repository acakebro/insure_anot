from __future__ import annotations

from datetime import date
from typing import Dict, List, Tuple

from .types import CarePathParameters, PersonProfile, PolicySetup, PremiumBand


DEFAULT_DOB = date(1996, 10, 9)
DEFAULT_PROJECTION_START = date(2026, 3, 6)


# Source: policy screenshots provided by user (effective 27 Feb 2026).
# Values are annual SGD rates by Age Next Birthday (ANB), grouped by ranges.
_GSH_BANDS: List[Tuple[int, int, float, float]] = [
    # age_from, age_to, gsh_total, gsh_cash
    (1, 3, 392.93, 0.00),
    (4, 20, 374.40, 0.00),
    (21, 25, 514.09, 0.00),
    (26, 30, 550.06, 0.00),
    (31, 35, 855.07, 52.07),
    (36, 40, 882.32, 79.32),
    (41, 45, 1358.58, 121.58),
    (46, 50, 1394.55, 157.55),
    (51, 55, 2079.11, 576.11),
    (56, 60, 2409.38, 906.38),
    (61, 63, 3341.52, 1610.52),
    (64, 65, 3356.78, 1625.78),
    (66, 68, 4425.96, 2499.96),
    (69, 70, 4676.66, 2750.66),
    (71, 73, 5412.22, 2869.22),
    (74, 75, 6488.83, 3772.83),
    (76, 78, 7395.25, 4468.25),
    (79, 80, 8664.87, 5577.87),
    (81, 83, 9231.04, 6028.04),
    (84, 85, 9937.53, 6421.53),
    (86, 88, 10143.59, 6458.59),
    (89, 90, 10223.16, 6538.16),
    (91, 93, 10344.82, 6618.82),
    (94, 95, 10410.22, 6684.22),
    (96, 98, 10477.80, 6751.80),
    (99, 100, 10526.85, 6800.85),
]

_GTC_BANDS: List[Tuple[int, int, float]] = [
    # age_from, age_to, gtc_total
    (1, 3, 503.58),
    (4, 20, 464.34),
    (21, 25, 446.90),
    (26, 30, 468.70),
    (31, 35, 547.18),
    (36, 40, 586.42),
    (41, 45, 878.54),
    (46, 50, 1034.41),
    (51, 55, 1621.92),
    (56, 60, 2133.13),
    (61, 63, 2782.77),
    (64, 65, 3001.86),
    (66, 68, 3761.59),
    (69, 70, 4151.81),
    (71, 73, 4665.20),
    (74, 75, 5481.61),
    (76, 78, 6204.28),
    (79, 80, 7187.46),
    (81, 83, 7808.76),
    (84, 85, 8364.66),
    (86, 88, 8611.00),
    (89, 90, 8959.80),
    (91, 93, 9209.41),
    (94, 95, 9416.51),
    (96, 98, 9560.39),
    (99, 100, 9680.29),
]

# Screenshot-provided value at ANB 30. Full GHC age table was not included in shared shots.
# For v1 defaults, we carry this annual value across all ANB bands; user can edit in-app.
_GHC_DEFAULT_TOTAL = 170.04
_GHC_DEFAULT_CASH = 170.04


def _ge_policy_bands(
    ghc_total: float = _GHC_DEFAULT_TOTAL, ghc_cash: float = _GHC_DEFAULT_CASH
) -> List[PremiumBand]:
    gtc_map = {(age_from, age_to): gtc_total for age_from, age_to, gtc_total in _GTC_BANDS}
    bands: List[PremiumBand] = []
    for age_from, age_to, gsh_total, gsh_cash in _GSH_BANDS:
        gtc_total = gtc_map.get((age_from, age_to), 0.0)
        bands.append(
            PremiumBand(
                age_from=age_from,
                age_to=age_to,
                gsh_total=gsh_total,
                gsh_cash=gsh_cash,
                gtc_total=gtc_total,
                gtc_cash=gtc_total,
                ghc_total=ghc_total,
                ghc_cash=ghc_cash,
            )
        )
    return bands


# Source: Income Enhanced IncomeShield premium table (main plan), Singapore Citizen/PR,
# Basic-SG column, effective 1 Oct 2025.
# URL: https://www.income.com.sg/health-and-personal-accident/enhanced-incomeshield/premiums
# Values below are mapped as:
# gsh_total = MediShield Life premium + Additional private insurance coverage premium (Basic-SG)
# gsh_cash = cash outlay shown in Basic-SG cash outlay column
_INCOME_EIS_BASIC_SG_ROWS: List[Tuple[int, int, float, float, float]] = [
    # age_from, age_to, medishield_premium, basic_sg_additional_premium, basic_sg_cash_outlay
    (1, 18, 200.00, 35.00, 0.00),
    (19, 20, 200.00, 47.00, 0.00),
    (21, 25, 295.00, 48.00, 0.00),
    (26, 30, 295.00, 48.00, 0.00),
    (31, 35, 503.00, 86.00, 0.00),
    (36, 40, 503.00, 108.00, 0.00),
    (41, 45, 637.00, 155.00, 0.00),
    (46, 50, 637.00, 178.00, 0.00),
    (51, 55, 903.00, 217.00, 0.00),
    (56, 60, 903.00, 220.00, 0.00),
    (61, 65, 1131.00, 390.00, 0.00),
    (66, 70, 1326.00, 615.00, 15.00),
    (71, 73, 1643.00, 914.00, 14.00),
    (74, 75, 1816.00, 968.00, 68.00),
    (76, 78, 2027.00, 1158.00, 258.00),
    (79, 80, 2187.00, 1318.00, 418.00),
    (81, 83, 2303.00, 1547.00, 647.00),
    (84, 85, 2616.00, 1703.00, 803.00),
    (86, 88, 2785.00, 1879.00, 979.00),
    (89, 90, 2785.00, 2189.00, 1289.00),
    (91, 93, 2826.00, 2620.00, 1720.00),
    (94, 95, 2826.00, 2922.00, 2022.00),
    (96, 98, 2826.00, 3221.00, 2321.00),
    (99, 100, 2826.00, 3530.00, 2630.00),
]


def _income_eis_basic_sg_policy_bands() -> List[PremiumBand]:
    bands: List[PremiumBand] = []
    for age_from, age_to, msl, additional, cash_outlay in _INCOME_EIS_BASIC_SG_ROWS:
        bands.append(
            PremiumBand(
                age_from=age_from,
                age_to=age_to,
                gsh_total=msl + additional,
                gsh_cash=cash_outlay,
                gtc_total=0.0,
                gtc_cash=0.0,
                ghc_total=0.0,
                ghc_cash=0.0,
            )
        )
    return bands


def default_person_profile() -> PersonProfile:
    return PersonProfile(
        date_of_birth=DEFAULT_DOB,
        projection_start_date=DEFAULT_PROJECTION_START,
        currency="SGD",
    )


def default_care_paths() -> Dict[str, CarePathParameters]:
    return {
        "partner_panel": CarePathParameters(
            name="Partnering institution + panel specialist",
            deductible=5000.0,
            coinsurance_rate=0.10,
            rider_deductible_coverage_rate=0.30,
            rider_coinsurance_coverage_rate=0.50,
            rider_loss_limit=6500.0,
        ),
        "non_panel_conservative": CarePathParameters(
            name="Non-panel / non-partner conservative path",
            deductible=6000.0,
            coinsurance_rate=0.40,
            rider_deductible_coverage_rate=0.0,
            rider_coinsurance_coverage_rate=0.0,
            rider_loss_limit=None,
        ),
    }


def default_setup_a() -> PolicySetup:
    return PolicySetup(
        setup_name="Setup A (Current Stack)",
        gsh_plan_name="GREAT SupremeHealth P PRIME",
        gtc_plan_name="GREAT TotalCare P PRIME",
        ghc_plan_name="GREAT Hospital Cash Plan A",
        include_gtc=True,
        include_ghc=True,
        premium_bands=_ge_policy_bands(),
        care_paths=default_care_paths(),
    )


def default_setup_b() -> PolicySetup:
    return PolicySetup(
        setup_name="Setup B (No GTC Rider)",
        gsh_plan_name="GREAT SupremeHealth P PRIME",
        gtc_plan_name="GREAT TotalCare P PRIME",
        ghc_plan_name="GREAT Hospital Cash Plan A",
        include_gtc=False,
        include_ghc=True,
        premium_bands=_ge_policy_bands(),
        care_paths=default_care_paths(),
    )


def default_setup_current_isp_only() -> PolicySetup:
    return PolicySetup(
        setup_name="Setup A (Current ISP Only)",
        gsh_plan_name="Income Enhanced IncomeShield Basic (SG) - Main Plan",
        gtc_plan_name="No Rider",
        ghc_plan_name="No Hospital Cash Plan",
        include_gtc=False,
        include_ghc=False,
        premium_bands=_income_eis_basic_sg_policy_bands(),
        care_paths={
            "partner_panel": CarePathParameters(
                name="Private path baseline (no rider)",
                deductible=3500.0,
                coinsurance_rate=0.10,
                rider_deductible_coverage_rate=0.0,
                rider_coinsurance_coverage_rate=0.0,
                rider_loss_limit=None,
            ),
            "non_panel_conservative": CarePathParameters(
                name="Non-panel / non-partner conservative path",
                deductible=3500.0,
                coinsurance_rate=0.40,
                rider_deductible_coverage_rate=0.0,
                rider_coinsurance_coverage_rate=0.0,
                rider_loss_limit=None,
            ),
        },
    )


def default_setup_ge_full_suite() -> PolicySetup:
    return PolicySetup(
        setup_name="Setup B (Proposed GE Full Suite)",
        gsh_plan_name="GREAT SupremeHealth P PRIME",
        gtc_plan_name="GREAT TotalCare P PRIME",
        ghc_plan_name="GREAT Hospital Cash Plan A",
        include_gtc=True,
        include_ghc=True,
        premium_bands=_ge_policy_bands(),
        care_paths=default_care_paths(),
    )
