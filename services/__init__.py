"""Application service layer."""

__all__ = ["OptimizerService"]


def __getattr__(name: str):
    if name == "OptimizerService":
        from services.optimizer_service import OptimizerService

        return OptimizerService
    raise AttributeError(name)
