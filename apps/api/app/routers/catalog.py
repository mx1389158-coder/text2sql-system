from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_orchestrator
from ..services.orchestrator import Text2SQLOrchestrator
from .query import verify_api_key


router = APIRouter(tags=["catalog"])


@router.get("/schema")
async def get_schema(
    scope: str = Depends(verify_api_key),
    orchestrator: Text2SQLOrchestrator = Depends(get_orchestrator),
):
    payload = orchestrator.catalog.to_dict()
    policy = orchestrator.access_policy.resolve(scope)
    if orchestrator.catalog.schema.lower() not in policy.schemas:
        payload["tables"] = []
        return payload

    tables = []
    allowed_tables = set(policy.tables)
    allowed_columns_by_table = {
        str(table["name"]).lower(): policy.allowed_columns(
            str(table["name"]).lower(),
            {str(column["name"]).lower() for column in table["columns"]},
        )
        for table in payload["tables"]
        if str(table["name"]).lower() in allowed_tables
    }
    for table in payload["tables"]:
        table_name = str(table["name"]).lower()
        if table_name not in allowed_tables:
            continue
        allowed_columns = allowed_columns_by_table[table_name]
        table["columns"] = [
            {
                **column,
                "examples": (
                    column.get("examples", [])
                    if policy.allows_sample_value(table_name, str(column["name"]))
                    else []
                ),
            }
            for column in table["columns"]
            if str(column["name"]).lower() in allowed_columns
        ]
        table["foreign_keys"] = [
            foreign_key
            for foreign_key in table.get("foreign_keys", [])
            if str(foreign_key["column"]).lower() in allowed_columns
            and str(foreign_key["referred_table"]).lower() in allowed_tables
            and str(foreign_key["referred_column"]).lower()
            in allowed_columns_by_table.get(
                str(foreign_key["referred_table"]).lower(), set()
            )
        ]
        tables.append(table)
    payload["tables"] = tables
    return payload

