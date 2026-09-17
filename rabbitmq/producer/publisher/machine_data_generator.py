"""
machine_data_generator.py — Phase 2 stochastic degradation engine.

Public surface (unchanged for publisher.py):
  gen = SyntheticMachineGenerator(machine_id=0, seed=42, accel=1.0)
  reading = gen.generate_one()   # returns extended-schema dict
  events  = gen.pop_events()     # list of machine_runs dicts (cleared on pop)
  state   = gen.serialize()      # full checkpoint dict (JSON-serialisable)
  gen.restore(state)             # resume from checkpoint

Physics / stochastic methods used:
  - Gamma process (exact increments) for monotone cumulative wear per component
  - Weibull-sampled target lifetimes (increasing hazard = wear-out)
  - Poisson shocks for sudden damage jumps
  - Ornstein-Uhlenbeck (exact discretisation) for smooth autocorrelated flows/currents
  - First-order thermal lag (exact exponential) for temperatures
  - Kijima imperfect-repair model
  - Semi-Markov state machine with lognormal sojourn times
  - Production calendar (shifts / night stops / weekends)
  - Configurable imperfection layer (dropouts, outliers, stuck, jitter)
  - Physics coupling: EM_Power = sqrt(3)*V*I*pf, integral totalizers
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def seconds_to_hms(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"

def _lognormal(rng: random.Random, mean_s: float, sigma_frac: float) -> float:
    """Sample lognormal with approximate mean=mean_s, sigma=sigma_frac*mean_s."""
    mu_ln = math.log(mean_s) - 0.5 * math.log(1 + sigma_frac ** 2)
    sig_ln = math.sqrt(math.log(1 + sigma_frac ** 2))
    return math.exp(rng.gauss(mu_ln, sig_ln))

def _poisson_draw(lam: float, rng: random.Random) -> int:
    if lam <= 0:
        return 0
    if lam < 1e-3:
        return 1 if rng.random() < lam else 0
    L, k, p = math.exp(-lam), 0, 1.0
    while p > L:
        k += 1
        p *= rng.random()
    return k - 1

# ---------------------------------------------------------------------------
# Stochastic process primitives
# ---------------------------------------------------------------------------

class GammaWearProcess:
    """Monotone cumulative damage via Gamma-process increments (exact)."""

    def __init__(self, alpha: float, d_fail: float = 100.0):
        # alpha: damage rate per second per unit stress (shape/second/stress)
        self.alpha = alpha
        self.d_fail = d_fail
        self.D = 0.0  # accumulated damage

    def step(self, stress: float, dt: float, rng: random.Random) -> None:
        shape = max(1e-9, self.alpha * max(0.05, stress) * dt)
        # Gamma(shape, scale=1) increment; additive property handles large dt
        self.D += rng.gammavariate(shape, 1.0)

    def add_shock(self, magnitude: float) -> None:
        self.D += magnitude

    def repair(self, effectiveness: float, rng: random.Random) -> None:
        """Kijima model: restore damaged component, don't fully reset."""
        noise = rng.gauss(0, 0.02)
        self.D = max(0.0, self.D * (1.0 - clamp(effectiveness + noise, 0.8, 1.0)))

    @property
    def health(self) -> float:
        return 100.0 * max(0.0, 1.0 - self.D / self.d_fail)

    @property
    def is_failed(self) -> bool:
        return self.D >= self.d_fail


class OUProcess:
    """Ornstein-Uhlenbeck process (exact discretisation — stable for any dt)."""

    def __init__(self, mu: float, theta: float, sigma: float, init: float = None):
        self.mu = mu
        self.theta = theta
        self.sigma = sigma
        self.x = init if init is not None else mu

    def step(self, dt: float, rng: random.Random, mu: float = None) -> float:
        target = mu if mu is not None else self.mu
        e = math.exp(-self.theta * dt)
        var = self.sigma ** 2 * (1.0 - e * e) / (2.0 * self.theta + 1e-12)
        self.x = self.x * e + target * (1.0 - e) + math.sqrt(max(0, var)) * rng.gauss(0, 1)
        return self.x


