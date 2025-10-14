"""Create plots for babies model."""
from collections.abc import Sequence

import arviz as az
import matplotlib.pyplot as plt
from arviz import InferenceData
from matplotlib.axes import Axes
from matplotlib.axes._subplots import Subplot
from pandas import DataFrame


def plot_length_dist(
    babies_idata: InferenceData,
    babies_data: DataFrame,
    month: int,
    ax: Axes | None = None,
    color: str | None = None,
) -> Subplot:
    """Plot the length given an age in months."""
    if ax is None:
        ax = plt.gca()

    length_data = babies_idata.sel(
        time_idx=babies_data.loc[lambda df: df["Month"] == month].index
    )["posterior_predictive"].stack(dim=["chain", "draw", "time_idx"])["length"]
    plot = az.plot_dist(
        length_data,
        fill_kwargs={"alpha": 1},
        ax=ax,
        color=color,
    )
    return plot


def make_length_comparison_plot(
    babies_idata: InferenceData,
    babies_data: DataFrame,
    months: Sequence[int],
    ax: Axes | None = None,
) -> Subplot:
    """Given a sequence of months, compare their distribution."""
    if ax is None:
        ax = plt.gca()

    for idx, month in enumerate(months):
        color = f"C{idx}"
        plot = plot_length_dist(
            babies_idata, babies_data=babies_data, month=month, ax=ax, color=color
        )

    return plot


def plot_length_hdi(
    babies_data: DataFrame,
    babies_idata: InferenceData,
    hdi_prob: float = 0.95,
    color: str = "C0",
    ax: Axes | None = None,
    alpha: float = 1.0,
) -> Subplot:
    """Plot HDI intervals for baby length fit."""
    if ax is None:
        ax = plt.gca()

    plot = az.plot_hdi(
        x=babies_data["Month"],
        y=babies_idata["posterior_predictive"]["length"],
        hdi_prob=hdi_prob,
        color=color,
        fill_kwargs={"alpha": alpha},
    )
    return plot


def make_length_hdi_plot(
    babies_data: DataFrame,
    babies_idata: InferenceData,
    hdi_probs: Sequence[float],
    ax: Axes | None = None,
    alpha: float = 1.0,
) -> Subplot:
    """Plot HDI of baby length over age."""
    if ax is None:
        ax = plt.gca()

    sorted_hdi_probs = sorted(hdi_probs, reverse=True)
    for idx, hdi_prob in enumerate(sorted_hdi_probs):
        color = f"C{idx}"
        plot = plot_length_hdi(
            babies_data,
            babies_idata=babies_idata,
            hdi_prob=hdi_prob,
            color=color,
            ax=ax,
            alpha=alpha,
        )

    return plot


def plot_dist_and_hdi(
    babies_data: DataFrame,
    babies_idata: InferenceData,
    months: Sequence[int],
    hdi_probs: Sequence[float],
    alpha: float = 1.0,
) -> tuple[Subplot, Subplot]:
    """Plot selected distributions of babie's height along with HDI of trend."""
    fig, (left_ax, right_ax) = plt.subplots(
        figsize=(25, 5),
        ncols=2,
        facecolor="#1C1B1F",
    )
    make_length_comparison_plot(
        babies_idata,
        babies_data=babies_data,
        months=months,
        ax=left_ax,
    ).set(xticks=[], yticks=[])
    make_length_hdi_plot(
        babies_data,
        babies_idata=babies_idata,
        hdi_probs=[0.50, 0.99],
        ax=right_ax,
    ).set(xticks=[], yticks=[])
    fig.tight_layout()
    return (left_ax, right_ax)
