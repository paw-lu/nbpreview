"""Create a model for baby length."""
import pymc as pm
from pandas import DataFrame
from pymc import Model


def model_baby_length(babies_data: DataFrame) -> Model:
    """Create model for baby length."""
    with pm.Model(coords={"time_idx": babies_data.index}) as babies_model:
        alpha = pm.Normal("alpha", sigma=10)
        beta = pm.Normal("beta", sigma=10)
        gamma = pm.HalfNormal("gamma", sigma=10)
        sigma = pm.HalfNormal("sigma", sigma=10)

        month = pm.MutableData("month", value=babies_data["Month"].astype(float))

        mu = pm.Deterministic("mu", alpha + beta * month**0.5, dims="time_idx")
        epsilon = pm.Deterministic(
            "epsilon",
            gamma + sigma * month,
            dims="time_idx",
        )

        pm.Normal(
            "length",
            mu=mu,
            sigma=epsilon,
            observed=babies_data["Length"],
            dims="time_idx",
        )
    return babies_model