class ThermalLag:
    """First-order thermal lag (exact exponential — stable for any dt)."""

    def __init__(self, tau: float, init: float):
        self.tau = tau   # time constant in seconds
        self.T = init    # current temperature

    def step(self, target: float, dt: float) -> float:
        self.T = target + (self.T - target) * math.exp(-dt / self.tau)
        return self.T

# ---------------------------------------------------------------------------
# Component degradation
# ---------------------------------------------------------------------------

_COMP_CFG = {
    # name: weibull shape k, mean time to failure (hours), shock rate/h, shock magnitude, d_fail
    "bearing":     dict(k=2.0, mttf_h=350, shock_rate_h=0.40, shock_mag=4.0, d_fail=100.0),
    "steam_valve": dict(k=1.8, mttf_h=500, shock_rate_h=0.20, shock_mag=3.0, d_fail=100.0),
    "heater":      dict(k=1.5, mttf_h=600, shock_rate_h=0.10, shock_mag=2.0, d_fail=100.0),
    "water_pump":  dict(k=2.2, mttf_h=420, shock_rate_h=0.30, shock_mag=3.5, d_fail=100.0),
}

COMPONENTS = list(_COMP_CFG.keys())


class ComponentState:
    """Health + Gamma degradation + Weibull-sampled lifetime per component."""

    def __init__(self, name: str, rng: random.Random, accel: float = 1.0):
        self.name = name
        cfg = _COMP_CFG[name]

        # Weibull-sample target life: L = lam * (-ln U)^(1/k), mean = lam*Gamma(1+1/k)
        k = cfg["k"]
        mean_lam = (cfg["mttf_h"] / accel) / math.gamma(1.0 + 1.0 / k)
        u = clamp(rng.random(), 0.01, 0.99)
        target_h = mean_lam * ((-math.log(u)) ** (1.0 / k))
        target_sec = max(3600.0, target_h * 3600.0)

        # Scale alpha so E[D(target_sec)] = d_fail (stress=1)
        alpha = cfg["d_fail"] / target_sec  # damage/second

        self.wear = GammaWearProcess(alpha=alpha, d_fail=cfg["d_fail"])
        self.shock_rate_s = cfg["shock_rate_h"] * accel / 3600.0
        self.shock_mag = cfg["shock_mag"]

    # ------------------------------------------------------------------
    def step(self, stress: float, dt: float, rng: random.Random) -> None:
        self.wear.step(stress, dt, rng)
        n = _poisson_draw(self.shock_rate_s * dt, rng)
        for _ in range(n):
            self.wear.add_shock(self.shock_mag * rng.uniform(0.5, 1.5))

    def repair(self, rng: random.Random) -> None:
        eff = rng.uniform(0.93, 1.00)
        self.wear.repair(eff, rng)
        self.wear.D = min(self.wear.D, self.wear.d_fail * 0.04)

    def age_others(self, rng: random.Random) -> None:
        """Slight aging from repair activity (Kijima model side-effect)."""
        self.wear.D += rng.uniform(0.0, self.wear.d_fail * 0.02)

    @property
    def health(self) -> float:
        return self.wear.health

    @property
    def is_failed(self) -> bool:
        return self.wear.is_failed

# ---------------------------------------------------------------------------
# Article / lot profiles
# ---------------------------------------------------------------------------

_ARTICLES = [5896, 5897, 5898, 5899, 5900]

_ARTICLE_PROFILE = {
    5896: dict(nominal_speed=25.0, sf_base=2.80, wat_base=12.20),
    5897: dict(nominal_speed=23.5, sf_base=2.95, wat_base=11.80),
    5898: dict(nominal_speed=26.0, sf_base=2.65, wat_base=12.50),
    5899: dict(nominal_speed=24.0, sf_base=2.90, wat_base=12.00),
    5900: dict(nominal_speed=27.0, sf_base=2.70, wat_base=11.60),
}

# ---------------------------------------------------------------------------
# Semi-Markov state machine
# ---------------------------------------------------------------------------

STATES = ("running", "idle", "changeover", "maintenance", "error")

# Shift calendar: operating 06:00–22:00 UTC, off 22:00–06:00 + weekends
_SHIFT_START_H = 6
_SHIFT_END_H = 22

