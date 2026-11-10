"""OpenAPI documentation of contract bodies.

Internal endpoints decode bodies strictly themselves (NaN rejection, float
rejection, schema-major checks), so request/response schemas are attached via
``openapi_extra`` and merged into ``components.schemas`` from the Pydantic
contracts (source of truth: ``research_engine/contracts``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

REF = "#/components/schemas/{model}"


def _models() -> dict[str, Any]:
    from research_engine.contracts.decisions import DecisionRequest, StrategyResult
    from research_engine.contracts.evidence import EvidenceBundle, RetrievalRun
    from research_engine.contracts.calculations import RiskReport
    from research_engine.contracts.portfolio import TransitionProposal, TransitionRequest

    from . import schemas

    return {
        "TransitionRequest": TransitionRequest,
        "TransitionProposal": TransitionProposal,
        "DecisionRequest": DecisionRequest,
        "StrategyResult": StrategyResult,
        "RiskReport": RiskReport,
        "EvidenceBundle": EvidenceBundle,
        "RetrievalRun": RetrievalRun,
        "PriceRequest": schemas.PriceRequest,
        "RiskRequest": schemas.RiskRequest,
        "EvidenceRetrieveRequest": schemas.EvidenceRetrieveRequest,
        "ResearchNoteRequest": schemas.ResearchNoteRequest,
        "IngestionRequest": schemas.IngestionRequest,
        "IndexBuildRequest": schemas.IndexBuildRequest,
        "BootstrapAllocationRequest": schemas.BootstrapAllocationRequest,
        "PerformanceRequest": schemas.PerformanceRequest,
        "PaymentCalendarRequest": schemas.PaymentCalendarRequest,
    }


def contract_body(name: str, description: str = "") -> dict[str, Any]:
    return {
        "requestBody": {
            "required": True,
            "description": description or f"{name} (camelCase JSON, decimal strings)",
            "content": {"application/json": {"schema": {"$ref": REF.format(model=name)}}},
        }
    }


def contract_response(name: str, description: str = "") -> dict[int | str, Any]:
    return {
        200: {
            "description": description or f"{name} (camelCase JSON)",
            "content": {"application/json": {"schema": {"$ref": REF.format(model=name)}}},
        }
    }


PROBLEM_SCHEMA = {
    "type": "object",
    "description": "RFC 9457 problem details",
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "code": {"type": "string"},
        "detail": {"type": "string"},
        "instance": {"type": "string"},
        "errors": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["type", "title", "status", "code", "detail"],
}


def component_schemas() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, model in _models().items():
        schema = model.model_json_schema(by_alias=True, ref_template=REF)
        for def_name, definition in schema.pop("$defs", {}).items():
            out.setdefault(def_name, definition)
        out[name] = schema
    out["Problem"] = PROBLEM_SCHEMA
    return out


def internal_openapi(app: FastAPI) -> dict[str, Any]:
    """OpenAPI document restricted to ``/internal/v1`` routes."""
    from . import ROUTERS

    doc = get_openapi(
        title="Research engine internal API",
        version="1.0.0",
        description=(
            "Python research-engine internal API (spec 14.3). Every path requires the "
            "X-API-Key header. Errors are application/problem+json. TransitionProposal and "
            "StrategyResult bodies carry sha256 hashes over canonical JSON and an HMAC-SHA256 "
            "signature with the shared ML_SERVICE_SIGNING_KEY."
        ),
        routes=[route for router in ROUTERS for route in router.routes],
    )
    components = doc.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    for name, schema in component_schemas().items():
        schemas[name] = schema
    components["securitySchemes"] = {
        "ApiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
    }
    doc["security"] = [{"ApiKey": []}]
    for path_item in doc.get("paths", {}).values():
        for operation in path_item.values():
            responses = operation.setdefault("responses", {})
            responses.pop("422", None)
            for status, text in (
                ("400", "Malformed request"),
                ("401", "Missing or invalid X-API-Key"),
                ("404", "Unknown resource"),
                ("409", "Hash/snapshot mismatch, stale state or idempotency conflict"),
                ("422", "Invalid request, unsupported schema version or units"),
                ("429", "Concurrency limit reached (Retry-After)"),
                ("503", "Dependency or capability unavailable"),
            ):
                responses.setdefault(
                    status,
                    {
                        "description": text,
                        "content": {
                            "application/problem+json": {
                                "schema": {"$ref": REF.format(model="Problem")}
                            }
                        },
                    },
                )
    _prune(doc)
    return doc


def _refs(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            out.add(ref.rsplit("/", 1)[1])
        for value in node.values():
            _refs(value, out)
    elif isinstance(node, list):
        for value in node:
            _refs(value, out)


def _prune(doc: dict[str, Any]) -> None:
    """Drop component schemas not reachable from the internal paths."""
    schemas = doc.get("components", {}).get("schemas", {})
    reachable: set[str] = set()
    frontier: set[str] = set()
    _refs(doc.get("paths", {}), frontier)
    while frontier:
        name = frontier.pop()
        if name in reachable or name not in schemas:
            continue
        reachable.add(name)
        found: set[str] = set()
        _refs(schemas[name], found)
        frontier |= found - reachable
    for name in list(schemas):
        if name not in reachable:
            schemas.pop(name)


def _rename_refs(node: Any, prefix: str) -> Any:
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(REF[:-7]):
                out[key] = REF.format(model=prefix + value.rsplit("/", 1)[1])
            else:
                out[key] = _rename_refs(value, prefix)
        return out
    if isinstance(node, list):
        return [_rename_refs(v, prefix) for v in node]
    return node


def install(app: FastAPI) -> None:
    """Development /openapi.json: internal paths use ``research.*`` component names so
    contract schemas never collide with the legacy /predict models."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        doc = original()
        internal = internal_openapi(app)
        prefix = "research."
        paths = {p: v for p, v in doc.get("paths", {}).items() if not p.startswith("/internal/")}
        paths.update(_rename_refs(internal["paths"], prefix))
        doc["paths"] = paths
        schemas = doc.setdefault("components", {}).setdefault("schemas", {})
        for name, schema in internal["components"]["schemas"].items():
            schemas[prefix + name] = _rename_refs(schema, prefix)
        doc["components"].setdefault("securitySchemes", {}).update(
            internal["components"]["securitySchemes"]
        )
        app.openapi_schema = doc
        return doc

    app.openapi = openapi  # type: ignore[method-assign]


def export(path: Path) -> dict[str, Any]:
    from app.main import app

    doc = internal_openapi(app)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return doc


DEFAULT_EXPORT = (
    Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "research-engine.v1.json"
)


if __name__ == "__main__":  # python -m app.v1.openapi_models [path]
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXPORT
    document = export(target)
    print(f"wrote {target} ({len(document.get('paths', {}))} paths)")
