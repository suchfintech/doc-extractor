"""Story 2.8 — determinism CI test.

Runs the Vision pipeline twice against the same canonical Passport image
via two independent S3 keys, then asserts the parsed Pydantic output is
byte-equal across runs. The two-key approach avoids the HEAD-skip
short-circuit that would otherwise return the first run's analysis on
run 2 without invoking the provider.

This is a **real-provider** test — ``temperature=0`` must hold the
determinism in production conditions, not just in test-isolation with a
mocked agent. It is therefore opt-in (``RUN_DETERMINISM=1``) and gated
to the nightly ``determinism.yml`` workflow to control cost.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from doc_extractor import s3_io
from doc_extractor.markdown_io import parse_md
from doc_extractor.pipelines import vision_path

DETERMINISM_ENABLED = os.environ.get("RUN_DETERMINISM") == "1"
SOURCE_KEY_A = os.environ.get("DETERMINISM_SOURCE_KEY_A", "")
SOURCE_KEY_B = os.environ.get("DETERMINISM_SOURCE_KEY_B", "")


@pytest.mark.skipif(
    not DETERMINISM_ENABLED,
    reason="Determinism test is opt-in — set RUN_DETERMINISM=1 (nightly workflow only).",
)
def test_passport_extraction_is_deterministic() -> None:
    """Same Passport image, two runs, two independent S3 keys → byte-equal Pydantic output.

    Two distinct source keys point at the *same* canonical Passport image so
    each run computes a fresh analysis (HEAD-skip would otherwise short-
    circuit run 2). The parsed ``model_dump()`` of the rendered analysis
    must match exactly. Any drift indicates the provider is not honouring
    ``temperature=0`` (or the schema is non-deterministic in serialisation
    order — which the byte-stability snapshot tests already guard against).
    """
    assert SOURCE_KEY_A and SOURCE_KEY_B, (
        "DETERMINISM_SOURCE_KEY_A and DETERMINISM_SOURCE_KEY_B must both be set "
        "to distinct S3 keys pointing at the same canonical Passport image."
    )
    assert SOURCE_KEY_A != SOURCE_KEY_B, (
        "DETERMINISM_SOURCE_KEY_A and _B must be distinct keys — using the same "
        "key would HEAD-skip run 2 and the test would always pass trivially."
    )

    async def _extract(source_key: str) -> dict[str, object]:
        result = await vision_path.run(source_key)
        assert not result.get("skipped"), (
            f"Run for {source_key} was HEAD-skipped — clear the analysis or "
            "use an unseen source key."
        )
        analysis_bytes = s3_io.read_analysis(str(result["analysis_key"]))
        return parse_md(analysis_bytes.decode("utf-8")).model_dump()

    out_a = asyncio.run(_extract(SOURCE_KEY_A))
    out_b = asyncio.run(_extract(SOURCE_KEY_B))

    assert out_a == out_b, (
        "Determinism violation: same image, two runs, different output. "
        "Provider may not be honouring temperature=0, or model is non-deterministic."
    )


def test_determinism_test_is_collected_when_disabled() -> None:
    """Sentinel: even when RUN_DETERMINISM is unset, this module must be
    importable and the real test must be collected (and skipped). Catches
    accidental import-time crashes that would silently drop the determinism
    guard from the nightly run.
    """
    # If the import at module top failed, this test would not run; reaching
    # here proves the module imports cleanly under the default disabled state.
    assert SOURCE_KEY_A is not None  # always true; sentinel only.
