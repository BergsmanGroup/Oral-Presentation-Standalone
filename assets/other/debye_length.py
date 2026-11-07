"""
Debye length calculator for a symmetric electrolyte.

Edit the parameters below, then run:
    python debye_length.py
"""

# ── User parameters ──────────────────────────────────────────────────────────
IONIC_STRENGTH      = 0.001    # mol / L  (= 0.5 * sum(z_i^2 * c_i))
TEMPERATURE         = 298.15  # K
RELATIVE_PERMITTIVITY = 78.4  # dimensionless  (water ≈ 78.4 at 25 °C)
VALENCE             = 1       # |z|  (symmetric z:z electrolyte)
# ─────────────────────────────────────────────────────────────────────────────

import math

# Physical constants (SI)
EPS_0 = 8.8541878128e-12   # F / m        vacuum permittivity
K_B   = 1.380649e-23       # J / K        Boltzmann constant
N_A   = 6.02214076e23      # mol^-1       Avogadro's number
E     = 1.602176634e-19    # C            elementary charge

# Convert ionic strength from mol/L → mol/m³
I_SI = IONIC_STRENGTH * 1e3  # mol / m³

# Debye length: λ = sqrt(ε_r ε_0 k_B T / (2 N_A e² z² I))
numerator   = RELATIVE_PERMITTIVITY * EPS_0 * K_B * TEMPERATURE
denominator = 2.0 * N_A * (E ** 2) * (VALENCE ** 2) * I_SI
lambda_D_m  = math.sqrt(numerator / denominator)

lambda_D_nm = lambda_D_m * 1e9
lambda_D_A  = lambda_D_m * 1e10

print("=" * 44)
print("  Debye Length Calculator")
print("=" * 44)
print(f"  Ionic strength      : {IONIC_STRENGTH}  mol/L")
print(f"  Temperature         : {TEMPERATURE}  K")
print(f"  Rel. permittivity   : {RELATIVE_PERMITTIVITY}")
print(f"  Valence (|z|)       : {VALENCE}")
print("-" * 44)
print(f"  Debye length (λ_D)  : {lambda_D_m:.4e}  m")
print(f"                        {lambda_D_nm:.4f}  nm")
print(f"                        {lambda_D_A:.4f}  Å")
print("=" * 44)
