"""
IVGS v5 — Temporal shadow of the eight-stage pipeline (WP-41-TEMPORAL-PREP).

This package is the **shadow implementation** authorised by AD-05 Draft 2
(APPROVED 2026-08-22). It touches no production path:

  * it registers no Celery task and is imported by no Celery worker;
  * its activities are STUBS — no GPU call, no engine client, no Pipeline API,
    no database, no SeaweedFS;
  * it imports from ``models.task_result`` and never writes to it.

What it *is* is the real workflow shape: the eight stages in spec order, the
two human gates as signals, the media fan-out as three distinct labelled
branches, the retry/timeout policy of AD-05 Draft 2 Appendix C, and the
idempotency binding WP-31 Lane C measured into existence.

Module layout (AD-05 §5, §6, §9; Draft 2 §5)
--------------------------------------------

===================  =========================================================
``dag.py``           Execution order as DATA: ``DagNode``, ``build_pipeline_dag``
                     from a storyboard, and the pure ``topological_waves``
                     compiler. Draft 2 §5. No Temporal import.
``policies.py``      Retry / timeout / heartbeat policy per activity, carrying
                     BOTH today's Celery constants and AD-05's target values so
                     the translation is visible. §9, Appendix C. No Temporal
                     import.
``idempotency.py``   The ``(job_id, stage, scene_index)`` key scheme and a
                     file-backed effect store that makes a twice-delivered
                     activity produce one effect. Draft 2 §6. No Temporal
                     import.
``payloads.py``      Activity input/output shapes, mirroring the live stage
                     models field for field. No Temporal import.
``conformance.py``   Loader for a banked reference run's checkpoint record,
                     and the comparison against a compiled DAG. No Temporal
                     import.
``activities.py``    The stub activity bodies. Requires ``temporalio``.
``workflow.py``      ``VideoPipelineWorkflow`` — walks the waves, holds the
                     signals and the state query. Requires ``temporalio``.
``worker.py``        The dev worker process for the node-07 cluster.
``client.py``        Driver CLI: start / signal / query / result / history.
===================  =========================================================

The first six modules import nothing from ``temporalio``, deliberately: the DAG
compiler, the policy table, the key scheme and the conformance check are all
unit-testable in the repo's existing venv, which has no Temporal SDK in it.
"""
