import asyncio
import time

from homeassistant.components.sensor import DOMAIN
from homeassistant.core import HomeAssistant

from custom_components.xiaomi_gateway3.climate import AqaraE1
from custom_components.xiaomi_gateway3.core.converters import ZIGBEE
from custom_components.xiaomi_gateway3.core.device import XDevice
from custom_components.xiaomi_gateway3.core.gateway import XGateway
from custom_components.xiaomi_gateway3.sensor import XiaomiAction

assert DOMAIN

ZDID = "lumi.112233aabbcc"
ZMAC = "0x0000112233aabbcc"
ZNWK = "0x12ab"


class Hass(HomeAssistant):
    def __init__(self):
        asyncio.get_running_loop = lambda: asyncio.new_event_loop()
        HomeAssistant.__init__(self)
        self.bus.async_fire = self.async_fire
        self.events = []

    def async_fire(self, *args, **kwargs):
        self.events.append(args)


def test_button():
    gw = XGateway("", "")
    device = XDevice(ZIGBEE, "lumi.sensor_86sw2", ZDID, ZMAC, ZNWK)
    device.setup_converters()
    device.available = True
    conv = next(conv for conv in device.converters if conv.attr == "action")

    button = XiaomiAction(gw, device, conv)
    button.hass = Hass()
    button.async_write_ha_state()

    state = button.hass.states.get(button.entity_id)
    assert state.state == ""
    assert state.attributes == {
        "device_class": "action",
        "friendly_name": "Aqara Double Wall Button Action",
        "icon": "mdi:bell",
    }

    data = device.decode_lumi([{"res_name": "13.1.85", "value": 1}])
    button.async_set_state(data)
    button.async_write_ha_state()

    state = button.hass.states.get(button.entity_id)
    assert state.state == "button_1_single"
    assert button.hass.events[1] == (
        "xiaomi_aqara.click",
        {
            "entity_id": "sensor.0x0000112233aabbcc_action",
            "click_type": "button_1_single",
        },
    )

    button.hass.loop.run_until_complete(asyncio.sleep(0.3))
    state = button.hass.states.get(button.entity_id)
    assert state.state == ""


def test_aqara_climate_e1():
    gw = XGateway("", "")
    device = XDevice(ZIGBEE, "lumi.airrtc.agl001", ZDID, ZMAC, ZNWK)
    device.setup_converters()
    device.available = True
    conv = next(conv for conv in device.converters if conv.attr == "climate")

    climate = AqaraE1(gw, device, conv)
    climate.hass = Hass()
    climate.async_write_ha_state()

    state = climate.hass.states.get(climate.entity_id)
    assert state.state == "unknown"
    assert state.attributes == {
        "hvac_modes": ["off", "heat", "auto"],
        "min_temp": 5,
        "max_temp": 30,
        "target_temp_step": 0.5,
        "current_temperature": None,
        "temperature": None,
        "device_class": "climate",
        "friendly_name": "Aqara Thermostat E1 Climate",
        "supported_features": 1,
    }

    data = device.decode_lumi([{"res_name": "1.8.85", "value": 2300}])
    climate.async_set_state(data)
    climate.async_write_ha_state()

    state = climate.hass.states.get(climate.entity_id)
    assert state.state == "unknown"
    assert state.attributes["temperature"] == 23.0

    data = device.decode_lumi([{"res_name": "4.21.85", "value": 1}])
    climate.async_set_state(data)
    climate.async_write_ha_state()

    state = climate.hass.states.get(climate.entity_id)
    assert state.state == "unknown"

    data = device.decode_lumi([{"res_name": "14.51.85", "value": 0}])
    climate.async_set_state(data)
    climate.async_write_ha_state()

    state = climate.hass.states.get(climate.entity_id)
    assert state.state == "heat"

    climate.hass.loop.run_until_complete(
        climate.async_set_temperature(temperature=22.5)
    )

    assert gw.mqtt.pub_buffer[0] == [
        "zigbee/recv",
        {
            "params": [{"res_name": "1.8.85", "value": 2250.0}],
            "cmd": "write",
            "did": "lumi.112233aabbcc",
        },
        False,
    ]
