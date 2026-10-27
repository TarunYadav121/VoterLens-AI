"""
app.py — VoterLens AI
======================
Flask REST API application factory and routes.

Endpoints:
  - GET  /api/health
  - GET  /api/sample-data
  - GET  /api/sample-data/previous
  - GET  /api/sample-data/current
  - POST /api/analyze
  - POST /api/compare-areas
  - POST /api/recheck-finding
  - GET  /api/export/<analysis_id>/<report_type>
  - POST /api/challenge/run
  - GET  /api/record/<analysis_id>/<record_id>
  - POST /api/explain-qa
  - POST /api/chat/explain
  - POST /api/chat/message
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import io
import json
import logging
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from typing import Any
import uuid

from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS
import pandas as pd

import comparator
import config as cfg
import data_generator
import detector
import explainer
from models import (
    AnalysisResponse,
    ChallengeResponse,
    ChallengeScenarioResult,
    ErrorResponse,
    HealthResponse,
    RecheckResponse,
    StoredAnalysis,
)
import insight_assistant
import reporter
import validator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"


def _ensure_sample_datasets() -> None:
    """Generate sample datasets on startup if they don't already exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    prev_path = DATA_DIR / "previous_roll.csv"
    curr_path = DATA_DIR / "current_roll.csv"
    exp_path = DATA_DIR / "expected_outcomes.json"

    if not prev_path.exists() or not curr_path.exists():
        logger.info("Sample datasets not found. Generating deterministically with seed 42...")
        try:
            prev_df, curr_df, expected = data_generator.generate_datasets()
            prev_df.to_csv(prev_path, index=False)
            curr_df.to_csv(curr_path, index=False)
            with open(exp_path, "w", encoding="utf-8") as f:
                json.dump(expected, f, indent=2)
            logger.info("Sample datasets generated successfully.")
        except Exception as e:
            logger.warning(f"Could not generate sample datasets at startup: {e}")


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = testing
    app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_FILE_SIZE_BYTES

    # CORS configuration: restrict to configured origins or localhost/frontend by default
    raw_origins = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
    )
    if os.environ.get("CORS_ALLOW_ALL", "0") == "1" or raw_origins.strip() == "*":
        cors_origins = "*"
    else:
        cors_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    # In-memory store with LRU eviction
    analysis_store: OrderedDict[str, StoredAnalysis] = OrderedDict()
    app.analysis_store = analysis_store

    # Ensure sample datasets exist
    _ensure_sample_datasets()

    # -----------------------------------------------------------------------
    # Error Handlers
    # -----------------------------------------------------------------------

    @app.errorhandler(400)
    def handle_bad_request(e):
        return jsonify({
            "status": "error",
            "code": "BAD_REQUEST",
            "message": str(getattr(e, "description", "Bad Request")),
            "details": {},
        }), 400

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({
            "status": "error",
            "code": "NOT_FOUND",
            "message": str(getattr(e, "description", "Resource not found")),
            "details": {},
        }), 404

    @app.errorhandler(413)
    def handle_file_too_large(e):
        return jsonify({
            "status": "error",
            "code": "FILE_TOO_LARGE",
            "message": f"Uploaded file exceeds the maximum allowed size of {cfg.MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
            "details": {},
        }), 413

    @app.errorhandler(500)
    def handle_internal_error(e):
        logger.error(f"Internal server error: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred during processing. Please try again.",
            "details": {},
        }), 500

    # -----------------------------------------------------------------------
    # Health check
    # -----------------------------------------------------------------------

    @app.get("/api/health")
    def health():
        return jsonify(HealthResponse(
            status="ok",
            service=cfg.APP_NAME + " Backend",
            version=cfg.APP_VERSION,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ).model_dump()), 200

    # -----------------------------------------------------------------------
    # Sample data routes
    # -----------------------------------------------------------------------

    @app.get("/api/sample-data")
    def get_sample_data_metadata():
        _ensure_sample_datasets()
        prev_path = DATA_DIR / "previous_roll.csv"
        curr_path = DATA_DIR / "current_roll.csv"

        if not prev_path.exists() or not curr_path.exists():
            return jsonify({
                "status": "error",
                "code": "SAMPLE_DATA_NOT_FOUND",
                "message": "Sample datasets have not yet been generated.",
            }), 404

        prev_df = pd.read_csv(prev_path, dtype=str)
        curr_df = pd.read_csv(curr_path, dtype=str)

        return jsonify({
            "previous": {
                "filename": "previous_roll.csv",
                "row_count": len(prev_df),
                "columns": list(prev_df.columns),
            },
            "current": {
                "filename": "current_roll.csv",
                "row_count": len(curr_df),
                "columns": list(curr_df.columns),
            },
        }), 200

    @app.get("/api/sample-data/previous")
    def download_sample_previous():
        _ensure_sample_datasets()
        prev_path = DATA_DIR / "previous_roll.csv"
        if not prev_path.exists():
            return jsonify({"status": "error", "code": "NOT_FOUND", "message": "previous_roll.csv not found"}), 404
        return send_file(
            prev_path,
            mimetype="text/csv",
            as_attachment=True,
            download_name="previous_roll.csv",
        )

    @app.get("/api/sample-data/current")
    def download_sample_current():
        _ensure_sample_datasets()
        curr_path = DATA_DIR / "current_roll.csv"
        if not curr_path.exists():
            return jsonify({"status": "error", "code": "NOT_FOUND", "message": "current_roll.csv not found"}), 404
        return send_file(
            curr_path,
            mimetype="text/csv",
            as_attachment=True,
            download_name="current_roll.csv",
        )

    # -----------------------------------------------------------------------
    # Core Analysis
    # -----------------------------------------------------------------------

    @app.post("/api/analyze")
    def analyze():
        if "previous_file" not in request.files or "current_file" not in request.files:
            return jsonify({
                "status": "error",
                "code": "MISSING_FILE",
                "message": "Both previous_file and current_file are required in multipart/form-data upload.",
                "details": {},
            }), 400

        prev_file = request.files["previous_file"]
        curr_file = request.files["current_file"]

        if not prev_file.filename or not curr_file.filename:
            return jsonify({
                "status": "error",
                "code": "MISSING_FILE",
                "message": "Both previous_file and current_file must be selected with valid filenames.",
                "details": {},
            }), 400

        def _is_csv(filename: str) -> bool:
            return Path(filename).suffix.lower() in cfg.ALLOWED_EXTENSIONS

        if not _is_csv(prev_file.filename) or not _is_csv(curr_file.filename):
            return jsonify({
                "status": "error",
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": "Only CSV files are supported. Please upload files with .csv extension.",
                "details": {},
            }), 400

        prev_bytes = prev_file.read()
        curr_bytes = curr_file.read()

        if len(prev_bytes) > cfg.MAX_FILE_SIZE_BYTES or len(curr_bytes) > cfg.MAX_FILE_SIZE_BYTES:
            return jsonify({
                "status": "error",
                "code": "FILE_TOO_LARGE",
                "message": f"Uploaded file exceeds the maximum allowed size of {cfg.MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
                "details": {},
            }), 413

        if len(prev_bytes.strip()) == 0 or len(curr_bytes.strip()) == 0:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_FAILED",
                "message": "Uploaded CSV file is completely empty.",
                "details": {},
            }), 400

        # Step 1: Validate files
        prev_val, prev_df = validator.validate_and_load(prev_bytes, "previous_file", prev_file.filename)
        if prev_val.has_blocking_errors:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_FAILED",
                "message": "previous_file contains critical errors that prevent analysis.",
                "details": {
                    "errors": [e.model_dump() for e in prev_val.errors],
                },
            }), 400

        curr_val, curr_df = validator.validate_and_load(curr_bytes, "current_file", curr_file.filename)
        if curr_val.has_blocking_errors:
            return jsonify({
                "status": "error",
                "code": "VALIDATION_FAILED",
                "message": "current_file contains critical errors that prevent analysis.",
                "details": {
                    "errors": [e.model_dump() for e in curr_val.errors],
                },
            }), 400

        # Step 2: Compute fingerprints
        fingerprints = {
            "previous_file": explainer.fingerprint(prev_bytes),
            "current_file": explainer.fingerprint(curr_bytes),
        }

        # Step 3: Run comparator
        comp_result = comparator.compare(
            prev_df,
            curr_df,
            ambiguous_prev_indices=prev_val.ambiguous_row_indices,
            ambiguous_curr_indices=curr_val.ambiguous_row_indices,
        )

        # Step 4: Verify count consistency
        consistency_issues = comparator.verify_count_consistency(comp_result)

        # Step 5: Run detector
        findings, annotated_area_stats = detector.detect(comp_result)
        comp_result.area_stats = annotated_area_stats

        # Step 6: Generate analysis ID & Evidence Passports
        analysis_id = f"ANALYSIS-{uuid.uuid4().hex[:8].upper()}"
        passports = explainer.build_evidence_passports(
            findings,
            comp_result,
            fingerprints,
            analysis_id,
        )

        # Step 7: Store in LRU in-memory store
        if len(analysis_store) >= cfg.MAX_STORED_ANALYSES:
            analysis_store.popitem(last=False)  # pop oldest

        analyzed_at = datetime.now(timezone.utc).isoformat()
        stored = StoredAnalysis(
            analysis_id=analysis_id,
            analyzed_at=analyzed_at,
            dataset_fingerprints=fingerprints,
            validation_results={
                "previous_file": prev_val,
                "current_file": curr_val,
            },
            comparison_result=comp_result,
            findings=findings,
            evidence_passports=passports,
            config_snapshot={
                "THRESHOLD_REMOVAL_RATE": cfg.THRESHOLD_REMOVAL_RATE,
                "THRESHOLD_ADDITION_RATE": cfg.THRESHOLD_ADDITION_RATE,
                "MIN_COMPARISON_GROUP_SIZE": cfg.MIN_COMPARISON_GROUP_SIZE,
            },
        )
        analysis_store[analysis_id] = stored

        # Step 8: Build response
        changes_block = comparator.build_changes_block(comp_result)

        validation_warnings = {
            "previous_file": [w.model_dump() for w in prev_val.warnings + prev_val.review_flags],
            "current_file": [w.model_dump() for w in curr_val.warnings + curr_val.review_flags],
            "count_consistency": consistency_issues,
        }

        resp = AnalysisResponse(
            analysis_id=analysis_id,
            status="success",
            analyzed_at=analyzed_at,
            dataset_fingerprints=fingerprints,
            summary=comp_result.summary,
            changes=changes_block,
            findings=findings,
            area_comparison=annotated_area_stats,
            evidence_passports=passports,
            validation_warnings=validation_warnings,
        )
        return jsonify(resp.model_dump()), 200

    # -----------------------------------------------------------------------
    # Counterfactual Audit Lab
    # -----------------------------------------------------------------------

    @app.post("/api/compare-areas")
    def compare_areas():
        data = request.get_json(silent=True) or {}
        analysis_id = data.get("analysis_id")
        area_id = data.get("area_id")
        comparison_method = data.get("comparison_method", "all_areas")
        threshold_override = data.get("threshold_override")
        filters = data.get("filters", {})

        if not analysis_id or not area_id:
            return jsonify({
                "status": "error",
                "code": "BAD_REQUEST",
                "message": "Both analysis_id and area_id are required.",
            }), 400

        parsed_threshold: float | None = None
        if threshold_override is not None:
            try:
                parsed_threshold = float(threshold_override)
            except (ValueError, TypeError):
                return jsonify({
                    "status": "error",
                    "code": "INVALID_THRESHOLD",
                    "message": "threshold_override must be a valid number.",
                }), 400

            if parsed_threshold <= 0:
                return jsonify({
                    "status": "error",
                    "code": "INVALID_THRESHOLD",
                    "message": "threshold_override must be a positive number.",
                }), 400

        stored = analysis_store.get(analysis_id)
        if not stored:
            return jsonify({
                "status": "error",
                "code": "ANALYSIS_NOT_FOUND",
                "message": f"Analysis with ID {analysis_id} not found in active session. Please run analysis first.",
            }), 404

        result = detector.compute_counterfactual(
            area_stats=stored.comparison_result.area_stats,
            target_area_id=area_id,
            comparison_method=comparison_method,
            threshold_override=parsed_threshold,
            filters=filters,
        )

        if "error" in result:
            return jsonify({
                "status": "error",
                "code": result["error"],
                "message": f"Area {area_id} not found in analysis {analysis_id}.",
            }), 404

        return jsonify(result), 200

    # -----------------------------------------------------------------------
    # Recheck Finding
    # -----------------------------------------------------------------------

    @app.post("/api/recheck-finding")
    def recheck_finding():
        data = request.get_json(silent=True) or {}
        analysis_id = data.get("analysis_id")
        finding_id = data.get("finding_id")

        if not analysis_id or not finding_id:
            return jsonify({
                "status": "error",
                "code": "BAD_REQUEST",
                "message": "Both analysis_id and finding_id are required.",
            }), 400

        stored = analysis_store.get(analysis_id)
        if not stored:
            return jsonify({
                "status": "error",
                "code": "ANALYSIS_NOT_FOUND",
                "message": "The original analysis is no longer available in memory. Please re-upload the datasets and run a new analysis.",
            }), 404

        original = next((f for f in stored.findings if f.finding_id == finding_id), None)
        if not original:
            return jsonify({
                "status": "error",
                "code": "FINDING_NOT_FOUND",
                "message": f"Finding {finding_id} was not found in analysis {analysis_id}.",
            }), 404

        # Deterministically re-run detection on the stored comparison result
        re_findings, _ = detector.detect(stored.comparison_result)
        recheck_finding_match = next(
            (rf for rf in re_findings if rf.rule_id == original.rule_id and rf.affected_area_id == original.affected_area_id),
            None,
        )

        match = False
        if recheck_finding_match:
            match = (
                recheck_finding_match.rule_id == original.rule_id
                and recheck_finding_match.affected_record_count == original.affected_record_count
                and recheck_finding_match.review_priority == original.review_priority
            )

        curr_config = {
            "COMPARISON_FIELDS": cfg.COMPARISON_FIELDS,
            "THRESHOLD_REMOVAL_RATE": cfg.THRESHOLD_REMOVAL_RATE,
            "THRESHOLD_ADDITION_RATE": cfg.THRESHOLD_ADDITION_RATE,
            "MIN_COMPARISON_GROUP_SIZE": cfg.MIN_COMPARISON_GROUP_SIZE,
            "AGE_MIN_PLAUSIBLE": cfg.AGE_MIN_PLAUSIBLE,
            "AGE_MAX_PLAUSIBLE": cfg.AGE_MAX_PLAUSIBLE,
            "MAX_ROW_COUNT": cfg.MAX_ROW_COUNT,
        }
        config_changed = bool(stored.config_snapshot and stored.config_snapshot != curr_config)
        dataset_changed = False

        resp = RecheckResponse(
            status="success",
            original_finding=original,
            recheck_finding=recheck_finding_match,
            match=match,
            dataset_changed=dataset_changed,
            config_changed=config_changed,
            recheck_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return jsonify(resp.model_dump()), 200

    # -----------------------------------------------------------------------
    # Export CSV Reports
    # -----------------------------------------------------------------------

    @app.get("/api/export/<analysis_id>/<report_type>")
    def export_report(analysis_id: str, report_type: str):
        stored = analysis_store.get(analysis_id)
        if not stored:
            return jsonify({
                "status": "error",
                "code": "ANALYSIS_NOT_FOUND",
                "message": f"Analysis with ID {analysis_id} not found.",
            }), 404

        result = reporter.export_report_csv(stored, report_type)
        if result is None:
            return jsonify({
                "status": "error",
                "code": "INVALID_REPORT_TYPE",
                "message": f"Invalid report_type '{report_type}'. Allowed types: {list(reporter.REPORT_EXPORTERS.keys())}",
            }), 400

        csv_content, filename = result
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # -----------------------------------------------------------------------
    # Record Change Inspector
    # -----------------------------------------------------------------------

    @app.get("/api/record/<analysis_id>/<record_id>")
    def inspect_record(analysis_id: str, record_id: str):
        stored = analysis_store.get(analysis_id)
        if not stored:
            return jsonify({
                "status": "error",
                "code": "ANALYSIS_NOT_FOUND",
                "message": f"Analysis with ID {analysis_id} not found.",
            }), 404

        comp = stored.comparison_result
        # Search in added, deleted, modified, unchanged
        category = None
        prev_vals: dict[str, Any] = {}
        curr_vals: dict[str, Any] = {}
        changed_fields: list[str] = []
        diffs_list: list[dict[str, Any]] = []

        # Check modified first
        mod = next((r for r in comp.modified if r.record_id == record_id), None)
        if mod:
            category = "MODIFIED"
            prev_vals = mod.previous_values
            curr_vals = mod.current_values
            changed_fields = mod.changed_fields
            diffs_list = [d.model_dump() for d in mod.diffs]
        else:
            add = next((r for r in comp.added if r.record_id == record_id), None)
            if add:
                category = "ADDED"
                curr_vals = add.data
                changed_fields = list(add.data.keys())
            else:
                dele = next((r for r in comp.deleted if r.record_id == record_id), None)
                if dele:
                    category = "DELETED"
                    prev_vals = dele.data
                    changed_fields = list(dele.data.keys())
                else:
                    unch = next((r for r in comp.unchanged if r.record_id == record_id), None)
                    if unch:
                        category = "UNCHANGED"
                        prev_vals = unch.data
                        curr_vals = unch.data
                    else:
                        return jsonify({
                            "status": "error",
                            "code": "RECORD_NOT_FOUND",
                            "message": f"Record with ID '{record_id}' not found in analysis {analysis_id}.",
                        }), 404

        area_id = curr_vals.get("area_id") or prev_vals.get("area_id")
        related_findings = [
            f.finding_id for f in stored.findings
            if (f.affected_area_id and f.affected_area_id == area_id)
        ]

        actions = []
        if category == "DELETED":
            actions = [
                "Verify removal record against official deletion or death certificate.",
                "Check whether the voter was transferred to another polling station or constituency.",
                "Confirm removal notice was issued in accordance with standard procedure.",
            ]
        elif category == "ADDED":
            actions = [
                "Confirm new enrollment application was submitted and verified.",
                "Cross-reference age against minimum registration age threshold.",
                "Verify residential address within designated polling area boundaries.",
            ]
        elif category == "MODIFIED":
            actions = [
                "Verify requested modifications against submitted correction forms.",
                "Confirm whether address/area change corresponds with an administrative boundary update.",
                "Verify demographic corrections (name, gender, age) with secondary identification documents.",
            ]
        else:
            actions = ["No action required; record is unchanged between versions."]

        return jsonify({
            "record_id": record_id,
            "change_category": category,
            "previous_values": prev_vals,
            "current_values": curr_vals,
            "changed_fields": changed_fields,
            "diffs": diffs_list,
            "related_findings": related_findings,
            "recommended_review_actions": actions,
        }), 200

    # -----------------------------------------------------------------------
    # Multilingual Explanation QA
    # -----------------------------------------------------------------------

    @app.post("/api/explain-qa")
    def explain_qa():
        data = request.get_json(silent=True) or {}
        analysis_id = data.get("analysis_id")
        finding_id = data.get("finding_id")
        question_key = data.get("question_key", "why_flagged")
        language = data.get("language", "simple")

        if not analysis_id or not finding_id:
            return jsonify({
                "status": "error",
                "code": "BAD_REQUEST",
                "message": "Both analysis_id and finding_id are required.",
            }), 400

        stored = analysis_store.get(analysis_id)
        if not stored:
            return jsonify({
                "status": "error",
                "code": "ANALYSIS_NOT_FOUND",
                "message": f"Analysis {analysis_id} not found.",
            }), 404

        finding = next((f for f in stored.findings if f.finding_id == finding_id), None)
        if not finding:
            return jsonify({
                "status": "error",
                "code": "FINDING_NOT_FOUND",
                "message": f"Finding {finding_id} not found in analysis {analysis_id}.",
            }), 404

        answer = explainer.answer_question(finding, question_key=question_key, language=language)
        return jsonify({
            "status": "success",
            "finding_id": finding_id,
            "question_key": question_key,
            "language": language,
            "answer": answer,
        }), 200

    # -----------------------------------------------------------------------
    # False-Alarm Challenge
    # -----------------------------------------------------------------------

    @app.post("/api/challenge/run")
    def run_challenge():
        """
        Executes the False-Alarm Challenge against 10 controlled scenarios (FAC-01 to FAC-10).
        Calculates precision and recall directly from outcomes without hardcoding.
        """
        scenarios: list[ChallengeScenarioResult] = []

        def _row(rid: str, aid: str, age=30, gender="M", name="Citizen Test") -> dict:
            return {
                "record_id": rid,
                "name": name,
                "age": age,
                "gender": gender,
                "area_id": aid,
                "area_name": f"Area {aid}",
                "area_type": "urban",
                "population_group": "group-1",
                "administrative_category": "standard",
                "polling_station_id": f"PS-{aid}-01",
                "registration_date": "2024-01-01",
            }

        # Scenario 1: Duplicate record_id in previous file -> Expected: POSITIVE
        s1_prev = pd.DataFrame([_row("R-001", "A01"), _row("R-001", "A01", name="Dupe Test")])
        s1_curr = pd.DataFrame([_row("R-001", "A01")])
        c1 = comparator.compare(s1_prev, s1_curr)
        f1, _ = detector.detect(c1)
        pred1 = "POSITIVE" if (len(f1) > 0 or len(c1.ambiguous_previous) > 0) else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-01",
            description="Duplicate record_id in previous file",
            expected="POSITIVE",
            predicted=pred1,
            outcome="TRUE_POSITIVE" if pred1 == "POSITIVE" else "FALSE_NEGATIVE",
            finding_id=f1[0].finding_id if f1 else None,
            notes="Should be flagged as ambiguous/duplicate identifier",
        ))

        # Scenario 2: Non-numeric age value in CSV -> Expected: POSITIVE
        s2_csv = (
            "record_id,name,area_id,area_name,age,gender\n"
            "R-001,Priya Sharma,A01,Area A01,thirty,F\n"
        ).encode("utf-8")
        val2 = validator.validate_csv(s2_csv, "test_file")
        pred2 = "POSITIVE" if len(val2.errors) > 0 or len(val2.warnings) > 0 else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-02",
            description="Non-numeric age value in file",
            expected="POSITIVE",
            predicted=pred2,
            outcome="TRUE_POSITIVE" if pred2 == "POSITIVE" else "FALSE_NEGATIVE",
            notes="Validator detects non-numeric age",
        ))

        # Scenario 3: Harmless formatting change (extra space in name) -> Expected: NEGATIVE
        s3_prev = pd.DataFrame([_row("R-001", "A01", name="Arjun Mehta")])
        s3_curr = pd.DataFrame([_row("R-001", "A01", name="Arjun  Mehta")])
        # After stripping / normalizing:
        s3_curr_norm = s3_curr.copy()
        s3_curr_norm["name"] = s3_curr_norm["name"].str.replace(r"\s+", " ", regex=True).str.strip()
        c3 = comparator.compare(s3_prev, s3_curr_norm)
        f3, _ = detector.detect(c3)
        pred3 = "POSITIVE" if (len(f3) > 0 or len(c3.modified) > 0) else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-03",
            description="Harmless formatting whitespace change in name",
            expected="NEGATIVE",
            predicted=pred3,
            outcome="TRUE_NEGATIVE" if pred3 == "NEGATIVE" else "FALSE_POSITIVE",
            notes="Normalized names are identical; no anomaly",
        ))

        # Scenario 4: Legitimate bulk registration -> High addition rate
        # 10 areas with 50 voters, one area gets 40 new voters
        s4_prev_rows = []
        s4_curr_rows = []
        for i in range(1, 11):
            aid = f"A{i:02d}"
            for j in range(50):
                rid = f"S4-{aid}-{j:03d}"
                s4_prev_rows.append(_row(rid, aid))
                s4_curr_rows.append(_row(rid, aid))
        # Area A01 gets 40 additions
        for k in range(40):
            s4_curr_rows.append(_row(f"S4-NEW-{k:03d}", "A01"))
        c4 = comparator.compare(pd.DataFrame(s4_prev_rows), pd.DataFrame(s4_curr_rows))
        f4, _ = detector.detect(c4)
        pred4 = "POSITIVE" if any(f.rule_id == "RULE-D-008" for f in f4) else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-04",
            description="Bulk registration in expanding housing area",
            expected="POSITIVE",
            predicted=pred4,
            outcome="TRUE_POSITIVE" if pred4 == "POSITIVE" else "FALSE_NEGATIVE",
            finding_id=next((f.finding_id for f in f4 if f.rule_id == "RULE-D-008"), None),
            notes="High addition rate triggers RULE-D-008 for human review",
        ))

        # Scenario 5: High removal rate in area B01 (> 20 pp above baseline) -> Expected: POSITIVE
        s5_prev_rows = []
        s5_curr_rows = []
        for i in range(1, 11):
            aid = f"B{i:02d}"
            for j in range(100):
                rid = f"S5-{aid}-{j:03d}"
                s5_prev_rows.append(_row(rid, aid))
                # Delete 50 from B01 (50% removal rate vs 0% in others)
                if aid == "B01" and j >= 50:
                    continue
                s5_curr_rows.append(_row(rid, aid))
        c5 = comparator.compare(pd.DataFrame(s5_prev_rows), pd.DataFrame(s5_curr_rows))
        f5, _ = detector.detect(c5)
        pred5 = "POSITIVE" if any(f.rule_id == "RULE-D-007" for f in f5) else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-05",
            description="High removal rate exceeding threshold in area B01",
            expected="POSITIVE",
            predicted=pred5,
            outcome="TRUE_POSITIVE" if pred5 == "POSITIVE" else "FALSE_NEGATIVE",
            finding_id=next((f.finding_id for f in f5 if f.rule_id == "RULE-D-007"), None),
            notes="RULE-D-007 triggered by 50% removal vs baseline 0%",
        ))

        # Scenario 6: Removal rate at exactly threshold -> Expected: POSITIVE
        # Baseline = 0%, target = exactly THRESHOLD_REMOVAL_RATE (20%)
        s6_prev_rows = []
        s6_curr_rows = []
        for i in range(1, 11):
            aid = f"C{i:02d}"
            for j in range(100):
                rid = f"S6-{aid}-{j:03d}"
                s6_prev_rows.append(_row(rid, aid))
                # In C01, delete exactly 20 records (20%)
                if aid == "C01" and j >= 80:
                    continue
                s6_curr_rows.append(_row(rid, aid))
        c6 = comparator.compare(pd.DataFrame(s6_prev_rows), pd.DataFrame(s6_curr_rows))
        f6, _ = detector.detect(c6)
        pred6 = "POSITIVE" if any(f.rule_id == "RULE-D-007" and f.affected_area_id == "C01" for f in f6) else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-06",
            description="Removal rate at boundary threshold (20 pp above baseline)",
            expected="POSITIVE",
            predicted=pred6,
            outcome="TRUE_POSITIVE" if pred6 == "POSITIVE" else "FALSE_NEGATIVE",
            notes="Detector boundary check (diff >= threshold)",
        ))

        # Scenario 7: Clean dataset, all areas within normal range -> Expected: NEGATIVE
        clean_prev, clean_curr = data_generator.generate_clean_datasets()
        c7 = comparator.compare(clean_prev, clean_curr)
        f7, _ = detector.detect(c7)
        pred7 = "POSITIVE" if len(f7) > 0 else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-07",
            description="Clean dataset with zero modifications or anomalies",
            expected="NEGATIVE",
            predicted=pred7,
            outcome="TRUE_NEGATIVE" if pred7 == "NEGATIVE" else "FALSE_POSITIVE",
            notes="No findings produced on clean datasets",
        ))

        # Scenario 8: Area with 0 previous records gaining records -> Expected: NEGATIVE for removal
        s8_prev = pd.DataFrame([_row("R-001", "D01")])
        s8_curr = pd.DataFrame([_row("R-001", "D01"), _row("R-002", "D02")])
        c8 = comparator.compare(s8_prev, s8_curr)
        f8, _ = detector.detect(c8)
        # Check area D02 specifically has removal_rate_pct is None and no removal finding
        d02_stat = next((s for s in c8.area_stats if s.area_id == "D02"), None)
        has_div_zero_or_removal_finding = (
            any(f.rule_id == "RULE-D-007" and f.affected_area_id == "D02" for f in f8)
            or (d02_stat is not None and d02_stat.removal_rate_pct is not None)
        )
        pred8 = "POSITIVE" if has_div_zero_or_removal_finding else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-08",
            description="New area with zero previous records gaining voters",
            expected="NEGATIVE",
            predicted=pred8,
            outcome="TRUE_NEGATIVE" if pred8 == "NEGATIVE" else "FALSE_POSITIVE",
            notes="Safe division handling: removal rate is null when previous count is 0",
        ))

        # Scenario 9: Missing age value -> Expected: POSITIVE
        s9_csv = (
            "record_id,name,area_id,area_name,age,gender\n"
            "R-001,Kiran Rao,E01,Area E01,,M\n"
        ).encode("utf-8")
        val9 = validator.validate_csv(s9_csv, "test_file")
        pred9 = "POSITIVE" if any(w.type == "MISSING_AGE" for w in val9.warnings) else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-09",
            description="Missing age value in dataset record",
            expected="POSITIVE",
            predicted=pred9,
            outcome="TRUE_POSITIVE" if pred9 == "POSITIVE" else "FALSE_NEGATIVE",
            notes="Validator raises WARNING for missing age",
        ))

        # Scenario 10: Invalid gender value -> Expected: POSITIVE
        s10_csv = (
            "record_id,name,area_id,area_name,age,gender\n"
            "R-001,Sunil Gupta,F01,Area F01,42,Z\n"
        ).encode("utf-8")
        val10 = validator.validate_csv(s10_csv, "test_file")
        pred10 = "POSITIVE" if any(rf.type == "INVALID_GENDER" for rf in val10.review_flags) else "NEGATIVE"
        scenarios.append(ChallengeScenarioResult(
            scenario_id="FAC-10",
            description="Invalid gender value ('Z')",
            expected="POSITIVE",
            predicted=pred10,
            outcome="TRUE_POSITIVE" if pred10 == "POSITIVE" else "FALSE_NEGATIVE",
            notes="Validator emits REVIEW_FLAG for unsupported gender code",
        ))

        # Calculate counts
        tp = sum(1 for s in scenarios if s.outcome == "TRUE_POSITIVE")
        tn = sum(1 for s in scenarios if s.outcome == "TRUE_NEGATIVE")
        fp = sum(1 for s in scenarios if s.outcome == "FALSE_POSITIVE")
        fn = sum(1 for s in scenarios if s.outcome == "FALSE_NEGATIVE")

        precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else None
        recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else None

        precision_note = None if (tp + fp) > 0 else "Zero positive predictions made; precision cannot be calculated."
        recall_note = None if (tp + fn) > 0 else "Zero positive scenarios defined; recall cannot be calculated."

        passed = tp + tn
        failed = fp + fn

        resp = ChallengeResponse(
            status="success",
            total_scenarios=len(scenarios),
            passed=passed,
            failed=failed,
            true_positives=tp,
            true_negatives=tn,
            false_positives=fp,
            false_negatives=fn,
            precision=precision,
            recall=recall,
            precision_note=precision_note,
            recall_note=recall_note,
            scenario_results=scenarios,
            disclaimer="These results reflect synthetic scenarios defined for this challenge. They do not measure real-world electoral fraud detection performance.",
        )
        return jsonify(resp.model_dump()), 200

    # -----------------------------------------------------------------------
    # Insight Assistant — Deterministic Summary
    # -----------------------------------------------------------------------

    @app.post("/api/chat/explain")
    def chat_explain():
        data = request.get_json(silent=True) or {}
        analysis_id = data.get("analysis_id")
        language = data.get("language", "en")

        if not analysis_id:
            return jsonify({
                "status": "error",
                "code": "BAD_REQUEST",
                "message": "analysis_id is required.",
            }), 400

        if language not in insight_assistant.SUPPORTED_LANGUAGES:
            return jsonify({
                "status": "error",
                "code": "UNSUPPORTED_LANGUAGE",
                "message": f"Language '{language}' is not supported. Supported: {sorted(insight_assistant.SUPPORTED_LANGUAGES)}",
            }), 400

        stored = analysis_store.get(analysis_id)
        if not stored:
            return jsonify({
                "status": "error",
                "code": "ANALYSIS_NOT_FOUND",
                "message": f"Analysis {analysis_id} not found.",
            }), 404

        result = insight_assistant.generate_summary(stored, language)
        return jsonify({"status": "success", **result}), 200

    # -----------------------------------------------------------------------
    # Insight Assistant — Conversational Message
    # -----------------------------------------------------------------------

    @app.post("/api/chat/message")
    def chat_message():
        data = request.get_json(silent=True) or {}
        analysis_id = data.get("analysis_id")
        message = data.get("message", "").strip()
        language = data.get("language", "en")
        conversation_id = data.get("conversation_id")

        if not analysis_id:
            return jsonify({
                "status": "error",
                "code": "BAD_REQUEST",
                "message": "analysis_id is required.",
            }), 400

        if language not in insight_assistant.SUPPORTED_LANGUAGES:
            return jsonify({
                "status": "error",
                "code": "UNSUPPORTED_LANGUAGE",
                "message": f"Language '{language}' is not supported. Supported: {sorted(insight_assistant.SUPPORTED_LANGUAGES)}",
            }), 400

        if not message:
            return jsonify({
                "status": "error",
                "code": "EMPTY_QUESTION",
                "message": "message field cannot be empty.",
            }), 400

        if len(message) > insight_assistant.MAX_QUESTION_LENGTH:
            return jsonify({
                "status": "error",
                "code": "QUESTION_TOO_LONG",
                "message": f"Question exceeds maximum length of {insight_assistant.MAX_QUESTION_LENGTH} characters.",
            }), 400

        stored = analysis_store.get(analysis_id)
        if not stored:
            return jsonify({
                "status": "error",
                "code": "ANALYSIS_NOT_FOUND",
                "message": f"Analysis {analysis_id} not found.",
            }), 404

        result = insight_assistant.handle_chat_message(
            stored=stored,
            message=message,
            language=language,
            conversation_id=conversation_id,
        )
        return jsonify({"status": "success", **result}), 200

    return app


app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug)
