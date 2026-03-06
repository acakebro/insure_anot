from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Dict, Iterable, List, Tuple

from .types import (
    CarePathParameters,
    ClaimScenario,
    ComparisonResult,
    PersonProfile,
    PolicySetup,
    PremiumBand,
    ProjectionAssumptions,
)


def calculate_age_next_birthday(dob: date, as_of: date) -> int:
    age = as_of.year - dob.year
    birthday_this_year = date(as_of.year, dob.month, dob.day)
    if as_of < birthday_this_year:
        return age
    return age + 1


def clamp_rate(value: float) -> float:
    return max(0.0, min(1.0, value))


def sort_bands(bands: Iterable[PremiumBand]) -> List[PremiumBand]:
    return sorted(list(bands), key=lambda b: (b.age_from, b.age_to))


def premium_for_age(
    setup: PolicySetup, age: int, carry_forward_last_band: bool
) -> Tuple[Dict[str, float], bool]:
    bands = sort_bands(setup.premium_bands)
    used_carry_forward = False
    selected_band = None

    for band in bands:
        if band.age_from <= age <= band.age_to:
            selected_band = band
            break

    if selected_band is None:
        if not bands:
            selected_band = PremiumBand(
                age_from=age,
                age_to=age,
                gsh_total=0.0,
                gsh_cash=0.0,
                gtc_total=0.0,
                gtc_cash=0.0,
                ghc_total=0.0,
                ghc_cash=0.0,
            )
        elif carry_forward_last_band and age > bands[-1].age_to:
            selected_band = bands[-1]
            used_carry_forward = True
        else:
            selected_band = PremiumBand(
                age_from=age,
                age_to=age,
                gsh_total=0.0,
                gsh_cash=0.0,
                gtc_total=0.0,
                gtc_cash=0.0,
                ghc_total=0.0,
                ghc_cash=0.0,
            )

    values = {
        "gsh_total": max(0.0, selected_band.gsh_total),
        "gsh_cash": max(0.0, selected_band.gsh_cash),
        "gtc_total": max(0.0, selected_band.gtc_total if setup.include_gtc else 0.0),
        "gtc_cash": max(0.0, selected_band.gtc_cash if setup.include_gtc else 0.0),
        "ghc_total": max(0.0, selected_band.ghc_total if setup.include_ghc else 0.0),
        "ghc_cash": max(0.0, selected_band.ghc_cash if setup.include_ghc else 0.0),
    }
    values["total"] = values["gsh_total"] + values["gtc_total"] + values["ghc_total"]
    values["cash"] = values["gsh_cash"] + values["gtc_cash"] + values["ghc_cash"]
    values["medisave"] = max(0.0, values["total"] - values["cash"])
    return values, used_carry_forward


def compute_oop_without_rider(bill_amount: float, path: CarePathParameters) -> float:
    deductible = max(0.0, path.deductible)
    coinsurance_rate = clamp_rate(path.coinsurance_rate)
    ded_paid = min(max(0.0, bill_amount), deductible)
    post_deductible = max(0.0, bill_amount - deductible)
    coinsurance_paid = coinsurance_rate * post_deductible
    return ded_paid + coinsurance_paid


def compute_oop_with_rider(bill_amount: float, path: CarePathParameters) -> float:
    deductible = max(0.0, path.deductible)
    coinsurance_rate = clamp_rate(path.coinsurance_rate)
    ded_cover_rate = clamp_rate(path.rider_deductible_coverage_rate)
    coin_cover_rate = clamp_rate(path.rider_coinsurance_coverage_rate)

    ded_paid = min(max(0.0, bill_amount), deductible)
    post_deductible = max(0.0, bill_amount - deductible)
    coinsurance_paid = coinsurance_rate * post_deductible

    ded_after_rider = ded_paid * (1.0 - ded_cover_rate)
    coin_after_rider = coinsurance_paid * (1.0 - coin_cover_rate)
    oop = ded_after_rider + coin_after_rider

    if path.rider_loss_limit is not None:
        oop = min(oop, max(0.0, path.rider_loss_limit))
    return max(0.0, oop)


def compute_claim_outcome(
    setup: PolicySetup, scenario: ClaimScenario
) -> Dict[str, float]:
    path = setup.care_paths[scenario.care_path_key]
    base_oop = compute_oop_without_rider(scenario.bill_amount, path)
    if setup.include_gtc:
        final_oop = compute_oop_with_rider(scenario.bill_amount, path)
    else:
        final_oop = base_oop
    return {
        "bill_amount": max(0.0, scenario.bill_amount),
        "base_oop": base_oop,
        "final_oop": final_oop,
        "rider_savings": max(0.0, base_oop - final_oop),
    }


