"Use the results of a model to create genx inputs for an operational run"

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import typer

PERIOD_YEAR = {
    "p1": 2027,
    "p2": 2030,
    "p3": 2035,
    "p4": 2040,
    "p5": 2045,
    "p6": 2050,
}


def load_genx_inputs(path: Path) -> Dict[str, pd.DataFrame]:
    """Load CSV files from the specified path and return a dictionary of pandas
    DataFrames.

    Parameters
    ----------
    path : Path
        he path where the GenX CSV files for a scenario are located.

    Returns
    -------
    Dict[str, pd.DataFrame]
        A dictionary of pandas DataFrames, where the keys are the file names (without
        the extension) and the values are the corresponding DataFrames.
    """

    inputs = {}
    for fn in path.glob("*.csv*"):
        inputs[fn.stem] = pd.read_csv(fn, na_filter=False)

    return inputs


def fix_duplicate_region_in_resource_name(gens: pd.DataFrame) -> pd.DataFrame:
    for zone in gens["zone"].unique():
        double_name = f"{zone}_{zone}_"
        single_name = f"{zone}_"
        gens["resource_name"] = gens["resource_name"].str.replace(
            double_name, single_name
        )

    return gens


def load_final_capacity(path: Path, year: int) -> Tuple[Dict[str, pd.DataFrame], bool]:
    d = {}
    d["tx_exp"] = pd.read_csv(path / "transmission_expansion.csv")
    d["tx_exp"] = (
        d["tx_exp"]
        .query("planning_year<=@year")
        .groupby("line_name", as_index=False)["value"]
        .sum()
    )
    d["tx_exp"] = d["tx_exp"].rename(columns={"line_name": "transmission_path_name"})
    d["gens"] = pd.read_csv(path / "resource_capacity.csv")

    # Check for resources with cluster numbers that were due to a bug and fixed in some inputs
    corrected_inputs = True
    for resource in [
        "SPPC_landbasedwind_class3_moderate_115_anyQual_0",
        "PJMC_landbasedwind_class3_moderate_14_anyQual_0",
        "SRCE_landbasedwind_class3_moderate_14_anyQual_0",
    ]:
        if resource in d["gens"]["resource_name"].unique():
            corrected_inputs = False

    d["gens"] = fix_duplicate_region_in_resource_name(d["gens"])
    for h in [2, 4, 6, 8, 10]:
        d["gens"].loc[:, "resource_name"] = d["gens"]["resource_name"].str.replace(
            f"_{h}hour", ""
        )
    if "end_MWh" in d["gens"].columns:
        energy_cap = d["gens"].query("end_MWh > 0")
        energy_cap.drop(columns=["end_value"], inplace=True)
        energy_cap.rename(columns={"end_MWh": "end_value"}, inplace=True)
        energy_cap["unit"] = "MWh"
        d["gens"] = pd.concat([d["gens"], energy_cap], ignore_index=True)
    d["gens"].rename(columns={"resource_name": "Resource"}, inplace=True)
    d["gens"] = (
        d["gens"]
        .query("planning_year==@year")
        .groupby(["Resource", "unit"])["end_value"]
        .sum()
    )

    return d, corrected_inputs


def reverse_line_name(s: str) -> str:
    segments = s.split("_to_")
    return segments[-1] + "_to_" + segments[0]


def fix_tx_line_names(line_names: List[str], genx_names: List[str]) -> pd.DataFrame:
    if len(line_names) != len(genx_names):
        print("Not all lines are represented in the outputs")
    for idx, name in enumerate(line_names):
        if not name in genx_names:
            rev_name = reverse_line_name(name)
            if not rev_name in genx_names:
                raise ValueError(
                    f"The transmission line name {name} and its reverse do not match GenX line names"
                )
            line_names[idx] = rev_name
    return line_names


def fix_max_cap_violations(final_cap: np.array, max_cap: np.array) -> np.array:
    for idx, (cap, m_cap) in enumerate(zip(final_cap, max_cap)):
        if m_cap > 0 and cap > m_cap:
            final_cap[idx] = m_cap
    return final_cap


def remove_nonvariable_resources(df: pd.DataFrame):
    """
    Remove columns from the DataFrame where the standard deviation is exactly 0.

    Parameters:
    df (pd.DataFrame): DataFrame with each column as a timeseries of data.

    Returns:
    pd.DataFrame: DataFrame with columns filtered based on standard deviation.
    """
    # Create a boolean mask where columns have all values equal to 1
    all_one_columns = (df == 1).all()

    # Filter out columns where all values are equal to 1
    filtered_df = df.loc[:, ~all_one_columns]

    return filtered_df


