from typing import Protocol

from app.core.config import Settings
from app.services.health_service import HealthService


class DriverMonitoringReadiness(Protocol):
    async def is_available(self) -> bool:
        pass


class HealthDriverMonitoringReadiness:
    def __init__(self, settings: Settings) -> None:
        self.health_service = HealthService(settings=settings)

    async def is_available(self) -> bool:
        return self.health_service.is_vit_model_available()
