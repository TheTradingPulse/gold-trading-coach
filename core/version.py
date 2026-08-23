"""Central application-version metadata for The Trading Pulse.

Foundation Pass 1 introduces one canonical location for NEW code. Legacy engine/scoring
version strings are intentionally preserved until their provenance is migrated safely.
"""

APP_VERSION = "3.4-foundation"
APP_RELEASE_NAME = "V3.4 Foundation"
BASELINE_COMMIT = "08c3603"

# Do not alias historical evidence versions to APP_VERSION. Existing journal/research
# records must retain the engine/scoring version that actually produced them.
