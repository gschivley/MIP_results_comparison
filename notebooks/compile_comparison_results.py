"Compile models results into cleaned comparison data files"

import os
from pathlib import Path
from typing import Dict, List

import altair as alt
import pandas as pd
from fig_functions import (
    calc_mean_annual_cap,
    calc_mean_annual_gen,
    fix_tx_line_names,
    load_data,
    load_genx_operations_data,
    reverse_dict_of_lists,
)

cwd = Path.cwd()

_scenarios = {
    "base": [
        "full-base-200",
        "full-base-200-retire",
        "full-base-200-no-ccs",
        "full-base-200-commit",
        "full-base-50",
        "full-base-1000",
        "full-base-200-tx-0",
        "full-base-200-tx-15",
        "full-base-200-tx-50",
        "20-week-foresight",
        "20-week-myopic",
    ],
    "current_policies": [
        "full-current-policies",
        "full-current-policies-low-gas",
        "full-current-policies-high-coal",
        "full-current-policies-retire",
        "full-current-policies-retire-low-gas",
        "full-current-policies-retire-high-coal",
        "full-current-policies-commit",
        "20-week-foresight-current-policy",
        "20-week-myopic-current-policy",
    ],
}

scenarios = reverse_dict_of_lists(_scenarios)

_child_scenarios = {
    "carbon_price": [
        "full-base-200",
        "full-base-50",
        "full-base-1000",
    ],
    "transmission": [
        "full-base-200-tx-0",
        "full-base-200-tx-15",
        "full-base-200-tx-50",
    ],
    "ccs": ["full-base-200-no-ccs"],
}

child_scenarios = reverse_dict_of_lists(_child_scenarios)

_configurations = {
    "base": [
        "full-base-200",
        "full-base-50",
        "full-base-1000",
        "full-current-policies",
        "full-base-200-tx-0",
        "full-base-200-tx-15",
        "full-base-200-tx-50",
        "full-base-200-no-ccs",
    ],
    "unit_commit": [
        "full-base-200-commit",
        "full-current-policies-commit",
    ],
    "retirement": [
        "full-base-200-retire",
        "full-current-policies-retire",
        "full-current-policies-retire-low-gas",
        "full-current-policies-retire-high-coal",
    ],
    "20-week": [
        "20-week-myopic-current-policy",
        "20-week-myopic",
    ],
    "foresight": [
        "20-week-foresight-current-policy",
        "20-week-foresight",
    ],
}
configurations = reverse_dict_of_lists(_configurations)

comparison_folders = {
    "carbon_price": [
        "full-base-50",
        "full-base-200",
        "full-base-1000",
    ],
    "foresight": [
        "full-base-200",
        "20-week-myopic",
        "20-week-foresight",
        "full-current-policies",
        "20-week-myopic-current-policy",
        "20-week-foresight-current-policy",
    ],
    "unit_commit": [
        "full-base-200",
        "full-base-200-commit",
        "full-current-policies",
        "full-current-policies-commit",
    ],
    "endogenous_retirement": [
        "full-base-200",
        "full-base-200-retire",
        "full-current-policies",
        "full-current-policies-retire",
        "full-current-policies-retire-low-gas",
        "full-current-policies-retire-high-coal",
    ],
    "transmission_expansion": [
        "full-base-200-tx-0",
        "full-base-200-tx-15",
        "full-base-200-tx-50",
        "full-base-200",
    ],
    "all": [
        "full-base-200",
        "full-base-200-retire",
        "full-base-200-no-ccs",
        "full-base-200-commit",
        "full-base-50",
        "full-base-1000",
        "full-current-policies",
        "full-current-policies-low-gas",
        "full-current-policies-high-coal",
        "full-current-policies-retire",
        "full-current-policies-retire-low-gas",
        "full-current-policies-retire-high-coal",
        "full-current-policies-commit",
        "full-base-200-tx-0",
        "full-base-200-tx-15",
        "full-base-200-tx-50",
        "20-week-foresight",
        "20-week-myopic",
        "20-week-foresight-current-policy",
        "20-week-myopic-current-policy",
    ],
}


