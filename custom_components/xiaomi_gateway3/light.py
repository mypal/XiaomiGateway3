import asyncio
from functools import cached_property

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityFeature,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_TRANSITION,
)
from homeassistant.helpers.restore_state import RestoreEntity

from .core.gate.base import XGateway
from .hass.entity import XEntity


# noinspection PyUnusedLocal
async def async_setup_entry(hass, entry, async_add_entities) -> None:
    XEntity.ADD[entry.entry_id + "light"] = async_add_entities


class XLight(XEntity, LightEntity, RestoreEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def on_init(self):
        self._attr_color_mode = ColorMode.ONOFF

        for conv in self.device.converters:
            if conv.attr == ATTR_BRIGHTNESS:
                self.listen_attrs.add(conv.attr)
                self._attr_color_mode = ColorMode.BRIGHTNESS
            elif conv.attr == ATTR_COLOR_TEMP:
                self.listen_attrs.add(conv.attr)
                self._attr_color_mode = ColorMode.COLOR_TEMP
                if hasattr(conv, "minm") and hasattr(conv, "maxm"):
                    self._attr_min_mireds = conv.minm
                    self._attr_max_mireds = conv.maxm
                elif hasattr(conv, "mink") and hasattr(conv, "maxk"):
                    self._attr_min_mireds = int(1000000 / conv.maxk)
                    self._attr_max_mireds = int(1000000 / conv.mink)
            elif conv.attr == ATTR_EFFECT and hasattr(conv, "map"):
                self.listen_attrs.add(conv.attr)
                self._attr_supported_features |= LightEntityFeature.EFFECT
                self._attr_effect_list = list(conv.map.values())

        self._attr_supported_color_modes = {self._attr_color_mode}

    def set_state(self, data: dict):
        if self.attr in data:
            self._attr_is_on = bool(data[self.attr])
        if ATTR_BRIGHTNESS in data:
            self._attr_brightness = data[ATTR_BRIGHTNESS]
        if ATTR_COLOR_TEMP in data:
            self._attr_color_temp = data[ATTR_COLOR_TEMP]
        if ATTR_EFFECT in data:
            self._attr_effect = data[ATTR_EFFECT]

    def get_state(self) -> dict:
        return {
            self.attr: self._attr_is_on,
            ATTR_BRIGHTNESS: self._attr_brightness,
            ATTR_COLOR_TEMP: self._attr_color_temp,
        }

    async def async_turn_on(self, **kwargs):
        self.device.write(kwargs if kwargs else {self.attr: True})

    async def async_turn_off(self, **kwargs):
        self.device.write({self.attr: False})


class XZigbeeLight(XLight):
    def on_init(self):
        super().on_init()

        for conv in self.device.converters:
            if conv.attr == ATTR_TRANSITION:
                self._attr_supported_features |= LightEntityFeature.TRANSITION

    @cached_property
    def default_transition(self) -> float | None:
        return self.device.extra.get("default_transition")

    async def async_turn_on(self, **kwargs):
        if self.default_transition is not None:
            kwargs.setdefault(ATTR_TRANSITION, self.default_transition)

        if ATTR_TRANSITION in kwargs:
            # important to sort args in right order, transition should be last
            kwargs = {
                k: kwargs[k]
                for k in (ATTR_BRIGHTNESS, ATTR_COLOR_TEMP, ATTR_TRANSITION)
                if k in kwargs
            }

        self.device.write(kwargs if kwargs else {self.attr: True})

    async def async_turn_off(self, **kwargs):
        if self.default_transition is not None:
            kwargs.setdefault(ATTR_TRANSITION, self.default_transition)

        if ATTR_TRANSITION in kwargs:
            kwargs.setdefault(ATTR_BRIGHTNESS, 0)

        self.device.write(kwargs if kwargs else {self.attr: False})


class XLightGroup(XLight):
    update_event: asyncio.Event

    def childs(self):
        return [
            XGateway.devices[did]
            for did in self.device.extra.get("childs", [])
            if did in XGateway.devices
        ]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.update_event = asyncio.Event()
        for child in self.childs():
            child.add_listener(self.forward_child_update)

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        for child in self.childs():
            child.remove_listener(self.forward_child_update)

    def forward_child_update(self, data: dict):
        self.update_event.set()
        self.device.dispatch(data)

    async def wait_for_update(self, delay=10):
        try:
            self.update_event.clear()
            async with asyncio.timeout(delay):
                await self.update_event.wait()
        except TimeoutError:
            pass

    async def async_turn_on(self, **kwargs):
        await super().async_turn_on(**kwargs)
        await self.wait_for_update()

    async def async_turn_off(self, **kwargs):
        await super().async_turn_off(**kwargs)
        await self.wait_for_update()


XEntity.NEW["light"] = XLight
XEntity.NEW["light.type.zigbee"] = XZigbeeLight
XEntity.NEW["light.type.group"] = XLightGroup
