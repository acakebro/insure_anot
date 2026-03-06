from __future__ import annotations

from datetime import date

from insure_anot.defaults import default_setup_a, default_setup_b
from insure_anot.engine import (
    calculate_age_next_birthday,
    compute_claim_outcome,
    premium_for_age,
    project_setup,
)
from insure_anot.types import PolicySetup, PremiumBand, ProjectionAssumptions
from insure_anot.types import ClaimScenario


def test_anb_logic_for_friend_case() -> None:
    dob = date(1996, 10, 9)
    as_of = date(2026, 3, 6)
    assert calculate_age_next_birthday(dob, as_of) == 30


def test_default_premium_sum_at_age_30() -> None:
    setup_a = default_setup_a()
    premiums, _ = premium_for_age(setup_a, age=30, carry_forward_last_band=True)
    assert round(premiums["total"], 2) == 1188.80


def test_oop_without_rider_for_150k_private_example() -> None:
    setup_b = default_setup_b()
    out = compute_claim_outcome(
        setup_b, scenario=ClaimScenario(bill_amount=150000, care_path_key="partner_panel")
    )
    assert round(out["final_oop"], 2) == 19500.00


def test_oop_with_rider_for_150k_private_example() -> None:
    setup_a = default_setup_a()
    out = compute_claim_outcome(
        setup_a, scenario=ClaimScenario(bill_amount=150000, care_path_key="partner_panel")
    )
    assert round(out["final_oop"], 2) == 6500.00


def test_provider_toggle_changes_outcome_materially() -> None:
    setup_a = default_setup_a()
    partner = compute_claim_outcome(
        setup_a, scenario=ClaimScenario(bill_amount=150000, care_path_key="partner_panel")
    )["final_oop"]
    non_panel = compute_claim_outcome(
        setup_a,
        scenario=ClaimScenario(
            bill_amount=150000, care_path_key="non_panel_conservative"
        ),
    )["final_oop"]
    assert non_panel > partner


def test_projection_carry_forward_warning_and_values() -> None:
    setup_a = default_setup_a()
    setup_b = default_setup_b()
    assumptions = ProjectionAssumptions(
        end_age=101,
        return_base=4.0,
        return_low=3.0,
        return_high=6.0,
        carry_forward_last_band=True,
    )
    result = project_setup(setup_a, setup_b, start_age=30, assumptions=assumptions)
    assert result.carry_forward_warning_a is True
    assert result.carry_forward_warning_b is True
    # Last known ANB row is 100; ANB 101 should carry-forward from ANB 100.
    assert round(result.premiums_total_a[-1], 2) == round(result.premiums_total_a[-2], 2)


def test_cash_and_total_investment_views_can_differ() -> None:
    setup_a = PolicySetup(
        setup_name="A",
        gsh_plan_name="GSH",
        gtc_plan_name="GTC",
        ghc_plan_name="GHC",
        include_gtc=False,
        include_ghc=False,
        premium_bands=[
            PremiumBand(
                age_from=30,
                age_to=30,
                gsh_total=600.0,
                gsh_cash=0.0,
                gtc_total=0.0,
                gtc_cash=0.0,
                ghc_total=0.0,
                ghc_cash=0.0,
            )
        ],
        care_paths=default_setup_a().care_paths,
    )
    setup_b = PolicySetup(
        setup_name="B",
        gsh_plan_name="GSH",
        gtc_plan_name="GTC",
        ghc_plan_name="GHC",
        include_gtc=False,
        include_ghc=False,
        premium_bands=[
            PremiumBand(
                age_from=30,
                age_to=30,
                gsh_total=500.0,
                gsh_cash=0.0,
                gtc_total=0.0,
                gtc_cash=0.0,
                ghc_total=0.0,
                ghc_cash=0.0,
            )
        ],
        care_paths=default_setup_b().care_paths,
    )
    result = project_setup(
        setup_a,
        setup_b,
        start_age=30,
        assumptions=ProjectionAssumptions(
            end_age=31,
            return_base=4.0,
            return_low=3.0,
            return_high=6.0,
            carry_forward_last_band=True,
        ),
    )
    assert result.invest_total_base[-1] > 0.0
    assert result.invest_cash_base[-1] == 0.0
