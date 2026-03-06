from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from insure_anot.defaults import (
    default_person_profile,
    default_setup_a,
    default_setup_b,
    default_setup_current_isp_only,
    default_setup_ge_full_suite,
)
from insure_anot.engine import (
    calculate_age_next_birthday,
    compute_claim_outcome,
    make_light_guidance,
    premium_for_age,
    project_investment_delta,
    project_setup,
)
from insure_anot.types import (
    CarePathParameters,
    ClaimScenario,
    PolicySetup,
    PremiumBand,
    ProjectionAssumptions,
)


def money(value: float) -> str:
    return f"S${value:,.2f}"


def escape_markdown_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
        .replace("$", "\\$")
    )


def clone_setup(setup: PolicySetup, setup_name: str) -> PolicySetup:
    cloned = deepcopy(setup)
    cloned.setup_name = setup_name
    return cloned


def get_default_setups(mode_key: str) -> tuple[PolicySetup, PolicySetup, PolicySetup]:
    if mode_key == "isp_vs_ge_full":
        return (
            clone_setup(
                default_setup_current_isp_only(),
                "Setup A (Current ISP Baseline - Income EIS Basic SG default)",
            ),
            clone_setup(default_setup_ge_full_suite(), "Setup B (Proposed GE Full Suite)"),
            clone_setup(default_setup_b(), "Setup C (GE Without GTC Rider)"),
        )
    if mode_key == "ge_full_vs_no_gtc":
        return (
            clone_setup(default_setup_ge_full_suite(), "Setup A (GE Full Suite)"),
            clone_setup(default_setup_b(), "Setup B (GE Without GTC Rider)"),
            clone_setup(default_setup_current_isp_only(), "Setup C (Current ISP Baseline)"),
        )
    return (
        clone_setup(default_setup_a(), "Setup A"),
        clone_setup(default_setup_b(), "Setup B"),
        clone_setup(default_setup_current_isp_only(), "Setup C"),
    )


def short_setup_summary(setup: PolicySetup) -> str:
    parts = [setup.gsh_plan_name]
    if setup.include_gtc:
        parts.append(setup.gtc_plan_name)
    if setup.include_ghc:
        parts.append(setup.ghc_plan_name)
    return " + ".join(parts)


def render_legend_and_guide() -> None:
    with st.expander("Legend & How This App Works (?)", expanded=False):
        st.markdown("**Legend**")
        legend_df = pd.DataFrame(
            [
                {"Term": "OOP", "Meaning": "Out-of-pocket amount paid by you for a claim event."},
                {
                    "Term": "ANB",
                    "Meaning": "Age Next Birthday. Insurance pricing usually follows this age basis.",
                },
                {"Term": "Cash Premium", "Meaning": "Portion of annual premium paid in cash."},
                {
                    "Term": "Total Premium",
                    "Meaning": "Cash + Medisave portions combined. Formula: Total = Cash + Medisave.",
                },
                {
                    "Term": "Anchor Claim",
                    "Meaning": "Primary claim scenario used for ranking/recommendation (default: S$100,000).",
                },
                {
                    "Term": "Opportunity Cost",
                    "Meaning": "Potential invested value of premium differences between setups.",
                },
                {
                    "Term": "Source Tags",
                    "Meaning": "POLICY-SOURCED DEFAULT means prefilled from policy docs; ASSUMPTION/SCENARIO means user modeling choice.",
                },
            ]
        )
        st.dataframe(legend_df, use_container_width=True, hide_index=True)

        st.markdown("**How to Use**")
        st.markdown(
            "1. Choose a preset in the sidebar, then edit Setup A / B / C tabs.\n"
            "2. Set projection assumptions and claim scenarios.\n"
            "3. Review claim OOP, premium projection, opportunity-cost charts, and 3-way ranking."
        )
        st.markdown("**Integrated Shield Payment Layers (Simplified)**")
        st.markdown(
            "1. Base ISP premium usually has Medisave-paid and cash top-up portions.\n"
            "2. Rider premium is usually additional cash premium.\n"
            "3. Optional hospital cash plans are separate add-ons."
        )
        st.caption(
            "Important: every section below this guide is recalculated live from your current inputs. "
            "If you change any setup parameter, the bottom-half results update automatically."
        )


def projection_quality(setup: PolicySetup, start_age: int, end_age: int) -> Dict[str, float]:
    bands = sorted(setup.premium_bands, key=lambda b: (b.age_from, b.age_to))
    if not bands:
        total_ages = max(0, end_age - start_age + 1)
        return {
            "total_ages": total_ages,
            "explicit_ages": 0,
            "carry_ages": 0,
            "missing_ages": total_ages,
            "explicit_pct": 0.0,
        }

    max_band_age = max(b.age_to for b in bands)
    explicit_ages = 0
    carry_ages = 0
    missing_ages = 0
    total_ages = max(0, end_age - start_age + 1)

    for age in range(start_age, end_age + 1):
        in_band = any(b.age_from <= age <= b.age_to for b in bands)
        if in_band:
            explicit_ages += 1
        elif age > max_band_age:
            carry_ages += 1
        else:
            missing_ages += 1

    explicit_pct = (explicit_ages / total_ages * 100.0) if total_ages > 0 else 0.0
    return {
        "total_ages": total_ages,
        "explicit_ages": explicit_ages,
        "carry_ages": carry_ages,
        "missing_ages": missing_ages,
        "explicit_pct": explicit_pct,
    }


def quality_flag(explicit_pct: float) -> str:
    if explicit_pct >= 90:
        return "High"
    if explicit_pct >= 60:
        return "Medium"
    return "Low"


def build_line_figure(
    x_values: List[int],
    series: List[dict],
    title: str,
    y_axis_title: str,
) -> go.Figure:
    fig = go.Figure()
    for item in series:
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=item["values"],
                mode="lines+markers",
                name=item["name"],
                line={
                    "width": item.get("width", 2),
                    "dash": item.get("dash", "solid"),
                    "color": item.get("color"),
                },
                marker={"size": item.get("marker_size", 4)},
                hovertemplate=f"{item['name']}: S$%{{y:,.2f}}<extra></extra>",
            )
        )

    fig.update_layout(
        title=title,
        hovermode="x unified",
        template="plotly_dark",
        margin={"l": 30, "r": 20, "t": 60, "b": 40},
        legend={"orientation": "h", "yanchor": "top", "y": -0.2, "xanchor": "left", "x": 0},
    )
    fig.update_xaxes(title="Age (ANB)", dtick=5)
    fig.update_yaxes(
        title=y_axis_title,
        tickprefix="S$",
        separatethousands=True,
    )
    return fig