def create_operational_genx_inputs(
    results_dict: Dict[str, pd.DataFrame],
    genx_dict: Dict[str, pd.DataFrame],
    co2_slack: int = 200,
    fixed_om_prefix: str = "",
    gen_data_only: bool = False,
) -> Dict[str, pd.DataFrame]:

    if "CO2_cap_slack" in genx_dict.keys():
        genx_dict["CO2_cap_slack"].loc[0, "PriceCap"] = co2_slack

    idx = pd.IndexSlice

    genx_dict["Generators_data"].set_index("Resource", inplace=True)
    # Add gen annuities to FOM and set New_Build to -1
    new_build_idx = (
        genx_dict["Generators_data"]
        .loc[genx_dict["Generators_data"]["New_Build"] == 1, :]
        .index
    )
    genx_dict["Generators_data"]["original_Fixed_OM_Cost_per_MWyr"] = genx_dict[
        "Generators_data"
    ]["Fixed_OM_Cost_per_MWyr"]
    genx_dict["Generators_data"]["original_Fixed_OM_Cost_per_MWhyr"] = genx_dict[
        "Generators_data"
    ]["Fixed_OM_Cost_per_MWhyr"]

    # Save base costs (without ITC)
    if fixed_om_prefix:
        genx_dict["Generators_data"].loc[
            :, f"{fixed_om_prefix}Fixed_OM_Cost_per_MWyr"
        ] = (genx_dict["Generators_data"].loc[:, "Fixed_OM_Cost_per_MWyr"].copy())
        genx_dict["Generators_data"].loc[
            :, f"{fixed_om_prefix}Fixed_OM_Cost_per_MWhyr"
        ] = (genx_dict["Generators_data"].loc[:, "Fixed_OM_Cost_per_MWhyr"].copy())

    genx_dict["Generators_data"].loc[
        new_build_idx, f"{fixed_om_prefix}Fixed_OM_Cost_per_MWyr"
    ] += genx_dict["Generators_data"].loc[new_build_idx, "Inv_Cost_per_MWyr"]
    genx_dict["Generators_data"].loc[
        new_build_idx, f"{fixed_om_prefix}Fixed_OM_Cost_per_MWhyr"
    ] += genx_dict["Generators_data"].loc[new_build_idx, "Inv_Cost_per_MWhyr"]
    genx_dict["Generators_data"]["New_Build"] = -1

    # Tranfer final capacity to input file
    for col in ["Existing_Cap_MW", "Existing_Cap_MWh"]:
        genx_dict["Generators_data"][col] = 0
    genx_dict["Generators_data"]["Existing_Cap_MW"] = (
        results_dict["gens"].loc[idx[:, "MW"]].round(2)
    )
    genx_dict["Generators_data"].fillna({"Existing_Cap_MW": 0}, inplace=True)
    if "MWh" in results_dict["gens"].index.get_level_values(1).unique():
        genx_dict["Generators_data"]["Existing_Cap_MWh"] = (
            results_dict["gens"].loc[idx[:, "MWh"]].round(2)
        )
        genx_dict["Generators_data"].fillna({"Existing_Cap_MWh": 0}, inplace=True)
        genx_dict["Generators_data"].loc[
            genx_dict["Generators_data"]["Existing_Cap_MW"] == 0, "Existing_Cap_MWh"
        ] = 0
    else:
        print("No energy storage capacity values are in the results")
    genx_dict["Generators_data"].loc[
        genx_dict["Generators_data"]["technology"] == "Hydroelectric Pumped Storage",
        "Existing_Cap_MWh",
    ] = (
        genx_dict["Generators_data"].loc[
            genx_dict["Generators_data"]["technology"]
            == "Hydroelectric Pumped Storage",
            "Existing_Cap_MW",
        ]
        * 15.5
    )

    genx_dict["Generators_data"]["Existing_Cap_MW"] = fix_max_cap_violations(
        genx_dict["Generators_data"]["Existing_Cap_MW"].values,
        genx_dict["Generators_data"]["Max_Cap_MW"].values,
    )

    genx_dict["Generators_data"].reset_index(inplace=True)

    if gen_data_only:
        return genx_dict

    # Check/fix transmission line names
    results_dict["tx_exp"]["transmission_path_name"] = fix_tx_line_names(
        results_dict["tx_exp"]["transmission_path_name"].to_list(),
        genx_dict["Network"]["transmission_path_name"].to_list(),
    )
    results_dict["tx_exp"].set_index("transmission_path_name", inplace=True)
    results_dict["tx_exp"] = (
        results_dict["tx_exp"]
        .reindex(index=genx_dict["Network"]["transmission_path_name"])
        .fillna(0)
    )
    line_names = [
        n
        for n in genx_dict["Network"]["transmission_path_name"]
        if n in results_dict["tx_exp"].index
    ]
    # new_tx = genx_dict["Network"].loc[:, "Line_Max_Flow_MW"].values - results_dict["tx_exp"].loc[line_names, "end_value"].values
    # new_tx_annuity =
    col_order = genx_dict["Network"].columns
    genx_dict["Network"].set_index("transmission_path_name", inplace=True)
    genx_dict["Network"]["Line_Max_Flow_MW"] += results_dict["tx_exp"]["value"].round(1)
    genx_dict["Network"].reset_index(drop=False, inplace=True)
    genx_dict["Network"] = genx_dict["Network"].loc[:, col_order]
    # genx_dict["Network"]["Line_Max_Flow_MW"] = 0
    # genx_dict["Network"].loc[:, "Line_Max_Flow_MW"] = (
    #     results_dict["tx_exp"].loc[line_names, "end_value"].values.round(1)
    # )
    genx_dict["Network"]["Line_Reinforcement_Cost_per_MWyr"] = 1e12

    genx_dict["Generators_variability"] = remove_nonvariable_resources(
        genx_dict["Generators_variability"]
    )

    return genx_dict


