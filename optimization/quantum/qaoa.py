"""Optional QAOA simulator path for a rebalancing QUBO. **Quantum Research Mode** (§14.2).

Strictly research-only and entirely optional. ``qiskit`` is imported lazily; if it is absent the
module exposes an explicit "unavailable" path and its tests are skipped with a documented reason
(§14.2). Results are **simulator** results and are never presented as hardware execution, and no
quantum-advantage claim is made. The operator-facing plan always comes from the classical
solvers; QAOA output never feeds Demo/Replay/Live views (§3).

The QAOA optimum is compared against the exact QUBO brute-force optimum (``qubo.brute_force_qubo``)
so a simulator run is only reported as "matched" when it actually reaches the known ground state.
"""

from __future__ import annotations

from dataclasses import dataclass

from .qubo import QuboProblem, brute_force_qubo


def qiskit_available() -> bool:
    """True iff a qiskit stack that can run the sampling QAOA is importable."""
    try:  # pragma: no cover - exercised only when qiskit is installed
        import qiskit_aer  # noqa: F401
        import qiskit_optimization  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass(frozen=True)
class QaoaResult:
    available: bool
    reason: str
    bits: tuple[int, ...] | None = None
    energy: float | None = None
    matches_bruteforce: bool | None = None


def solve_qaoa(qubo: QuboProblem, *, reps: int = 1, seed: int = 42) -> QaoaResult:
    """Run QAOA on the Aer simulator for the QUBO; degrade cleanly if qiskit is absent.

    Returns a structured result rather than raising, so callers/tests can branch on
    ``available``. When qiskit is present the sampled optimum is checked against the exact
    brute-force ground state of the same QUBO.
    """
    if not qiskit_available():
        return QaoaResult(
            available=False,
            reason="qiskit_optimization / qiskit_aer not installed (Research Mode optional)",
        )

    # pragma: no cover below — only runs in an environment with qiskit installed.
    from qiskit_aer.primitives import Sampler
    from qiskit_algorithms import QAOA
    from qiskit_algorithms.optimizers import COBYLA
    from qiskit_optimization import QuadraticProgram
    from qiskit_optimization.algorithms import MinimumEigenOptimizer

    qp = QuadraticProgram()
    for v in range(qubo.num_vars):
        qp.binary_var(name=f"b{v}")
    linear = {f"b{v}": qubo.linear.get(v, 0.0) for v in range(qubo.num_vars)}
    quadratic = {(f"b{u}", f"b{w}"): c for (u, w), c in qubo.quadratic.items()}
    qp.minimize(constant=qubo.offset, linear=linear, quadratic=quadratic)

    sampler = Sampler(run_options={"seed": seed, "shots": 2048})
    qaoa = QAOA(sampler=sampler, optimizer=COBYLA(), reps=reps)
    result = MinimumEigenOptimizer(qaoa).solve(qp)

    bits = tuple(int(round(x)) for x in result.x)
    energy = float(result.fval)
    _, exact_energy = brute_force_qubo(qubo)
    return QaoaResult(
        available=True,
        reason="qaoa on aer simulator (research mode; simulator, not hardware)",
        bits=bits,
        energy=energy,
        matches_bruteforce=abs(energy - exact_energy) < 1e-6,
    )