def project_setup(
    setup_a: PolicySetup,
    setup_b: PolicySetup,
    start_age: int,
    assumptions: ProjectionAssumptions,
) -> ComparisonResult:
    ages = list(range(start_age, assumptions.end_age + 1))
    total_a: List[float] = []
    total_b: List[float] = []
    cash_a: List[float] = []
    cash_b: List[float] = []
    cum_total_a: List[float] = []
    cum_total_b: List[float] = []
    cum_cash_a: List[float] = []
    cum_cash_b: List[float] = []
    carry_warn_a = False
    carry_warn_b = False

    run_total_a = 0.0
    run_total_b = 0.0
    run_cash_a = 0.0
    run_cash_b = 0.0

    for age in ages:
        prem_a, carry_a = premium_for_age(setup_a, age, assumptions.carry_forward_last_band)
        prem_b, carry_b = premium_for_age(setup_b, age, assumptions.carry_forward_last_band)
        carry_warn_a = carry_warn_a or carry_a
        carry_warn_b = carry_warn_b or carry_b

        total_a.append(prem_a["total"])
        total_b.append(prem_b["total"])
        cash_a.append(prem_a["cash"])
        cash_b.append(prem_b["cash"])

        run_total_a += prem_a["total"]
        run_total_b += prem_b["total"]
        run_cash_a += prem_a["cash"]
        run_cash_b += prem_b["cash"]

        cum_total_a.append(run_total_a)
        cum_total_b.append(run_total_b)
        cum_cash_a.append(run_cash_a)
        cum_cash_b.append(run_cash_b)

    invest_cash_base = project_investment_delta(cash_a, cash_b, assumptions.return_base)
    invest_cash_low = project_investment_delta(cash_a, cash_b, assumptions.return_low)
    invest_cash_high = project_investment_delta(cash_a, cash_b, assumptions.return_high)
    invest_total_base = project_investment_delta(total_a, total_b, assumptions.return_base)
    invest_total_low = project_investment_delta(total_a, total_b, assumptions.return_low)
    invest_total_high = project_investment_delta(total_a, total_b, assumptions.return_high)

    return ComparisonResult(
        ages=ages,
        premiums_total_a=total_a,
        premiums_total_b=total_b,
        premiums_cash_a=cash_a,
        premiums_cash_b=cash_b,
        cumulative_total_a=cum_total_a,
        cumulative_total_b=cum_total_b,
        cumulative_cash_a=cum_cash_a,
        cumulative_cash_b=cum_cash_b,
        invest_cash_base=invest_cash_base,
        invest_cash_low=invest_cash_low,
        invest_cash_high=invest_cash_high,
        invest_total_base=invest_total_base,
        invest_total_low=invest_total_low,
        invest_total_high=invest_total_high,
        carry_forward_warning_a=carry_warn_a,
        carry_forward_warning_b=carry_warn_b,
    )


def project_investment_delta(
    setup_a_series: Iterable[float], setup_b_series: Iterable[float], annual_return_pct: float
) -> List[float]:
    r = annual_return_pct / 100.0
    value = 0.0
    out: List[float] = []
    for premium_a, premium_b in zip(setup_a_series, setup_b_series):
        savings_if_choose_b = max(0.0, premium_a - premium_b)
        value = (value + savings_if_choose_b) * (1.0 + r)
        out.append(value)
    return out


def make_light_guidance(
    setup_a: PolicySetup,
    setup_b: PolicySetup,
    comparison: ComparisonResult,
    oop_a_150k: float,
    oop_b_150k: float,
) -> str:
    end_cash_a = comparison.cumulative_cash_a[-1]
    end_cash_b = comparison.cumulative_cash_b[-1]
    extra_cash_for_a = max(0.0, end_cash_a - end_cash_b)
    oop_saving_if_keep_a = max(0.0, oop_b_150k - oop_a_150k)

    if end_cash_a <= end_cash_b and oop_a_150k <= oop_b_150k:
        return (
            f"{setup_a.setup_name} is financially stronger in this model: "
            "lower/equal projected premiums and lower/equal out-of-pocket in the 150k scenario."
        )
    if end_cash_b <= end_cash_a and oop_b_150k <= oop_a_150k:
        return (
            f"{setup_b.setup_name} is financially stronger in this model: "
            "lower/equal projected premiums and lower/equal out-of-pocket in the 150k scenario."
        )
    if oop_saving_if_keep_a > 0 and extra_cash_for_a > 0:
        break_even = extra_cash_for_a / oop_saving_if_keep_a
        return (
            f"{setup_a.setup_name} buys more claim protection, but costs "
            f"{extra_cash_for_a:,.2f} more cash over projection. "
            f"At 150k-claim economics, it takes about {break_even:.2f} claim-events "
            "to break even on pure cash terms."
        )
    return (
        "Both setups involve trade-offs. Use the scenario table and opportunity-cost chart "
        "to decide based on your risk tolerance and provider-path assumptions."
    )


def to_band_dicts(bands: Iterable[PremiumBand]) -> List[Dict[str, float]]:
    return [asdict(b) for b in sort_bands(bands)]
