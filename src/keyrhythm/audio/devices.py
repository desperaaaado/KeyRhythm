from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutputDevice:
    index: int
    key: str
    label: str
    host_api: str
    name: str
    low_latency_seconds: float
    default_sample_rate: float


def list_output_devices(sounddevice_module, required_rate: int = 48_000) -> list[OutputDevice]:
    devices = sounddevice_module.query_devices()
    apis = sounddevice_module.query_hostapis()
    result: list[OutputDevice] = []
    for index, device in enumerate(devices):
        if device["max_output_channels"] < 2:
            continue
        api_name = apis[device["hostapi"]]["name"]
        try:
            sounddevice_module.check_output_settings(
                device=index, channels=2, dtype="float32", samplerate=required_rate
            )
        except Exception:
            continue
        key = f"{api_name}::{device['name']}"
        result.append(OutputDevice(
            index=index,
            key=key,
            label=f"{device['name']} — {api_name}",
            host_api=api_name,
            name=device["name"],
            low_latency_seconds=float(device["default_low_output_latency"]),
            default_sample_rate=float(device["default_samplerate"]),
        ))
    return result


def resolve_output_device(sounddevice_module, requested: str | int | None) -> int | None:
    if isinstance(requested, int):
        return requested
    devices = list_output_devices(sounddevice_module)
    if requested:
        exact = next((device for device in devices if device.key == requested), None)
        if exact:
            return exact.index
        same_name = [device for device in devices if device.name == requested]
        if same_name:
            return min(same_name, key=_preference).index
    try:
        default_index = int(sounddevice_module.default.device[1])
        default_name = sounddevice_module.query_devices(default_index)["name"]
        same_hardware = [device for device in devices if device.name == default_name]
        if same_hardware:
            return min(same_hardware, key=_preference).index
    except Exception:
        pass
    wasapi = [device for device in devices if "WASAPI" in device.host_api.upper()]
    if wasapi:
        return min(wasapi, key=_preference).index
    return min(devices, key=_preference).index if devices else None


def _preference(device: OutputDevice) -> tuple[int, float, int]:
    api = device.host_api.upper()
    api_rank = 0 if "WASAPI" in api else 1 if "WDM-KS" in api else 2
    return api_rank, device.low_latency_seconds, device.index