def _in_shift(dt_utc: datetime) -> bool:
    if dt_utc.weekday() >= 5:   # Saturday=5, Sunday=6
        return False
    return _SHIFT_START_H <= dt_utc.hour < _SHIFT_END_H


def _seconds_to_shift_end(dt_utc: datetime) -> float:
    """Seconds until the current shift ends (night stop or weekend)."""
    if dt_utc.weekday() >= 5:
        # Weekend: compute seconds to next Monday 06:00
        days_to_monday = (7 - dt_utc.weekday()) % 7
        if days_to_monday == 0:
            days_to_monday = 7
        target = (dt_utc + timedelta(days=days_to_monday)).replace(
            hour=_SHIFT_START_H, minute=0, second=0, microsecond=0
        )
        return max(60.0, (target - dt_utc).total_seconds())
    if dt_utc.hour < _SHIFT_START_H:
        target = dt_utc.replace(hour=_SHIFT_START_H, minute=0, second=0, microsecond=0)
        return max(60.0, (target - dt_utc).total_seconds())
    if dt_utc.hour >= _SHIFT_END_H:
        # Night stop until tomorrow 06:00
        tomorrow = (dt_utc + timedelta(days=1)).replace(
            hour=_SHIFT_START_H, minute=0, second=0, microsecond=0
        )
        return max(60.0, (tomorrow - dt_utc).total_seconds())
    # Inside shift: seconds until shift ends
    target = dt_utc.replace(hour=_SHIFT_END_H, minute=0, second=0, microsecond=0)
    return max(60.0, (target - dt_utc).total_seconds())

# ---------------------------------------------------------------------------
# Imperfection layer
# ---------------------------------------------------------------------------

class ImperfectionLayer:
    """Dropouts, outliers, stuck sensors, timestamp jitter — all configurable."""

    def __init__(self, cfg: dict, rng: random.Random):
        self.p_drop = cfg.get("p_drop", 0.0)
        self.p_outlier = cfg.get("p_outlier", 0.0)
        self.p_stuck = cfg.get("p_stuck", 0.0)
        self.ts_jitter_ms = cfg.get("ts_jitter_ms", 0.0)
        self._rng = rng
        self._dropout_active: Dict[str, int] = {}  # key → ticks remaining
        self._stuck_val: Dict[str, Any] = {}
        self._stuck_ticks: Dict[str, int] = {}

    def apply(self, key: str, value: Any, ts: datetime) -> Tuple[Any, datetime]:
        if value is None:
            return value, ts

        # Stuck sensor (Markov: enter with p_stuck, last 5-20 ticks)
        if key in self._stuck_ticks and self._stuck_ticks[key] > 0:
            self._stuck_ticks[key] -= 1
            value = self._stuck_val.get(key, value)
        elif self._rng.random() < self.p_stuck:
            self._stuck_ticks[key] = self._rng.randint(5, 20)
            self._stuck_val[key] = value

        # Dropout (bursty Markov)
        if key in self._dropout_active and self._dropout_active[key] > 0:
            self._dropout_active[key] -= 1
            value = None
        elif self._rng.random() < self.p_drop:
            self._dropout_active[key] = self._rng.randint(1, 8)
            value = None

        # Outlier / spike
        if value is not None and self._rng.random() < self.p_outlier:
            if isinstance(value, (int, float)):
                value = value * self._rng.choice([0.1, 3.5])

        # Timestamp jitter
        if self.ts_jitter_ms > 0:
            jitter = self._rng.uniform(-self.ts_jitter_ms, self.ts_jitter_ms)
            ts = ts + timedelta(milliseconds=jitter)

        return value, ts

# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

# Motor electrical constants (22 kW LV motor, 400 V 3-phase, pf=0.85)
_V_LINE = 400.0
_PF = 0.85
_SQRT3 = math.sqrt(3.0)
_N_RUNS_PER_SESSION = 8  # failure cycles before new session_id


