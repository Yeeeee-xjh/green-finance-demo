"""数绿融通：绿色与转型信贷全流程智能作业能力层。"""

__all__ = ["GreenCreditAgent"]

def __getattr__(name):
    if name == "GreenCreditAgent":
        from .orchestrator import GreenCreditAgent
        return GreenCreditAgent
    raise AttributeError(name)