def write_genx_operational_files(genx_dict: Dict[str, pd.DataFrame], path: Path):
    path.mkdir(parents=True, exist_ok=True)
    for name, df in genx_dict.items():
        if "Generators_variability" not in name:
            name = name.replace(".csv", "")
            df.to_csv(path / f"{name}.csv", index=False)


def weighted_avg_annuities(
    inputs_path: Path, output_path: Path, fixed_om_prefixs: str = [""]
):
    gen_data = {}
    existing_gen = {}
    new_gen = {}
    period_fixed_costs = {}

    all_inputs_path = inputs_path.parent
    all_outputs_path = output_path.parent
    gen_files = list(all_inputs_path.rglob("Generators_data*"))
    periods = sorted([f.parts[-2].split("_")[-1] for f in gen_files])
    # periods = ["p1", "p2", "p3", "p4", "p5", "p6"]
    for period in periods:
        gen_data[period] = pd.read_csv(
            all_outputs_path / f"Inputs_{period}" / "Generators_data.csv",
            na_filter=False,
        ).set_index("Resource")
        existing_gen[period] = gen_data[period].loc[
            gen_data[period]["Inv_Cost_per_MWyr"] == 0, :
        ]
        new_gen[period] = gen_data[period].loc[
            gen_data[period]["Inv_Cost_per_MWyr"] > 0, :
        ]
        assert len(gen_data[period]) == (
            len(existing_gen[period]) + len(new_gen[period])
        )

        fixed_cost_cols = []
        for prefix in fixed_om_prefixs:
            fixed_cost_cols.extend(
                [f"{prefix}Fixed_OM_Cost_per_MWyr", f"{prefix}Fixed_OM_Cost_per_MWhyr"]
            )
        period_fixed_costs[period] = (
            new_gen[period]
            .loc[
                :,
                fixed_cost_cols,
            ]
            .copy()
        )

    for i, p in enumerate(periods):
        for kind in ["MW", "MWh"]:
            new_gen[p] = period_weighted_avg_cost(
                new_gen,
                period_fixed_costs,
                periods[: i + 1],
                kind=kind,
                fixed_om_prefixs=fixed_om_prefixs,
            )

    for period in periods:
        fn = output_path.parent / f"Inputs_{period}" / "Generators_data.csv"
        pd.concat([existing_gen[period], new_gen[period]]).to_csv(fn)
        if fn.exists():
            print(fn)

        # gen_data[period].to_csv(
        #     output_path.parent / f"Inputs_{period}" / "Generators_data.csv"
        # )