def setup_to_premium_df(setup: PolicySetup) -> pd.DataFrame:
    rows = [
        {
            "age_from": b.age_from,
            "age_to": b.age_to,
            "gsh_total": b.gsh_total,
            "gsh_cash": b.gsh_cash,
            "gtc_total": b.gtc_total,
            "gtc_cash": b.gtc_cash,
            "ghc_total": b.ghc_total,
            "ghc_cash": b.ghc_cash,
        }
        for b in setup.premium_bands
    ]
    return pd.DataFrame(rows)


def setup_to_care_path_df(setup: PolicySetup) -> pd.DataFrame:
    rows = []
    for key, path in setup.care_paths.items():
        rows.append(
            {
                "path_key": key,
                "path_name": path.name,
                "deductible": path.deductible,
                "coinsurance_rate": path.coinsurance_rate,
                "rider_deductible_coverage_rate": path.rider_deductible_coverage_rate,
                "rider_coinsurance_coverage_rate": path.rider_coinsurance_coverage_rate,
                "rider_loss_limit": path.rider_loss_limit,
            }
        )
    return pd.DataFrame(rows)


def sanitize_premium_df(df: pd.DataFrame) -> pd.DataFrame:
    required = [
        "age_from",
        "age_to",
        "gsh_total",
        "gsh_cash",
        "gtc_total",
        "gtc_cash",
        "ghc_total",
        "ghc_cash",
    ]
    for col in required:
        if col not in df.columns:
            df[col] = 0
    df = df[required].copy()
    if df.empty:
        df.loc[0] = [30, 30, 550.06, 0.0, 468.70, 468.70, 170.04, 170.04]
    df = df.dropna(how="all")
    if df.empty:
        df.loc[0] = [30, 30, 550.06, 0.0, 468.70, 468.70, 170.04, 170.04]

    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["age_from"] = df["age_from"].astype(int)
    df["age_to"] = df["age_to"].astype(int)

    # Normalize invalid ranges quickly so downstream projection is deterministic.
    swap_mask = df["age_from"] > df["age_to"]
    df.loc[swap_mask, ["age_from", "age_to"]] = df.loc[swap_mask, ["age_to", "age_from"]].values

    numeric_cols = [c for c in required if c not in ("age_from", "age_to")]
    for col in numeric_cols:
        df[col] = df[col].clip(lower=0.0)

    return df.sort_values(["age_from", "age_to"]).reset_index(drop=True)


