"""Climate platform for GWM RU."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import has_capability
from .const import DOMAIN
from .coordinator import GwmRuCoordinator
from .entity import GwmRuEntity, setup_vehicle_entities


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: GwmRuCoordinator = hass.data[DOMAIN][entry.entry_id]

    def entities_for_vehicle(vehicle):
        if not has_capability(vehicle, "1-1-9"):
            return ()
        return (GwmRuClimate(coordinator, vehicle["vin"]),)

    setup_vehicle_entities(coordinator, async_add_entities, entities_for_vehicle)


class GwmRuClimate(GwmRuEntity, ClimateEntity):
    _attr_name = "Климат"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
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

    def _instructions(self, switch_order: str, temperature: float | None = None) -> dict:
        target = temperature if temperature is not None else self.target_temperature or 18
        return {
            "0x04": {
                "airConditioner": {
                    "operationTime": "15",
                    "switchOrder": switch_order,
                    "temperature": str(int(target)),
                }
            }
        }

    async def _send(self, switch_order: str, temperature: float | None = None) -> None:
        if not self.coordinator.security_pin:
            raise HomeAssistantError("Security PIN is required")
        await self.coordinator.async_execute_t5(
            self.vin,
            self._instructions(switch_order, temperature),
            "0x04",
            self.coordinator.security_pin,
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.COOL:
            await self._send("1")
        elif hvac_mode == HVACMode.OFF:
            await self._send("2")
        else:
            raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")

    async def async_turn_on(self) -> None:
        await self._send("1")

    async def async_turn_off(self) -> None:
        await self._send("2")

    async def async_set_temperature(self, **kwargs) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        temperature = max(self.min_temp, min(self.max_temp, float(temperature)))
        self._requested_target_temperature = temperature
        # On GWM RU changing target temperature should be an actual remote command.
        # If climate is currently off, the same command also starts it.
        await self._send("1", temperature)