def period_weighted_avg_cost(
    new_gen: Dict[str, pd.DataFrame],
    period_fixed_costs: Dict[str, pd.DataFrame],
    periods: List[str],
    kind: str,
    fixed_om_prefixs: List[str] = [""],
) -> pd.DataFrame:
    if len(periods) == 1:
        return new_gen[periods[0]]

    final_period = periods[-1]
    final_year = PERIOD_YEAR[final_period]
    new_gen[final_period].loc[:, f"Fixed_OM_Cost_per_{kind}yr"] = 0
    total_build = new_gen[final_period][f"Existing_Cap_{kind}"]
    p_build = {}
    frac_build = {}

    # First period fraction built and fractional cost
    # Assume plants are built/deployed in the final year of each period
    plant_age = final_year - 2027
    p_build[periods[0]] = new_gen[periods[0]][f"Existing_Cap_{kind}"].where(
        new_gen[periods[0]]["Lifetime"] >= plant_age, 0
    )
    frac_build[periods[0]] = (
        (p_build[periods[0]] / total_build)
        .fillna(0)
        .replace(np.inf, 0)
        .replace(-np.inf, 0)
    )
    for prefix in fixed_om_prefixs:
        new_gen[final_period].loc[:, f"{prefix}Fixed_OM_Cost_per_{kind}yr"] = (
            period_fixed_costs[periods[0]][f"{prefix}Fixed_OM_Cost_per_{kind}yr"]
            * frac_build[periods[0]]
        ).astype(int)

    # Fraction built and fractional cost from subsequent periods
    for p1, p2 in zip(periods[:-1], periods[1:]):
        plant_age = final_year - PERIOD_YEAR[p2]
        # p_build[p2] = new_gen[p2][f"Existing_Cap_{kind}"] - p_build[p1]
        p_build[p2] = new_gen[p2][f"Existing_Cap_{kind}"].where(
            new_gen[p2]["Lifetime"] >= plant_age, 0
        ) - new_gen[p1][f"Existing_Cap_{kind}"].where(
            new_gen[p2]["Lifetime"] >= plant_age, 0
        )
        frac_build[p2] = (
            (p_build[p2] / total_build).fillna(0).replace(np.inf, 0).replace(-np.inf, 0)
        )
        for prefix in fixed_om_prefixs:
            new_gen[final_period].loc[:, f"{prefix}Fixed_OM_Cost_per_{kind}yr"] += (
                period_fixed_costs[p2].loc[:, f"{prefix}Fixed_OM_Cost_per_{kind}yr"]
                * frac_build[p2]
            ).astype(int)

    return new_gen[final_period]


def shrink_model_size(output_path: Path):
    "Remove resources with capacity of 0 to reduce model size"
    all_outputs_path = output_path.parent
    gen_files = all_outputs_path.rglob("Generators_data*")

    for gen_path in gen_files:
        gen_data = pd.read_csv(gen_path, na_filter=False)
        gen_data = gen_data.loc[
            (gen_data["Existing_Cap_MW"] >= 10)
            | (gen_data["technology"].str.contains("Off", case=False)),
            :,
        ]
        gen_data.to_csv(gen_path, index=False)


def main(
    results_path: str,
    genx_inputs_path: str,
    output_path: str,
    co2_slack: int = 200,
    year: int = 2050,
):
    if "test" in results_path:
        return None
    if not Path(results_path).exists():
        folder_name = Path(results_path).stem
        if " " in folder_name:
            folder_name = folder_name.replace(" ", "_")
        elif "_" in folder_name:
            folder_name = folder_name.replace("_", " ")
        results_path = Path(results_path).parent / folder_name
        if not results_path.exists():
            raise ValueError(f"The folder {results_path} does not exist")

    year = int(year)
    Path(output_path).mkdir(parents=True, exist_ok=True)

    print("Loading model results")
    print(results_path)
    model_results, corrected_inputs = load_final_capacity(Path(results_path), year)
    if corrected_inputs:
        # Some results have different resource names because of a PG bug. Use corrected
        # inputs where results don't have the very high cluster number
        print("Using corrected inputs")
        genx_inputs_path = genx_inputs_path.replace("commit", "commit_corrected")

    print("Loading GenX inputs")
    print(genx_inputs_path)
    genx_inputs = load_genx_inputs(Path(genx_inputs_path))
    genx_inputs["Network"].to_csv(Path(output_path) / "original_network.csv")

    print("Creating operational inputs")
    operational_inputs = create_operational_genx_inputs(
        model_results, genx_inputs, fixed_om_prefix=""
    )

    if "current" in str(results_path):
        fixed_om_prefix = "base_"
        base_genx_inputs_path = Path(
            genx_inputs_path.replace("current_policies", "base")
        )
        base_genx_inputs = load_genx_inputs(Path(base_genx_inputs_path))
        base_operational_inputs = create_operational_genx_inputs(
            model_results,
            base_genx_inputs,
            fixed_om_prefix=fixed_om_prefix,
            gen_data_only=True,
        )
        for col in ["Fixed_OM_Cost_per_MWyr", "Fixed_OM_Cost_per_MWhyr"]:
            operational_inputs["Generators_data"][f"{fixed_om_prefix}{col}"] = (
                base_operational_inputs["Generators_data"][
                    f"{fixed_om_prefix}{col}"
                ].copy()
            )

    print("Writing operational inputs")
    write_genx_operational_files(operational_inputs, Path(output_path))

    if year == 2050:
        if "current" in str(results_path):
            fixed_om_prefixs = ["", "base_"]
        else:
            fixed_om_prefixs = [""]
        weighted_avg_annuities(
            Path(genx_inputs_path), Path(output_path), fixed_om_prefixs=fixed_om_prefixs
        )
        print("Removing small generators")
        shrink_model_size(Path(output_path))


if __name__ == "__main__":
    typer.run(main)