class SyntheticMachineGenerator:
    """
    One-machine stochastic degradation generator.
    Call generate_one() to advance one dt-second tick and return a reading dict.
    """

    def __init__(
        self,
        machine_id: int = 0,
        seed: int = None,
        accel: float = 1.0,
        dt: float = 3.0,
        sim_start_ts: datetime = None,
        imperfection_cfg: dict = None,
        no_calendar: bool = False,
    ):
        self.machine_id = machine_id
        self.machine_name = f"Machine {machine_id + 1}"
        self.dt = dt
        self.accel = accel
        self.no_calendar = no_calendar  # if True, skip shift/weekend checks

        self.rng = random.Random(seed if seed is not None else random.randint(0, 2**31))

        # Simulation clock
        self.sim_ts: datetime = sim_start_ts or datetime.now(timezone.utc)

        # Components
        self.components: Dict[str, ComponentState] = {
            name: ComponentState(name, self.rng, accel=accel) for name in COMPONENTS
        }

        # Lot / production tracking (must be set before _init_sensors)
        self.article: int = self.rng.choice(_ARTICLES)

        # Sensor dynamics (OU processes — one per measured signal)
        self._init_sensors()

        # State machine
        self.state: str = "idle"  # start idle, will transition to running
        self.state_remaining_s: float = 5.0  # short initial idle

        self.lot_1: int = self.rng.randint(2_000_000, 2_999_999)
        self.lot_2: int = self.lot_1 + 1
        self.lot_target_m: float = self.rng.uniform(1000.0, 2500.0)
        self.length: float = 0.0
        self.lot_time_s: float = 0.0

        # Cumulative counters (reset each session)
        self.steam_total: float = self.rng.uniform(100.0, 500.0)
        self.water_total: float = self.rng.uniform(500.0, 2000.0)
        self.em_energy_kwh: float = self.rng.uniform(50.0, 200.0)

        # Machine-lifetime counter (never resets)
        self.machine_time_s: float = self.rng.uniform(5000 * 3600, 8000 * 3600)

        # Session tracking
        self.session_id: str = str(uuid.uuid4())
        self.seq: int = 0
        self.repair_count: int = 0  # failure+repair cycles this session

        # Event buffer (machine_runs)
        self._events: List[dict] = []
        self._current_run_start_ts: str = self.sim_ts.isoformat()
        self._current_run_start_seq: int = 0

        # Imperfections
        self._imp = ImperfectionLayer(imperfection_cfg or {}, self.rng)

        # Accumulated quality counts (reset per lot)
        self._good_count: int = 0
        self._reject_count: int = 0

    # ------------------------------------------------------------------
    # Sensor initialisation
    # ------------------------------------------------------------------

    def _init_sensors(self) -> None:
        art = _ARTICLE_PROFILE.get(self.article, _ARTICLE_PROFILE[5896])
        # OU for flows, current, pressure, speed — theta chosen for ~60s correlation time
        self._ou_sf   = OUProcess(mu=art["sf_base"],  theta=0.05, sigma=0.15)
        self._ou_wat  = OUProcess(mu=art["wat_base"], theta=0.05, sigma=0.25)
        self._ou_cur  = OUProcess(mu=30.0,             theta=0.03, sigma=0.8)
        self._ou_vib  = OUProcess(mu=2.0,              theta=0.04, sigma=0.12)
        self._ou_pres = OUProcess(mu=6.0,              theta=0.08, sigma=0.08)
        self._ou_spd  = OUProcess(mu=art["nominal_speed"], theta=0.10, sigma=0.3)
        # Thermal lags — bearing_temp (tau=600s), winding_temp (tau=900s)
        self._tl_bear = ThermalLag(tau=600.0,  init=50.0)
        self._tl_wind = ThermalLag(tau=900.0,  init=72.0)

    # ------------------------------------------------------------------
    # Core tick
    # ------------------------------------------------------------------

    def generate_one(self) -> dict:
        """Advance one dt-second simulation tick; return extended-schema reading."""
        dt = self.dt

        # ── 1. Compute stress from speed and ambient
        art = _ARTICLE_PROFILE.get(self.article, _ARTICLE_PROFILE[5896])
        ambient = 28.0 + 5.0 * math.sin(2 * math.pi * self.sim_ts.hour / 24.0)

        if self.state == "running":
            speed_frac = clamp(self._ou_spd.x / art["nominal_speed"], 0.5, 1.2)
            stress = speed_frac * (1.0 + 0.05 * (ambient - 25.0) / 10.0)
        else:
            stress = 0.0

        # ── 2. Degrade components (only while running)
        if self.state == "running":
            for comp in self.components.values():
                comp.step(stress, dt, self.rng)

        # ── 3. State machine transition
        self._tick_state_machine(dt)

        # ── 4. Compute sensor readings
        reading = self._build_reading(dt, stress, ambient, art)

        # ── 5. Advance clocks
        self.sim_ts += timedelta(seconds=dt)
        self.seq += 1
        if self.state == "running":
            self.machine_time_s += dt
            self.lot_time_s += dt

        return reading

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _tick_state_machine(self, dt: float) -> None:
        if self.state == "running":
            # Check failure
            for name, comp in self.components.items():
                if comp.is_failed:
                    self._enter_error(name)
                    return

            # Check calendar (night stop / weekend)
            if not self.no_calendar and not _in_shift(self.sim_ts):
                idle_sec = _seconds_to_shift_end(self.sim_ts)
                self.state = "idle"
                self.state_remaining_s = idle_sec + self.rng.uniform(-120, 120)
                return

            # Check lot completion
            if self.length >= self.lot_target_m:
                self._start_changeover()
                return

        elif self.state in ("idle", "changeover", "maintenance"):
            self.state_remaining_s -= dt
            if self.state_remaining_s <= 0:
                self._resume_running()

        elif self.state == "error":
            # Should not linger in error; immediately move to maintenance
            self.state_remaining_s -= dt
            if self.state_remaining_s <= 0:
                self._enter_maintenance()

    def _enter_error(self, failed_component: str) -> None:
        # Emit failure event
        self._events.append({
            "session_id": self.session_id,
            "machine_name": self.machine_name,
            "component": failed_component,
            "severity": "failure",
            "run_start_ts": self._current_run_start_ts,
            "failure_ts": self.sim_ts.isoformat(),
            "repair_ts": None,
            "run_hours_to_failure": round((self.machine_time_s - self._current_run_start_machine_time) / 3600.0, 3),
            "seq_at_failure": self.seq,
        })
        self._pending_failed_component = failed_component
        self.state = "error"
        self.state_remaining_s = self.rng.uniform(30, 120)  # brief error state

    def _enter_maintenance(self) -> None:
        self.state = "maintenance"
        self.state_remaining_s = _lognormal(self.rng, 7200.0, 0.45)

    def _resume_running(self) -> None:
        prev_state = self.state

        if prev_state == "maintenance":
            # Repair the failed component, slightly age others
            failed = getattr(self, "_pending_failed_component", None)
            if failed and failed in self.components:
                self.components[failed].repair(self.rng)
                for name, comp in self.components.items():
                    if name != failed:
                        comp.age_others(self.rng)
            # Update repair event
            if self._events:
                self._events[-1]["repair_ts"] = self.sim_ts.isoformat()
            self.repair_count += 1
            # Campaign boundary: new session after N_RUNS_PER_SESSION cycles
            if self.repair_count >= _N_RUNS_PER_SESSION:
                self._start_new_session()
                return

        # A changeover or post-maintenance resume begins a fresh lot; otherwise
        # the completed lot's `length` stays >= target and re-triggers changeover
        # every tick (machine never actually runs).
        if prev_state in ("changeover", "maintenance"):
            self._start_new_lot()

        self.state = "running"
        self._current_run_start_ts = self.sim_ts.isoformat()
        self._current_run_start_machine_time = self.machine_time_s
        self._current_run_start_seq = self.seq

    def _start_changeover(self) -> None:
        self.state = "changeover"
        self.state_remaining_s = _lognormal(self.rng, 2700.0, 0.40)

    def _start_new_session(self) -> None:
        self.session_id = str(uuid.uuid4())
        self.seq = 0
        self.repair_count = 0
        self.steam_total = 0.0
        self.water_total = 0.0
        self.em_energy_kwh = 0.0
        self._start_new_lot()
        self.state = "running"
        self._current_run_start_ts = self.sim_ts.isoformat()
        self._current_run_start_machine_time = self.machine_time_s
        self._current_run_start_seq = 0

    def _start_new_lot(self) -> None:
        self.article = self.rng.choice(_ARTICLES)
        self.lot_1 = self.rng.randint(2_000_000, 2_999_999)
        self.lot_2 = self.lot_1 + 1
        self.lot_target_m = self.rng.uniform(1000.0, 2500.0)
        self.length = 0.0
        self.lot_time_s = 0.0
        self._good_count = 0
        self._reject_count = 0
        # Re-initialise OU processes for new article setpoints
        self._init_sensors()

    # ------------------------------------------------------------------
    # Sensor synthesis
    # ------------------------------------------------------------------

    def _build_reading(
        self, dt: float, stress: float, ambient: float, art: dict
    ) -> dict:
        running = self.state == "running"
        h = {n: c.health for n, c in self.components.items()}  # health [0,100]

        # Degradation fractions [0,1]
        d_bear = 1.0 - h["bearing"] / 100.0
        d_valve = 1.0 - h["steam_valve"] / 100.0
        d_heat = 1.0 - h["heater"] / 100.0
        d_pump = 1.0 - h["water_pump"] / 100.0

        if running:
            # Speed: bearing wear reduces speed
            speed_mu = art["nominal_speed"] * (0.72 + 0.28 * (1.0 - d_bear ** 1.2))
            speed = clamp(self._ou_spd.step(dt, self.rng, mu=speed_mu), 5.0, 35.0)

            # Motor current: rises with bearing + pump degradation
            cur_mu = 30.0 + 10.0 * d_bear ** 1.5 + 5.0 * d_pump ** 1.5
            # Inflated sigma as bearing wears
            self._ou_cur.sigma = 0.8 + 3.0 * d_bear ** 2
            motor_current = clamp(self._ou_cur.step(dt, self.rng, mu=cur_mu), 10.0, 60.0)

            # Vibration: bearing primary signal — accelerating rise
            vib_mu = 2.0 + 6.0 * d_bear ** 1.8
            self._ou_vib.sigma = 0.12 + 1.5 * d_bear ** 1.5
            vibration_rms = clamp(self._ou_vib.step(dt, self.rng, mu=vib_mu), 0.5, 12.0)

            # Bearing temperature (thermal lag)
            bear_target = 50.0 + 38.0 * d_bear ** 1.4 + 5.0 * d_bear
            bearing_temp = clamp(self._tl_bear.step(bear_target, dt), 30.0, 110.0)

            # Winding temperature (heater primary signal)
            wind_target = 72.0 + 58.0 * d_heat ** 1.3 + 8.0 * d_bear
            winding_temp = clamp(self._tl_wind.step(wind_target, dt), 40.0, 145.0)

            # Air pressure: drops with pump degradation
            pres_mu = 6.0 - 1.8 * d_pump ** 1.2
            air_pressure = clamp(self._ou_pres.step(dt, self.rng, mu=pres_mu), 3.5, 7.0)

            # Steam flow: valve degradation → drops and becomes erratic
            sf_mu = art["sf_base"] * (0.30 + 0.70 * (1.0 - d_valve ** 0.8))
            self._ou_sf.sigma = 0.15 + 0.80 * d_valve ** 1.5
            sf_flow = clamp(self._ou_sf.step(dt, self.rng, mu=sf_mu), 0.05, 5.5)

            # Water flow: pump degradation → drops and becomes erratic
            wat_mu = art["wat_base"] * (0.40 + 0.60 * (1.0 - d_pump ** 0.7))
            self._ou_wat.sigma = 0.25 + 1.20 * d_pump ** 1.5
            wat_flow = clamp(self._ou_wat.step(dt, self.rng, mu=wat_mu), 2.0, 16.0)

            # Physics: EM_Power = sqrt(3) * V * I * pf (in kW)
            em_power_kw = (_SQRT3 * _V_LINE * motor_current * _PF) / 1000.0

            # Totalizers
            self.steam_total += sf_flow * dt / 3600.0    # L/min * s → L/60
            self.water_total += wat_flow * dt / 3600.0
            self.em_energy_kwh += em_power_kw * dt / 3600.0
            self.length += speed * dt / 60.0  # m/min * s → m

            # Quality (Binomial): reject rate rises with valve + heater degradation
            reject_rate = clamp(0.01 + 0.20 * d_valve ** 1.2 + 0.20 * d_heat ** 1.2, 0.0, 0.95)
            n_units = max(1, int(speed * dt / 60.0 / 0.5))  # ~0.5m per fabric unit
            n_rejects = sum(1 for _ in range(n_units) if self.rng.random() < reject_rate)
            n_good = n_units - n_rejects
            self._good_count += n_good
            self._reject_count += n_rejects

        else:
            # Not running: sensors settle toward rest/ambient values
            speed = 0.0
            motor_current = clamp(self._ou_cur.step(dt, self.rng, mu=5.0), 0.0, 15.0)
            vibration_rms = clamp(self._ou_vib.step(dt, self.rng, mu=0.3), 0.0, 1.5)
            bearing_temp = clamp(self._tl_bear.step(ambient + 5.0, dt), 20.0, 90.0)
            winding_temp = clamp(self._tl_wind.step(ambient + 10.0, dt), 20.0, 100.0)
            air_pressure = clamp(self._ou_pres.step(dt, self.rng, mu=5.5), 3.0, 7.0)
            sf_flow = clamp(self._ou_sf.step(dt, self.rng, mu=0.1), 0.0, 0.5)
            wat_flow = clamp(self._ou_wat.step(dt, self.rng, mu=0.5), 0.0, 2.0)
            em_power_kw = 0.0
            n_good = 0
            n_rejects = 0

        # Apply imperfections
        ts = self.sim_ts
        sf_flow_out, ts = self._imp.apply("sf_flow", sf_flow, ts)
        wat_flow_out, ts = self._imp.apply("wat_flow", wat_flow, ts)
        em_power_out, _ = self._imp.apply("em_power", em_power_kw if running else None, ts)
        vib_out, _ = self._imp.apply("vibration_rms", vibration_rms, ts)
        cur_out, _ = self._imp.apply("motor_current", motor_current, ts)
        bear_temp_out, _ = self._imp.apply("bearing_temp", bearing_temp, ts)
        wind_temp_out, _ = self._imp.apply("winding_temp", winding_temp, ts)
        pres_out, _ = self._imp.apply("air_pressure", air_pressure, ts)

        def f2(v): return None if v is None else round(float(v), 2)
        def f3(v): return None if v is None else round(float(v), 3)

        return {
            "session_id": self.session_id,
            "seq": self.seq,
            "machine_name": self.machine_name,
            "state": self.state,
            "timestamp": ts.isoformat(),
            "plc": {
                "lot_1": self.lot_1,
                "lot_2": self.lot_2,
                "article": self.article,
                "speed": f2(speed),
                "length": f2(self.length),
                "runmemory": self.state == "running",
                "lot_time": seconds_to_hms(self.lot_time_s),
                "machine_time": seconds_to_hms(self.machine_time_s),
                "steam_consumed_lot": f3(self.steam_total),
                "water_consumed_lot": f3(self.water_total),
                "power_consumed_lot": f2(self.em_energy_kwh),
                "air_consumed_lot": 0,
            },
            "utility": {
                "SF_Flow": f2(sf_flow_out),
                "SF_Tot": f3(self.steam_total),
                "Wat_Flow": f2(wat_flow_out),
                "Wat_Tot": f3(self.water_total),
                "EM_Power": f2(em_power_out),
                "EM_Energy": f2(self.em_energy_kwh),
            },
            "health": {
                "vibration_rms": f2(vib_out),
                "motor_current": f2(cur_out),
                "bearing_temp": f2(bear_temp_out),
                "winding_temp": f2(wind_temp_out),
                "air_pressure": f2(pres_out),
            },
            "quality": {
                "good_count": self._good_count,
                "reject_count": self._reject_count,
            },
            "_truth": {
                "health": {n: round(c.health, 2) for n, c in self.components.items()},
                "active_fault": self.state if self.state in ("error", "maintenance") else None,
                "ambient": round(ambient, 1),
            },
        }

    # ------------------------------------------------------------------
    # Event API
    # ------------------------------------------------------------------

    def pop_events(self) -> List[dict]:
        """Return and clear buffered machine_runs events."""
        out = self._events[:]
        self._events.clear()
        return out

    # ------------------------------------------------------------------
    # Checkpoint / restore
    # ------------------------------------------------------------------

    def serialize(self) -> dict:
        """Return full generator state as a JSON-serialisable dict."""
        rng_state = list(self.rng.getstate())
        rng_state[1] = list(rng_state[1])  # inner tuple → list for JSON
        return {
            "machine_id": self.machine_id,
            "machine_name": self.machine_name,
            "session_id": self.session_id,
            "seq": self.seq,
            "repair_count": self.repair_count,
            "state": self.state,
            "state_remaining_s": self.state_remaining_s,
            "sim_ts": self.sim_ts.isoformat(),
            "machine_time_s": self.machine_time_s,
            "lot_time_s": self.lot_time_s,
            "article": self.article,
            "lot_1": self.lot_1,
            "lot_2": self.lot_2,
            "lot_target_m": self.lot_target_m,
            "length": self.length,
            "steam_total": self.steam_total,
            "water_total": self.water_total,
            "em_energy_kwh": self.em_energy_kwh,
            "good_count": self._good_count,
            "reject_count": self._reject_count,
            "current_run_start_ts": self._current_run_start_ts,
            "current_run_start_machine_time": getattr(self, "_current_run_start_machine_time", self.machine_time_s),
            "current_run_start_seq": self._current_run_start_seq,
            "pending_failed_component": getattr(self, "_pending_failed_component", None),
            "components": {n: {"D": c.wear.D, "d_fail": c.wear.d_fail, "alpha": c.wear.alpha} for n, c in self.components.items()},
            "ou": {
                "sf_x": self._ou_sf.x, "wat_x": self._ou_wat.x,
                "cur_x": self._ou_cur.x, "vib_x": self._ou_vib.x,
                "pres_x": self._ou_pres.x, "spd_x": self._ou_spd.x,
            },
            "tl": {"bear_T": self._tl_bear.T, "wind_T": self._tl_wind.T},
            "rng_state": rng_state,
        }

    def restore(self, s: dict) -> None:
        """Resume from a checkpoint dict produced by serialize()."""
        self.machine_id = s["machine_id"]
        self.machine_name = s["machine_name"]
        self.session_id = s["session_id"]
        self.seq = s["seq"]
        self.repair_count = s["repair_count"]
        self.state = s["state"]
        self.state_remaining_s = s["state_remaining_s"]
        self.sim_ts = datetime.fromisoformat(s["sim_ts"])
        self.machine_time_s = s["machine_time_s"]
        self.lot_time_s = s["lot_time_s"]
        self.article = s["article"]
        self.lot_1 = s["lot_1"]
        self.lot_2 = s["lot_2"]
        self.lot_target_m = s["lot_target_m"]
        self.length = s["length"]
        self.steam_total = s["steam_total"]
        self.water_total = s["water_total"]
        self.em_energy_kwh = s["em_energy_kwh"]
        self._good_count = s["good_count"]
        self._reject_count = s["reject_count"]
        self._current_run_start_ts = s["current_run_start_ts"]
        self._current_run_start_machine_time = s["current_run_start_machine_time"]
        self._current_run_start_seq = s["current_run_start_seq"]
        self._pending_failed_component = s.get("pending_failed_component")

        for name, cd in s["components"].items():
            self.components[name].wear.D = cd["D"]
            self.components[name].wear.d_fail = cd["d_fail"]
            self.components[name].wear.alpha = cd["alpha"]

        ou = s["ou"]
        self._ou_sf.x = ou["sf_x"]
        self._ou_wat.x = ou["wat_x"]
        self._ou_cur.x = ou["cur_x"]
        self._ou_vib.x = ou["vib_x"]
        self._ou_pres.x = ou["pres_x"]
        self._ou_spd.x = ou["spd_x"]

        tl = s["tl"]
        self._tl_bear.T = tl["bear_T"]
        self._tl_wind.T = tl["wind_T"]

        rs = s["rng_state"]
        rs[1] = tuple(rs[1])
        self.rng.setstate(tuple(rs))