def sanitize_care_path_df(df: pd.DataFrame) -> pd.DataFrame:
    required = [
        "path_key",
        "path_name",
        "deductible",
        "coinsurance_rate",
        "rider_deductible_coverage_rate",
        "rider_coinsurance_coverage_rate",
        "rider_loss_limit",
    ]
    for col in required:
        if col not in df.columns:
            df[col] = ""
    df = df[required].copy()
    if df.empty:
        df.loc[0] = [
            "partner_panel",
            "Partnering institution + panel specialist",
            5000.0,
            0.10,
            0.30,
            0.50,
            6500.0,
        ]
        df.loc[1] = [
            "non_panel_conservative",
            "Non-panel / non-partner conservative path",
            5000.0,
            0.40,
            0.0,
            0.0,
            None,
        ]

    df["path_key"] = df["path_key"].astype(str).str.strip().replace("", pd.NA)
    missing_key_mask = df["path_key"].isna()
    for idx in df[missing_key_mask].index:
        df.at[idx, "path_key"] = f"path_{idx + 1}"

    df["path_name"] = df["path_name"].astype(str).str.strip().replace("", pd.NA)
    missing_name_mask = df["path_name"].isna()
    for idx in df[missing_name_mask].index:
        df.at[idx, "path_name"] = df.at[idx, "path_key"]

    numeric_cols = [
        "deductible",
        "coinsurance_rate",
        "rider_deductible_coverage_rate",
        "rider_coinsurance_coverage_rate",
        "rider_loss_limit",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in [
        "deductible",
        "coinsurance_rate",
        "rider_deductible_coverage_rate",
        "rider_coinsurance_coverage_rate",
    ]:
        df[col] = df[col].fillna(0.0).clip(lower=0.0)
    for col in [
        "coinsurance_rate",
        "rider_deductible_coverage_rate",
        "rider_coinsurance_coverage_rate",
    ]:
        df[col] = df[col].clip(upper=1.0)

    # Treat blank/zero/negative loss limit as no limit for conservative scenarios.
    df["rider_loss_limit"] = df["rider_loss_limit"].where(df["rider_loss_limit"] > 0, None)
    return df.reset_index(drop=True)


def premium_df_to_bands(df: pd.DataFrame) -> List[PremiumBand]:
    out: List[PremiumBand] = []
    for row in df.to_dict("records"):
        out.append(
            PremiumBand(
                age_from=int(row["age_from"]),
                age_to=int(row["age_to"]),
                gsh_total=float(row["gsh_total"]),
                gsh_cash=float(row["gsh_cash"]),
                gtc_total=float(row["gtc_total"]),
                gtc_cash=float(row["gtc_cash"]),
                ghc_total=float(row["ghc_total"]),
                ghc_cash=float(row["ghc_cash"]),
            )
        )
    return out


def care_df_to_paths(df: pd.DataFrame) -> Dict[str, CarePathParameters]:
    out: Dict[str, CarePathParameters] = {}
    for row in df.to_dict("records"):
        key = str(row["path_key"])
        loss_limit = row.get("rider_loss_limit")
        if pd.isna(loss_limit):
            loss_limit = None
        out[key] = CarePathParameters(
            name=str(row["path_name"]),
            deductible=float(row["deductible"]),
            coinsurance_rate=float(row["coinsurance_rate"]),
            rider_deductible_coverage_rate=float(row["rider_deductible_coverage_rate"]),
            rider_coinsurance_coverage_rate=float(row["rider_coinsurance_coverage_rate"]),
            rider_loss_limit=float(loss_limit) if loss_limit is not None else None,
        )
    return out


def render_setup_editor(prefix: str, default_setup: PolicySetup) -> PolicySetup:
    is_ge_default = "great supremehealth" in default_setup.gsh_plan_name.lower()
    is_income_default = "enhanced incomeshield" in default_setup.gsh_plan_name.lower()

    st.subheader(default_setup.setup_name)
    st.caption(
        "Source tags used below: `POLICY-SOURCED DEFAULT` = prefilled from policy tables, "
        "`ASSUMPTION/SCENARIO` = editable modeling choice."
    )
    setup_name = st.text_input(
        "Setup Name",
        value=default_setup.setup_name,
        key=f"{prefix}_setup_name",
    )
    col1, col2 = st.columns(2)
    with col1:
        st.caption("`ASSUMPTION/SCENARIO`")
        include_gtc = st.checkbox(
            "Include GTC Rider",
            value=default_setup.include_gtc,
            key=f"{prefix}_include_gtc",
        )
    with col2:
        st.caption("`ASSUMPTION/SCENARIO`")
        include_ghc = st.checkbox(
            "Include GHC Plan",
            value=default_setup.include_ghc,
            key=f"{prefix}_include_ghc",
        )

    with st.expander("Plan Labels", expanded=False):
        st.caption("`ASSUMPTION/SCENARIO` (display names only; does not change math)")
        gsh_plan_name = st.text_input(
            "GSH Plan Name",
            value=default_setup.gsh_plan_name,
            key=f"{prefix}_gsh_name",
        )
        gtc_plan_name = st.text_input(
            "GTC Plan Name",
            value=default_setup.gtc_plan_name,
            key=f"{prefix}_gtc_name",
        )
        ghc_plan_name = st.text_input(
            "GHC Plan Name",
            value=default_setup.ghc_plan_name,
            key=f"{prefix}_ghc_name",
        )

    with st.expander("Premium Age-Bands (Editable)", expanded=True):
        if is_ge_default:
            st.caption(
                "`POLICY-SOURCED DEFAULT` from GE premium tables. Overwrite if your setup is from another insurer."
            )
        elif is_income_default:
            st.caption(
                "`POLICY-SOURCED DEFAULT` from Income EIS Basic (SG) main-plan tables. "
                "Overwrite if your setup differs."
            )
        else:
            st.caption(
                "`POLICY-SOURCED DEFAULT` if applicable; otherwise treat as a scenario template and overwrite."
            )
        st.caption(
            "Columns are intentionally the same across Setup A/B/C for consistent comparison math."
        )
        if not include_gtc and not include_ghc:
            st.caption(
                "For ISP-only baseline, keep `gtc_total`, `gtc_cash`, `ghc_total`, `ghc_cash` at `0` "
                "(unless you intentionally model rider/add-on costs)."
            )
        st.caption(
            "Each row is an age band. Totals and cash are annual SGD values. "
            "Medisave is computed as total minus cash."
        )
        st.caption(
            "If your policy has ANB-by-ANB rates in PDF, add them here for accurate projections. "
            "If you only enter one row (e.g., age 30), future years will rely on carry-forward."
        )
        premium_df_default = setup_to_premium_df(default_setup)
        disabled_columns = []
        if not include_gtc:
            disabled_columns.extend(["gtc_total", "gtc_cash"])
        if not include_ghc:
            disabled_columns.extend(["ghc_total", "ghc_cash"])
        premium_df = st.data_editor(
            premium_df_default,
            key=f"{prefix}_premium_df",
            num_rows="dynamic",
            use_container_width=True,
            disabled=disabled_columns,
        )
        premium_df = sanitize_premium_df(pd.DataFrame(premium_df))
        if not include_gtc:
            premium_df["gtc_total"] = 0.0
            premium_df["gtc_cash"] = 0.0
        if not include_ghc:
            premium_df["ghc_total"] = 0.0
            premium_df["ghc_cash"] = 0.0

    with st.expander("Care Path Parameters (Editable)", expanded=True):
        st.caption("`MIXED`: policy terms + scenario assumptions (provider pathway, panel usage, conservative stress-case).")
        st.caption(
            "Rates are decimals (0.10 = 10%). "
            "Set rider_loss_limit blank to represent no cap."
        )
        care_df_default = setup_to_care_path_df(default_setup)
        care_df = st.data_editor(
            care_df_default,
            key=f"{prefix}_care_df",
            num_rows="dynamic",
            use_container_width=True,
        )
        care_df = sanitize_care_path_df(pd.DataFrame(care_df))

    return PolicySetup(
        setup_name=setup_name,
        gsh_plan_name=gsh_plan_name,
        gtc_plan_name=gtc_plan_name,
        ghc_plan_name=ghc_plan_name,
        include_gtc=include_gtc,
        include_ghc=include_ghc,
        premium_bands=premium_df_to_bands(premium_df),
        care_paths=care_df_to_paths(care_df),
    )


def build_claim_table(
    setup_a: PolicySetup,
    setup_b: PolicySetup,
    setup_c: PolicySetup,
    bills: List[float],
    selected_paths: List[str],
) -> pd.DataFrame:
    rows = []
    for path_key in selected_paths:
        for bill in bills:
            outcome_a = compute_claim_outcome(
                setup_a, ClaimScenario(bill_amount=bill, care_path_key=path_key)
            )
            outcome_b = compute_claim_outcome(
                setup_b, ClaimScenario(bill_amount=bill, care_path_key=path_key)
            )
            outcome_c = compute_claim_outcome(
                setup_c, ClaimScenario(bill_amount=bill, care_path_key=path_key)
            )
            rows.append(
                {
                    "care_path": setup_a.care_paths[path_key].name,
                    "bill_amount": bill,
                    "oop_setup_a": outcome_a["final_oop"],
                    "oop_setup_b": outcome_b["final_oop"],
                    "oop_setup_c": outcome_c["final_oop"],
                    "oop_delta_a_minus_b": outcome_a["final_oop"] - outcome_b["final_oop"],
                    "oop_delta_a_minus_c": outcome_a["final_oop"] - outcome_c["final_oop"],
                    "oop_delta_b_minus_c": outcome_b["final_oop"] - outcome_c["final_oop"],
                    "rider_savings_setup_a": outcome_a["rider_savings"],
                    "rider_savings_setup_b": outcome_b["rider_savings"],
                    "rider_savings_setup_c": outcome_c["rider_savings"],
                }
            )
    return pd.DataFrame(rows)


def project_single_setup(
    setup: PolicySetup,
    start_age: int,
    end_age: int,
    carry_forward_last_band: bool,
) -> Dict[str, object]:
    ages = list(range(start_age, end_age + 1))
    total: List[float] = []
    cash: List[float] = []
    cumulative_total: List[float] = []
    cumulative_cash: List[float] = []
    carry_warning = False
    run_total = 0.0
    run_cash = 0.0

    for age in ages:
        prem, used_carry = premium_for_age(setup, age, carry_forward_last_band)
        total.append(float(prem["total"]))
        cash.append(float(prem["cash"]))
        run_total += float(prem["total"])
        run_cash += float(prem["cash"])
        cumulative_total.append(run_total)
        cumulative_cash.append(run_cash)
        carry_warning = carry_warning or used_carry

    return {
        "ages": ages,
        "total": total,
        "cash": cash,
        "cum_total": cumulative_total,
        "cum_cash": cumulative_cash,
        "carry_warning": carry_warning,
    }


def make_three_way_recommendation(
    ranking_df: pd.DataFrame,
    anchor_bill: float,
    anchor_path_name: str,
) -> Dict[str, str]:
    cheapest = ranking_df.sort_values("end_cash", ascending=True).iloc[0]
    safest = ranking_df.sort_values("anchor_oop", ascending=True).iloc[0]
    balanced = ranking_df.sort_values(
        ["combined_score", "cost_rank", "protection_rank"], ascending=[True, True, True]
    ).iloc[0]

    if cheapest["setup_name"] == safest["setup_name"]:
        headline = f"Recommendation: {cheapest['setup_name']}"
        reason = (
            f"It is both the cheapest projected cashflow choice and the lowest anchor "
            f"out-of-pocket option for {money(anchor_bill)} under {anchor_path_name}."
        )
        conclusion = (
            "This setup dominates on cost and protection in the current assumptions. "
            "Still validate provider-path and policy wording details before final decision."
        )
    else:
        headline = "Recommendation: use the balanced pick, then confirm your priority"
        reason = (
            f"Cheapest setup: {cheapest['setup_name']} ({money(float(cheapest['end_cash']))} projected cash). "
            f"Best protection setup: {safest['setup_name']} "
            f"({money(float(safest['anchor_oop']))} anchor out-of-pocket). "
            f"Balanced pick by combined rank: {balanced['setup_name']}."
        )
        conclusion = (
            "If you optimize pure long-run cost, choose the cheapest setup. "
            "If you optimize worst-case claim cash outlay, choose the best-protection setup."
        )

    return {
        "headline": headline,
        "reason": reason,
        "conclusion": conclusion,
    }


def main() -> None:
    st.set_page_config(page_title="Insure Anot v1", layout="wide")
    st.title("Insure Anot?: Hospital Plan & Rider Decision Calculator")
    st.caption(
        "3-way comparison mode: edit Setup A / B / C and rank all options by projected cashflow and claim exposure."
    )
    st.info(
        "Default data is preloaded from policy sources: GE GSH/GTC full ANB bands and "
        "Income Enhanced IncomeShield Basic (SG) main-plan bands (effective 1 Oct 2025). "
        "GHC Plan A uses the screenshot annual value (S$170.04) as a carry-forward default, "
        "and remains editable."
    )
    render_legend_and_guide()

    person = default_person_profile()
    mode_options = {
        "Current ISP vs Proposed GE Full Suite (Recommended)": "isp_vs_ge_full",
        "GE Full Suite vs GE Without GTC Rider": "ge_full_vs_no_gtc",
    }

    with st.sidebar:
        st.header("Comparison Preset")
        selected_mode_label = st.selectbox(
            "Comparison Mode",
            list(mode_options.keys()),
            index=0,
        )
        selected_mode_key = mode_options[selected_mode_label]
        st.caption(
            "Setup A is baseline, Setup B is primary alternative, Setup C is optional third scenario."
        )
        st.markdown("---")

        st.header("Profile & Assumptions")
        dob = st.date_input("Date of Birth", value=person.date_of_birth)
        projection_start = st.date_input(
            "Projection Start Date", value=person.projection_start_date
        )
        anb = calculate_age_next_birthday(dob, projection_start)
        st.metric("Age Next Birthday (ANB)", anb)

        default_end_age = min(100, max(anb, 80))
        end_age = st.slider(
            "Projection End Age", min_value=anb, max_value=100, value=default_end_age
        )
        return_base = st.number_input(
            "Base Return %", min_value=0.0, max_value=20.0, value=4.24, step=0.1
        )
        return_low = st.number_input(
            "Low Return %", min_value=0.0, max_value=20.0, value=3.0, step=0.1
        )
        return_high = st.number_input(
            "High Return %", min_value=0.0, max_value=20.0, value=6.0, step=0.1
        )

        st.markdown("---")
        st.subheader("Claim Scenario Inputs")
        st.caption(
            "Use one primary bill scenario for decision ranking. "
            "You can optionally add one extra bill scenario for comparison."
        )
        primary_bill = st.number_input(
            "Primary Bill Scenario (SGD)",
            min_value=1000.0,
            value=100000.0,
            step=1000.0,
            format="%.0f",
            help=(
                "Main hospital bill used for ranking, recommendation, and self-fund checks. "
                "Example: 100000 means a S$100,000 claim scenario."
            ),
        )
        additional_bill = st.number_input(
            "Optional Additional Bill Scenario (SGD)",
            min_value=0.0,
            value=0.0,
            step=1000.0,
            format="%.0f",
            help=(
                "Enter 0 to ignore. If you enter 150000, claim results will also show a "
                "S$150,000 scenario row."
            ),
        )

    default_a, default_b, default_c = get_default_setups(selected_mode_key)

    tab_a, tab_b, tab_c = st.tabs(["Setup A", "Setup B", "Setup C"])
    with tab_a:
        setup_a = render_setup_editor(f"{selected_mode_key}_setup_a", default_a)
    with tab_b:
        setup_b = render_setup_editor(f"{selected_mode_key}_setup_b", default_b)
    with tab_c:
        setup_c = render_setup_editor(f"{selected_mode_key}_setup_c", default_c)

    st.markdown("## What Setup A / B / C Means")
    st.caption(f"Active preset: {selected_mode_label}")
    if selected_mode_key == "isp_vs_ge_full":
        st.warning(
            "Important: in this preset, Setup A defaults to Income Enhanced IncomeShield Basic (SG) "
            "main-plan rates and no rider/cash plan. If your true current ISP is different, overwrite "
            "Setup A Premium Age-Bands and Care Path Parameters with your own policy values."
        )
    intro_a, intro_b, intro_c = st.columns(3)
    with intro_a:
        st.markdown(f"**Setup A**: `{setup_a.setup_name}`")
        st.write(short_setup_summary(setup_a))
    with intro_b:
        st.markdown(f"**Setup B**: `{setup_b.setup_name}`")
        st.write(short_setup_summary(setup_b))
    with intro_c:
        st.markdown(f"**Setup C**: `{setup_c.setup_name}`")
        st.write(short_setup_summary(setup_c))
    st.caption(
        "Interpretation: rank all 3 setups by projected cumulative cash and anchor-claim out-of-pocket, "
        "then decide whether your priority is long-run cost or worst-case protection."
    )
    st.info(
        "Everything below is dynamic. The results sections are not fixed templates; "
        "they update whenever Setup A/B/C or assumptions change."
    )

    common_paths = [
        key
        for key in setup_a.care_paths.keys()
        if key in setup_b.care_paths and key in setup_c.care_paths
    ]
    if not common_paths:
        st.error("No overlapping care-path keys across Setup A, Setup B, and Setup C.")
        st.stop()

    selected_paths = st.multiselect(
        "Care Paths to Simulate",
        options=common_paths,
        default=["partner_panel"] if "partner_panel" in common_paths else [common_paths[0]],
        format_func=lambda k: setup_a.care_paths[k].name,
    )
    if not selected_paths:
        st.warning("Please select at least one care path.")
        st.stop()

    bills = sorted(
        {float(primary_bill)} | ({float(additional_bill)} if additional_bill > 0 else set())
    )
    if not bills:
        st.warning("Please choose at least one bill amount.")
        st.stop()

    assumptions = ProjectionAssumptions(
        end_age=end_age,
        return_base=return_base,
        return_low=return_low,
        return_high=return_high,
        carry_forward_last_band=True,
    )

    projection_a = project_single_setup(setup_a, anb, end_age, True)
    projection_b = project_single_setup(setup_b, anb, end_age, True)
    projection_c = project_single_setup(setup_c, anb, end_age, True)
    ages = projection_a["ages"]

    quality_a = projection_quality(setup_a, anb, end_age)
    quality_b = projection_quality(setup_b, anb, end_age)
    quality_c = projection_quality(setup_c, anb, end_age)

    st.markdown("## Projection Accuracy Audit")
    quality_df = pd.DataFrame(
        [
            {
                "Setup": "Setup A",
                "Name": setup_a.setup_name,
                "Explicit Age Coverage": f"{quality_a['explicit_ages']}/{quality_a['total_ages']} ({quality_a['explicit_pct']:.1f}%)",
                "Carry-Forward Ages": int(quality_a["carry_ages"]),
                "Missing Ages": int(quality_a["missing_ages"]),
                "Quality": quality_flag(float(quality_a["explicit_pct"])),
            },
            {
                "Setup": "Setup B",
                "Name": setup_b.setup_name,
                "Explicit Age Coverage": f"{quality_b['explicit_ages']}/{quality_b['total_ages']} ({quality_b['explicit_pct']:.1f}%)",
                "Carry-Forward Ages": int(quality_b["carry_ages"]),
                "Missing Ages": int(quality_b["missing_ages"]),
                "Quality": quality_flag(float(quality_b["explicit_pct"])),
            },
            {
                "Setup": "Setup C",
                "Name": setup_c.setup_name,
                "Explicit Age Coverage": f"{quality_c['explicit_ages']}/{quality_c['total_ages']} ({quality_c['explicit_pct']:.1f}%)",
                "Carry-Forward Ages": int(quality_c["carry_ages"]),
                "Missing Ages": int(quality_c["missing_ages"]),
                "Quality": quality_flag(float(quality_c["explicit_pct"])),
            },
        ]
    )
    st.dataframe(quality_df, use_container_width=True, hide_index=True)

    min_explicit_pct = min(
        float(quality_a["explicit_pct"]),
        float(quality_b["explicit_pct"]),
        float(quality_c["explicit_pct"]),
    )
    if min_explicit_pct < 90:
        st.warning(
            "Premium projection is only as accurate as the age-band rows you entered. "
            "At least one setup has incomplete explicit age coverage, so long-run projection values may be understated or overstated."
        )
        st.caption(
            "To improve accuracy, copy full ANB premium rates from your policy PDF into each setup's Premium Age-Bands table."
        )

    current_a, _ = premium_for_age(setup_a, anb, True)
    current_b, _ = premium_for_age(setup_b, anb, True)
    current_c, _ = premium_for_age(setup_c, anb, True)

    st.markdown("## Snapshot at Start Age")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.metric("Setup A Annual Total", money(current_a["total"]))
        st.metric("Setup A Annual Cash", money(current_a["cash"]))
    with s2:
        st.metric("Setup B Annual Total", money(current_b["total"]))
        st.metric("Setup B Annual Cash", money(current_b["cash"]))
    with s3:
        st.metric("Setup C Annual Total", money(current_c["total"]))
        st.metric("Setup C Annual Cash", money(current_c["cash"]))

    if (
        bool(projection_a["carry_warning"])
        or bool(projection_b["carry_warning"])
        or bool(projection_c["carry_warning"])
    ):
        st.warning(
            "Projection used carry-forward beyond last age-band for at least one setup. "
            "Add more age-band rows for better long-run accuracy."
        )

    st.markdown("## Claim Scenario Results")
    claim_table = build_claim_table(setup_a, setup_b, setup_c, bills, selected_paths)
    display_claim = claim_table.copy()
    numeric_cols = [
        "bill_amount",
        "oop_setup_a",
        "oop_setup_b",
        "oop_setup_c",
        "oop_delta_a_minus_b",
        "oop_delta_a_minus_c",
        "oop_delta_b_minus_c",
        "rider_savings_setup_a",
        "rider_savings_setup_b",
        "rider_savings_setup_c",
    ]
    for col in numeric_cols:
        display_claim[col] = display_claim[col].map(lambda x: round(float(x), 2))
    display_claim = display_claim.rename(
        columns={
            "care_path": "Care Path",
            "bill_amount": "Bill Amount (SGD)",
            "oop_setup_a": "Out-of-Pocket (OOP) - Setup A",
            "oop_setup_b": "Out-of-Pocket (OOP) - Setup B",
            "oop_setup_c": "Out-of-Pocket (OOP) - Setup C",
            "oop_delta_a_minus_b": "OOP Delta (A - B)",
            "oop_delta_a_minus_c": "OOP Delta (A - C)",
            "oop_delta_b_minus_c": "OOP Delta (B - C)",
            "rider_savings_setup_a": "Rider Savings - Setup A",
            "rider_savings_setup_b": "Rider Savings - Setup B",
            "rider_savings_setup_c": "Rider Savings - Setup C",
        }
    )
    st.dataframe(display_claim, use_container_width=True)

    # Anchor recommendation uses primary bill input and default partner-panel path when available.
    anchor_path = "partner_panel" if "partner_panel" in common_paths else selected_paths[0]
    anchor_bill = float(primary_bill)
    oop_a_anchor = compute_claim_outcome(
        setup_a, ClaimScenario(bill_amount=anchor_bill, care_path_key=anchor_path)
    )["final_oop"]
    oop_b_anchor = compute_claim_outcome(
        setup_b, ClaimScenario(bill_amount=anchor_bill, care_path_key=anchor_path)
    )["final_oop"]
    oop_c_anchor = compute_claim_outcome(
        setup_c, ClaimScenario(bill_amount=anchor_bill, care_path_key=anchor_path)
    )["final_oop"]

    st.markdown("## Premium Projection")
    premium_df = pd.DataFrame(
        {
            "age": ages,
            "setup_a_total": projection_a["total"],
            "setup_b_total": projection_b["total"],
            "setup_c_total": projection_c["total"],
            "setup_a_cash": projection_a["cash"],
            "setup_b_cash": projection_b["cash"],
            "setup_c_cash": projection_c["cash"],
            "cum_total_a": projection_a["cum_total"],
            "cum_total_b": projection_b["cum_total"],
            "cum_total_c": projection_c["cum_total"],
            "cum_cash_a": projection_a["cum_cash"],
            "cum_cash_b": projection_b["cum_cash"],
            "cum_cash_c": projection_c["cum_cash"],
        }
    )
    annual_fig = build_line_figure(
        x_values=ages,
        title="Annual Premium Projection (Total and Cash)",
        y_axis_title="Annual Premium (SGD)",
        series=[
            {"name": "Setup A Total", "values": premium_df["setup_a_total"], "color": "#3B82F6"},
            {"name": "Setup B Total", "values": premium_df["setup_b_total"], "color": "#EF4444"},
            {"name": "Setup C Total", "values": premium_df["setup_c_total"], "color": "#22C55E"},
            {
                "name": "Setup A Cash",
                "values": premium_df["setup_a_cash"],
                "color": "#93C5FD",
                "dash": "dot",
            },
            {
                "name": "Setup B Cash",
                "values": premium_df["setup_b_cash"],
                "color": "#FCA5A5",
                "dash": "dot",
            },
            {
                "name": "Setup C Cash",
                "values": premium_df["setup_c_cash"],
                "color": "#86EFAC",
                "dash": "dot",
            },
        ],
    )
    cumulative_fig = build_line_figure(
        x_values=ages,
        title="Cumulative Premium Projection (Total and Cash)",
        y_axis_title="Cumulative Premium (SGD)",
        series=[
            {"name": "Setup A Cumulative Total", "values": premium_df["cum_total_a"], "color": "#3B82F6"},
            {"name": "Setup B Cumulative Total", "values": premium_df["cum_total_b"], "color": "#EF4444"},
            {"name": "Setup C Cumulative Total", "values": premium_df["cum_total_c"], "color": "#22C55E"},
            {
                "name": "Setup A Cumulative Cash",
                "values": premium_df["cum_cash_a"],
                "color": "#93C5FD",
                "dash": "dot",
            },
            {
                "name": "Setup B Cumulative Cash",
                "values": premium_df["cum_cash_b"],
                "color": "#FCA5A5",
                "dash": "dot",
            },
            {
                "name": "Setup C Cumulative Cash",
                "values": premium_df["cum_cash_c"],
                "color": "#86EFAC",
                "dash": "dot",
            },
        ],
    )
    st.plotly_chart(annual_fig, use_container_width=True)
    st.plotly_chart(cumulative_fig, use_container_width=True)

    setup_projection_map = {
        "Setup A": {"setup": setup_a, "projection": projection_a, "anchor_oop": oop_a_anchor},
        "Setup B": {"setup": setup_b, "projection": projection_b, "anchor_oop": oop_b_anchor},
        "Setup C": {"setup": setup_c, "projection": projection_c, "anchor_oop": oop_c_anchor},
    }

    st.markdown("## Opportunity Cost")
    st.caption(
        "Note: 'Insurance Multiplier' (coverage / cash value) is a life-policy conversion metric "
        "and is not used in this hospital-plan module."
    )
    i1, i2 = st.columns(2)
    with i1:
        reference_label = st.selectbox(
            "Reference Setup (the setup you would choose instead)",
            list(setup_projection_map.keys()),
            index=0,
        )
    compare_candidates = [k for k in setup_projection_map.keys() if k != reference_label]
    with i2:
        compared_label = st.selectbox(
            "Compared Setup (opportunity cost measured against reference)",
            compare_candidates,
            index=0,
        )

    reference_setup = setup_projection_map[reference_label]["setup"]
    compared_setup = setup_projection_map[compared_label]["setup"]
    reference_series = setup_projection_map[reference_label]["projection"]
    compared_series = setup_projection_map[compared_label]["projection"]
    invest_cash_low = project_investment_delta(
        compared_series["cash"], reference_series["cash"], assumptions.return_low
    )
    invest_cash_base = project_investment_delta(
        compared_series["cash"], reference_series["cash"], assumptions.return_base
    )
    invest_cash_high = project_investment_delta(
        compared_series["cash"], reference_series["cash"], assumptions.return_high
    )
    invest_total_low = project_investment_delta(
        compared_series["total"], reference_series["total"], assumptions.return_low
    )
    invest_total_base = project_investment_delta(
        compared_series["total"], reference_series["total"], assumptions.return_base
    )
    invest_total_high = project_investment_delta(
        compared_series["total"], reference_series["total"], assumptions.return_high
    )

    invest_df = pd.DataFrame(
        {
            "age": ages,
            "cash_low": invest_cash_low,
            "cash_base": invest_cash_base,
            "cash_high": invest_cash_high,
            "total_low": invest_total_low,
            "total_base": invest_total_base,
            "total_high": invest_total_high,
        }
    )
    st.caption(
        f"Opportunity cost shown for choosing {compared_label} instead of {reference_label}."
    )

    delta_total_now = float(compared_series["total"][0] - reference_series["total"][0])
    delta_cash_now = float(compared_series["cash"][0] - reference_series["cash"][0])
    delta_medisave_now = delta_total_now - delta_cash_now
    delta_explanation = (
        f"Total premium = Medisave + Cash. At ANB {anb}, "
        f"delta ({compared_label} - {reference_label}) is "
        f"{money(delta_total_now)} total = {money(delta_cash_now)} cash + {money(delta_medisave_now)} Medisave."
    )
    st.markdown(f"**{escape_markdown_text(delta_explanation)}**")

    cash_fig = build_line_figure(
        x_values=ages,
        title="Invested Premium Difference (Cash Outlay Only)",
        y_axis_title="Projected Investment Value (SGD)",
        series=[
            {"name": "Low Return", "values": invest_df["cash_low"], "color": "#FCA5A5"},
            {"name": "Base Return", "values": invest_df["cash_base"], "color": "#93C5FD"},
            {"name": "High Return", "values": invest_df["cash_high"], "color": "#3B82F6"},
        ],
    )
    st.plotly_chart(cash_fig, use_container_width=True)

    same_cash_total = (
        all(abs(a - b) < 1e-9 for a, b in zip(invest_cash_low, invest_total_low))
        and all(abs(a - b) < 1e-9 for a, b in zip(invest_cash_base, invest_total_base))
        and all(abs(a - b) < 1e-9 for a, b in zip(invest_cash_high, invest_total_high))
    )
    if same_cash_total:
        st.info(
            "Cash-only and Total-premium opportunity-cost views are identical in this setup pair "
            "because the compared-vs-reference premium delta is effectively all cash (very small/no Medisave delta)."
        )

    with st.expander("Advanced View: Include Medisave Portion in Opportunity Cost", expanded=False):
        st.caption(
            "Use this only if you also want to treat Medisave premium differences as economic opportunity cost."
        )
        total_fig = build_line_figure(
            x_values=ages,
            title="Invested Premium Difference (Total Premium = Cash + Medisave)",
            y_axis_title="Projected Investment Value (SGD)",
            series=[
                {"name": "Low Return", "values": invest_df["total_low"], "color": "#FCA5A5"},
                {"name": "Base Return", "values": invest_df["total_base"], "color": "#93C5FD"},
                {"name": "High Return", "values": invest_df["total_high"], "color": "#3B82F6"},
            ],
        )
        st.plotly_chart(total_fig, use_container_width=True)

    # Optional pairwise guidance for the selected opportunity-cost pair.
    pair_result = project_setup(
        compared_setup,
        reference_setup,
        anb,
        assumptions,
    )
    pair_guidance = make_light_guidance(
        compared_setup,
        reference_setup,
        pair_result,
        float(setup_projection_map[compared_label]["anchor_oop"]),
        float(setup_projection_map[reference_label]["anchor_oop"]),
    )
    st.info(
        escape_markdown_text(f"Pair Guidance ({compared_label} vs {reference_label}): {pair_guidance}")
    )
    st.caption(
        "How to read: opportunity cost uses premium difference (Compared - Reference). "
        "If Compared is more expensive, that difference is treated as the yearly investable amount."
    )

    st.markdown("### Same-Scenario Self-Fund Check")
    claim_age_default = min(max(anb, 50), end_age)
    claim_age = st.slider(
        "Assumed claim age for this check",
        min_value=anb,
        max_value=end_age,
        value=claim_age_default,
    )
    claim_path_for_check = st.selectbox(
        "Care path for this check",
        options=selected_paths,
        index=0,
        format_func=lambda k: setup_a.care_paths[k].name,
        key="self_fund_claim_path",
    )
    claim_bill_for_check = float(primary_bill)
    claim_age_index = ages.index(claim_age)
    invested_pot_at_claim_age = float(invest_cash_base[claim_age_index])
    invested_principal_at_claim_age = float(
        sum(
            max(0.0, float(compared_series["cash"][idx]) - float(reference_series["cash"][idx]))
            for idx in range(claim_age_index + 1)
        )
    )
    invested_gain_at_claim_age = invested_pot_at_claim_age - invested_principal_at_claim_age

    reference_cash_paid_to_date = float(reference_series["cum_cash"][claim_age_index])
    compared_cash_paid_to_date = float(compared_series["cum_cash"][claim_age_index])
    reference_total_paid_to_date = float(reference_series["cum_total"][claim_age_index])
    compared_total_paid_to_date = float(compared_series["cum_total"][claim_age_index])

    reference_claim = compute_claim_outcome(
        reference_setup,
        ClaimScenario(bill_amount=claim_bill_for_check, care_path_key=claim_path_for_check),
    )
    compared_claim = compute_claim_outcome(
        compared_setup,
        ClaimScenario(bill_amount=claim_bill_for_check, care_path_key=claim_path_for_check),
    )
    remaining_after_reference_oop = invested_pot_at_claim_age - float(reference_claim["final_oop"])
    reference_cash_burden_now = reference_cash_paid_to_date + float(reference_claim["final_oop"])
    compared_cash_burden_now = compared_cash_paid_to_date + float(compared_claim["final_oop"])

    sf1, sf2, sf3 = st.columns(3)
    with sf1:
        st.metric(
            f"Invested Pot at Age {claim_age} (Base Return)",
            money(invested_pot_at_claim_age),
        )
    with sf2:
        st.metric(
            f"OOP if You Choose {reference_label}",
            money(float(reference_claim["final_oop"])),
        )
    with sf3:
        st.metric(
            f"OOP if You Choose {compared_label}",
            money(float(compared_claim["final_oop"])),
        )

    st.markdown("#### Premiums Paid To Claim Age")
    premium_paid_df = pd.DataFrame(
        [
            {
                "Setup": reference_label,
                "Cash Premium Paid to Claim Age": money(reference_cash_paid_to_date),
                "Total Premium Paid to Claim Age": money(reference_total_paid_to_date),
            },
            {
                "Setup": compared_label,
                "Cash Premium Paid to Claim Age": money(compared_cash_paid_to_date),
                "Total Premium Paid to Claim Age": money(compared_total_paid_to_date),
            },
        ]
    )
    st.dataframe(premium_paid_df, use_container_width=True, hide_index=True)
    premium_delta_col1, premium_delta_col2 = st.columns(2)
    with premium_delta_col1:
        st.metric(
            "Cash Premium Delta (Compared - Reference)",
            money(compared_cash_paid_to_date - reference_cash_paid_to_date),
        )
    with premium_delta_col2:
        st.metric(
            "Total Premium Delta (Compared - Reference)",
            money(compared_total_paid_to_date - reference_total_paid_to_date),
        )

    st.markdown("#### Investment Build-Up (Cash Gap Strategy)")
    i_cap1, i_cap2 = st.columns(2)
    with i_cap1:
        st.metric(
            f"Invested Capital Contributed by Age {claim_age}",
            money(invested_principal_at_claim_age),
        )
    with i_cap2:
        st.metric(
            f"Investment Gain by Age {claim_age} (Base Return)",
            money(invested_gain_at_claim_age),
        )

    st.markdown("#### Cash Burden At Claim Age (Premium Paid + OOP)")
    cash_burden_df = pd.DataFrame(
        [
            {
                "Setup": reference_label,
                "Cash Premium Paid to Claim Age": money(reference_cash_paid_to_date),
                "OOP for Claim Scenario": money(float(reference_claim["final_oop"])),
                "Cash Burden (Premium + OOP)": money(reference_cash_burden_now),
            },
            {
                "Setup": compared_label,
                "Cash Premium Paid to Claim Age": money(compared_cash_paid_to_date),
                "OOP for Claim Scenario": money(float(compared_claim["final_oop"])),
                "Cash Burden (Premium + OOP)": money(compared_cash_burden_now),
            },
        ]
    )
    st.dataframe(cash_burden_df, use_container_width=True, hide_index=True)

    if remaining_after_reference_oop >= 0:
        self_fund_success = (
            f"If you choose {reference_label}, invest the cash premium gap at base return, "
            f"and a {money(claim_bill_for_check)} claim happens at age {claim_age}, "
            f"you can pay OOP and still have about {money(remaining_after_reference_oop)} left."
        )
        st.success(escape_markdown_text(self_fund_success))
    else:
        self_fund_warning = (
            f"If you choose {reference_label}, invest the cash premium gap at base return, "
            f"and a {money(claim_bill_for_check)} claim happens at age {claim_age}, "
            f"you face about {money(abs(remaining_after_reference_oop))} shortfall after paying OOP."
        )
        st.warning(escape_markdown_text(self_fund_warning))

    ranking_df = pd.DataFrame(
        [
            {
                "setup_label": "Setup A",
                "setup_name": setup_a.setup_name,
                "end_cash": float(projection_a["cum_cash"][-1]),
                "end_total": float(projection_a["cum_total"][-1]),
                "anchor_oop": float(oop_a_anchor),
            },
            {
                "setup_label": "Setup B",
                "setup_name": setup_b.setup_name,
                "end_cash": float(projection_b["cum_cash"][-1]),
                "end_total": float(projection_b["cum_total"][-1]),
                "anchor_oop": float(oop_b_anchor),
            },
            {
                "setup_label": "Setup C",
                "setup_name": setup_c.setup_name,
                "end_cash": float(projection_c["cum_cash"][-1]),
                "end_total": float(projection_c["cum_total"][-1]),
                "anchor_oop": float(oop_c_anchor),
            },
        ]
    )
    ranking_df["cost_rank"] = ranking_df["end_cash"].rank(method="min", ascending=True).astype(int)
    ranking_df["protection_rank"] = ranking_df["anchor_oop"].rank(
        method="min", ascending=True
    ).astype(int)
    ranking_df["combined_score"] = ranking_df["cost_rank"] + ranking_df["protection_rank"]
    ranking_df = ranking_df.sort_values(
        ["combined_score", "cost_rank", "protection_rank"], ascending=[True, True, True]
    ).reset_index(drop=True)

    st.markdown("## End-Age Totals & 3-Way Ranking")
    r1, r2, r3 = st.columns(3)
    with r1:
        st.markdown(f"**Setup A Cash**: {money(float(projection_a['cum_cash'][-1]))}")
        st.markdown(f"**Setup A Anchor OOP**: {money(float(oop_a_anchor))}")
    with r2:
        st.markdown(f"**Setup B Cash**: {money(float(projection_b['cum_cash'][-1]))}")
        st.markdown(f"**Setup B Anchor OOP**: {money(float(oop_b_anchor))}")
    with r3:
        st.markdown(f"**Setup C Cash**: {money(float(projection_c['cum_cash'][-1]))}")
        st.markdown(f"**Setup C Anchor OOP**: {money(float(oop_c_anchor))}")

    ranking_display = ranking_df.copy()
    ranking_display["end_cash"] = ranking_display["end_cash"].map(money)
    ranking_display["end_total"] = ranking_display["end_total"].map(money)
    ranking_display["anchor_oop"] = ranking_display["anchor_oop"].map(money)
    ranking_display = ranking_display.rename(
        columns={
            "setup_label": "Setup",
            "setup_name": "Name",
            "end_cash": "Projected Cash @ End Age",
            "end_total": "Projected Total Premium @ End Age",
            "anchor_oop": f"Anchor Out-of-Pocket (OOP) @ {money(anchor_bill)}",
            "cost_rank": "Cost Rank",
            "protection_rank": "Protection Rank",
            "combined_score": "Combined Score",
        }
    )
    st.dataframe(ranking_display, use_container_width=True, hide_index=True)

    recommendation = make_three_way_recommendation(
        ranking_df,
        anchor_bill=anchor_bill,
        anchor_path_name=setup_a.care_paths[anchor_path].name,
    )

    st.markdown("## Recommendation")
    st.success(recommendation["headline"])
    st.markdown(escape_markdown_text(recommendation["reason"]))

    st.markdown("## Conclusion")
    st.markdown(escape_markdown_text(recommendation["conclusion"]))
    st.write(
        "Use the result as a decision aid, then validate final terms in the insurer benefit schedule "
        "and your exact provider pathway (panel vs non-panel)."
    )

    st.caption(
        "Disclaimer: This tool is a financial comparison aid based on user inputs and scenario assumptions. "
        "It is not medical, legal, or professional insurance advice."
    )


if __name__ == "__main__":
    main()