def create_dataframes(data_folders: List[Path]) -> Dict[str, pd.DataFrame]:
    data_folders = [cwd.parent / f for f in data_folders]
    data_folders = [f for f in data_folders if f.exists()]

    # Compile data from each of the case folders
    cap_list = []
    gen_list = []
    emiss_list = []
    tx_list = []
    tx_exp_list = []
    op_cost_list = []
    op_cost_model_list = []
    # op_marginal_price_list = []
    op_nse_list = []
    op_gen_list = []
    op_cap_list = []
    op_emiss_list = []
    for folder in data_folders:
        case_id = folder.stem.split("short-")[-1]
        cap_data = load_data(folder, "resource_capacity.csv")
        cap_data = cap_data.query("unit=='MW' and not tech_type.isna()")
        cap_data["case"] = case_id
        cap_data["scenario"] = scenarios.get(folder.name, "none")
        cap_data["configuration"] = configurations.get(folder.name, "none")
        cap_data["child_scenario"] = child_scenarios.get(folder.name, "none")
        cap_list.append(cap_data)

        gen_data = load_data(folder, "generation.csv")
        gen_data["case"] = case_id
        gen_data["scenario"] = scenarios.get(folder.name, "none")
        gen_data["configuration"] = configurations.get(folder.name, "none")
        gen_data["child_scenario"] = child_scenarios.get(folder.name, "none")
        gen_list.append(gen_data)

        emiss_data = load_data(folder, "emissions.csv")
        emiss_data.loc[emiss_data["unit"] == "kg", "value"] /= 1000
        emiss_data["case"] = case_id
        emiss_data["scenario"] = scenarios.get(folder.name, "none")
        emiss_data["configuration"] = configurations.get(folder.name, "none")
        emiss_data["child_scenario"] = child_scenarios.get(folder.name, "none")
        emiss_list.append(emiss_data)

        tx_data = load_data(folder, "transmission.csv")
        tx_data["case"] = case_id
        tx_data["scenario"] = scenarios.get(folder.name, "none")
        tx_data["configuration"] = configurations.get(folder.name, "none")
        tx_data["child_scenario"] = child_scenarios.get(folder.name, "none")
        tx_list.append(tx_data)

        tx_exp_data = load_data(folder, "transmission_expansion.csv")
        tx_exp_data["case"] = case_id
        tx_exp_data["scenario"] = scenarios.get(folder.name, "none")
        tx_exp_data["configuration"] = configurations.get(folder.name, "none")
        tx_exp_data["child_scenario"] = child_scenarios.get(folder.name, "none")
        tx_exp_list.append(tx_exp_data)

        try:
            op_cost_data = load_genx_operations_data(folder, "costs.csv")
            op_cost_data["case"] = case_id
            op_cost_data["scenario"] = scenarios.get(folder.name, "none")
            op_cost_data["configuration"] = configurations.get(folder.name, "none")
            op_cost_data["child_scenario"] = child_scenarios.get(folder.name, "none")
            op_cost_model_data = load_genx_operations_data(
                folder, "costs.csv", model_costs_only=True
            )
            op_cost_model_data["case"] = case_id
            op_cost_model_data["configuration"] = configurations.get(
                folder.name, "none"
            )
            op_cost_model_data["scenario"] = scenarios.get(folder.name, "none")
            op_cost_model_data["child_scenario"] = child_scenarios.get(
                folder.name, "none"
            )
            op_cost_list.append(op_cost_data)
            op_cost_model_list.append(op_cost_model_data)

            op_nse_data = load_genx_operations_data(folder, "nse.csv", hourly_data=True)
            op_nse_data["case"] = case_id
            op_nse_data["scenario"] = scenarios.get(folder.name, "none")
            op_nse_data["configuration"] = configurations.get(folder.name, "none")
            op_nse_data["child_scenario"] = child_scenarios.get(folder.name, "none")
            op_nse_list.append(op_nse_data)
        except:
            pass

        # try:
        #     op_marginal_price_data = load_genx_operations_data(
        #         folder, "average_annual_prices.csv"
        #     )
        #     op_marginal_price_data["case"] = case_id
        #     op_marginal_price_data["scenario"] = scenarios.get(folder.name, "none")
        #     op_marginal_price_data["configuration"] = configurations.get(
        #         folder.name, "none"
        #     )
        #     op_marginal_price_data["child_scenario"] = child_scenarios.get(
        #         folder.name, "none"
        #     )
        #     op_marginal_price_list.append(op_marginal_price_data)
        # except:
        #     pass

        op_gen_cap_data = load_genx_operations_data(folder, "capacityfactor.csv")
        if not op_gen_cap_data.empty:
            op_gen_cap_data = op_gen_cap_data.query("~tech_type.str.contains('Other')")
            op_gen_cap_data["case"] = case_id
            op_gen_data = op_gen_cap_data[
                [
                    "tech_type",
                    "planning_year",
                    "model",
                    "AnnualSum",
                    "resource_name",
                    "case",
                ]
            ].rename(columns={"AnnualSum": "value"})
            op_cap_data = op_gen_cap_data[
                [
                    "tech_type",
                    "planning_year",
                    "model",
                    "Capacity",
                    "resource_name",
                    "case",
                ]
            ].rename(columns={"Capacity": "end_value"})
            op_cap_data["unit"] = "MW"
            op_gen_list.append(op_gen_data)
            op_cap_list.append(op_cap_data)

        op_emiss_data = load_genx_operations_data(
            folder, "emissions.csv", hourly_data=True
        )
        # try:
        #     op_emiss_data = op_emiss_data.query("~tech_type.str.contains('Other')")
        # except:
        #     pass
        op_emiss_data["case"] = case_id
        op_emiss_data["scenario"] = scenarios.get(folder.name, "none")
        op_emiss_data["configuration"] = configurations.get(folder.name, "none")
        op_emiss_data["child_scenario"] = child_scenarios.get(folder.name, "none")
        op_emiss_list.append(op_emiss_data)

    cap = pd.concat(cap_list, ignore_index=True)
    gen = pd.concat(gen_list, ignore_index=True)
    for hour in [2, 4, 6, 8]:
        cap["resource_name"] = cap["resource_name"].str.replace(f"_{hour}hour", "")
        gen["resource_name"] = gen["resource_name"].str.replace(f"_{hour}hour", "")
    emiss = pd.concat(emiss_list, ignore_index=True)
    tx = pd.concat(tx_list, ignore_index=True)
    tx_exp = pd.concat(tx_exp_list, ignore_index=True)
    op_costs = pd.concat(op_cost_list, ignore_index=True)
    op_costs_model = pd.concat(op_cost_model_list, ignore_index=True)
    # op_marginal_price = pd.concat(op_marginal_price_list, ignore_index=True)
    op_nse = pd.concat(op_nse_list, ignore_index=True)
    op_emiss = pd.concat(op_emiss_list, ignore_index=True)
    if op_cap_list:
        op_gen = pd.concat(op_gen_list, ignore_index=True)
        op_cap = pd.concat(op_cap_list, ignore_index=True)
    else:
        op_gen = pd.DataFrame()
        op_cap = pd.DataFrame()

    tx["start_region"] = tx["line_name"].str.split("_to_").str[0]
    tx["dest_region"] = tx["line_name"].str.split("_to_").str[1]

    first_year = tx["planning_year"].min()
    starting_tx = tx.loc[tx["planning_year"] == first_year, :]
    starting_tx = starting_tx.rename(columns={"start_value": "value"})
    starting_tx["planning_year"] = 2023

    tx_exp["start_region"] = tx_exp["line_name"].str.split("_to_").str[0]
    tx_exp["dest_region"] = tx_exp["line_name"].str.split("_to_").str[1]
    tx_all = pd.concat([starting_tx, tx_exp])
    tx_exp_data = (
        tx_exp.groupby(
            ["line_name", "planning_year", "case", "start_region", "dest_region"],
            as_index=False,
        )["value"]
        .mean()
        .sort_values("case")
    )
    tx_exp_data

    avg_total_region_cap = calc_mean_annual_cap(cap, new_build=False, by_agg_zone=True)
    avg_new_region_cap = calc_mean_annual_cap(cap, by_agg_zone=True, new_build=True)
    avg_new_total_cap = calc_mean_annual_cap(cap, by_agg_zone=False, new_build=True)

    avg_region_gen = calc_mean_annual_gen(gen, by_agg_zone=True)
    avg_total_gen = calc_mean_annual_gen(gen, by_agg_zone=False)

    df_dict = {
        "capacity": cap,
        "generation": gen,
        "avg_region_cap": avg_total_region_cap,
        "avg_new_region_cap": avg_new_region_cap.reset_index(),
        "avg_new_total_cap": avg_new_total_cap.reset_index(),
        "avg_region_gen": avg_region_gen.reset_index(),
        "avg_total_gen": avg_total_gen.reset_index(),
        "annual_tx_expansion": tx_all,
        "avg_annual_tx_expansion": tx_exp_data,
        "emissions": emiss,
        "operational_costs": op_costs,
        "operational_costs_model": op_costs_model,
        # "operational_marginal_price": op_marginal_price,
        "operational_emissions": op_emiss,
        "operational_nse": op_nse,
        "operational_gen": op_gen,
    }

    return df_dict


MODEL_NAMES = ["GenX", "Switch", "TEMOA", "USENSYS"]

if __name__ == "__main__":
    sort_by = ["case", "model", "planning_year"]
    for name, data_folders in comparison_folders.items():
        print(name)
        save_data_folder = cwd.parent / "compiled_results" / name
        save_data_folder.mkdir(exist_ok=True, parents=True)

        df_dict = create_dataframes(data_folders=data_folders)

        for f, _df in df_dict.items():
            print(f)
            _df.sort_values([c for c in sort_by if c in _df.columns], inplace=True)
            if "model" in _df.columns:
                for m_name in MODEL_NAMES:
                    _df.loc[_df["model"].str.lower() == m_name.lower(), "model"] = (
                        m_name
                    )
            _df.to_csv(save_data_folder / f"{f}.csv", index=False)
            if f in ["capacity", "generation"] and name == "all":
                _df.to_parquet(save_data_folder / f"{f}.parquet")
