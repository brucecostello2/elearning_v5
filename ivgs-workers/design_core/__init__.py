"""The Design Core — WP-IVGS-12, Phase 1 of the recovery plan.

Normative source: ``dev/design/Instructional_Design_Foundation_for_IVGS_2026-08-29.md``.

⛔ EVERY MODULE IN THIS PACKAGE IS OUTSIDE THE AD-05 §8 FREEZE, AND THAT IS THE
POINT. The eight stage task bodies may be wrapped and not edited. The Design
Contract has to travel from the model's mouth to the database through a stage
body whose two field lists are hard-coded (``stage2_storyboard.py:314-357`` and
``:467-492``), so it travels beside that body instead of through it: the LLM
client offers every parsed response to registered observers, this package
registers one, and the observer forwards the whole contract to the API. Nothing
here monkey-patches anything, and no third freeze exception was requested.
"""
from design_core.contract import (  # noqa: F401
    CONTRACT_VERSION,
    design_contract_schema,
    parse_contract,
    response_format_for,
)
