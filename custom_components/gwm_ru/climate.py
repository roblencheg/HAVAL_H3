"""Climate platform for GWM RU."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]
    setup_vehicle_entities(
        coordinator,
        async_add_entities,
        lambda vehicle: (GwmRuClimate(coordinator, vehicle["vin"]),),
    )


class GwmRuClimate(GwmRuEntity, ClimateEntity):
    _attr_name = "Климат"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = 16
    _attr_max_temp = 32

    def __init__(self, coordinator: GwmRuCoordinator, vin: str) -> None:
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{coordinator.entity_prefix(vin)}_climate"
        self._requested_target_temperature: float | None = None

    @property
    def available(self) -> bool:
        capabilities = (self.vehicle or {}).get("capabilities") or {}
        return (
            super().available
            and capabilities.get("climate", True)
            and self.coordinator.enable_remote_controls
            and bool(self.coordinator.security_pin)
        )

    @property
    def hvac_mode(self) -> HVACMode:
        state = ((self.vehicle or {}).get("state") or {})
        return HVACMode.COOL if state.get("climate_on") is True else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        value = ((self.vehicle or {}).get("state") or {}).get("ambient_temperature")
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def target_temperature(self) -> float | None:
        return self._requested_target_temperature or 18.0

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if not self.coordinator.security_pin:
            raise HomeAssistantError("Security PIN is required")
        switch_order = "1" if hvac_mode == HVACMode.COOL else "2"
        instructions = {
            "0x04": {
                "airConditioner": {
                    "operationTime": "15",
                    "switchOrder": switch_order,
                    "temperature": str(int(self.target_temperature or 18)),
                }
            }
        }
        await self.coordinator.async_execute_t5(
            self.vin,
            instructions,
            "0x04",
            self.coordinator.security_pin,
        )

    async def async_set_temperature(self, **kwargs) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        temperature = max(self.min_temp, min(self.max_temp, float(temperature)))
        self._requested_target_temperature = temperature
        if self.hvac_mode == HVACMode.OFF:
            return
        instructions = {
            "0x04": {
                "airConditioner": {
                    "operationTime": "15",
                    "switchOrder": "1",
                    "temperature": str(int(temperature)),
                }
            }
        }
        await self.coordinator.async_execute_t5(
            self.vin,
            instructions,
            "0x04",
            self.coordinator.security_pin,
        )
