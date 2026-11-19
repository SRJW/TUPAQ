"""Read and validate iOS battery health telemetry via DiagnosticsService (read-only)."""


def _valid_int(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def parse_battery(raw):
    """Extract only bounded, real iOS IOPMPowerSource metrics; unknown fields stay omitted."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    charge = raw.get('CurrentCapacity')
    if _valid_int(charge, 0, 100):
        result['charge_percent'] = charge
    cycles = raw.get('CycleCount')
    if _valid_int(cycles, 0, 20000):
        result['cycle_count'] = cycles
    design = raw.get('DesignCapacity')
    nominal = raw.get('NominalChargeCapacity')
    raw_max = raw.get('AppleRawMaxCapacity')
    max_mah = nominal if _valid_int(nominal, 100, 30000) else raw_max if _valid_int(raw_max, 100, 30000) else None
    if _valid_int(design, 100, 30000):
        result['design_capacity_mah'] = design
    if max_mah is not None:
        result['max_capacity_mah'] = max_mah
    if 'design_capacity_mah' in result and 'max_capacity_mah' in result:
        pct = round(result['max_capacity_mah'] * 100 / result['design_capacity_mah'], 1)
        if 1 <= pct <= 120:
            result['health_percent'] = min(100.0, pct)
    temp = raw.get('Temperature')
    if _valid_int(temp, -2000, 8000):
        result['temperature_c'] = round(temp / 100, 1)
    voltage = raw.get('Voltage')
    if _valid_int(voltage, 2000, 6000):
        result['voltage_v'] = round(voltage / 1000, 2)
    charging = raw.get('IsCharging')
    if isinstance(charging, bool):
        result['is_charging'] = charging
    external = raw.get('ExternalConnected')
    if isinstance(external, bool):
        result['external_connected'] = external
    return result


async def read_battery(lockdown):
    """Best-effort read-only battery query; returns {} if iOS declines DiagnosticsService."""
    try:
        from pymobiledevice3.services.diagnostics import DiagnosticsService
        async with DiagnosticsService(lockdown) as diag:
            raw = await diag.get_battery()
        return parse_battery(raw)
    except Exception:
        return {}
