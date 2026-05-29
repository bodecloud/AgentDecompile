"""Data Types Tool Provider - manage-data-types.

Single tool, mode = archives (list type libraries), list (types in category),
by_string (parse C-style type string), info (resolve catalog type metadata),
create (add typedef to catalog), delete (remove from catalog),
apply (set type at address). Used to improve decompilation when variables
are undefined or show as raw numbers.
"""

from __future__ import annotations

import logging
import uuid

from typing import Any, cast

from mcp import types

from agentdecompile_cli.mcp_server.providers._collectors import collect_data_type_archives
from agentdecompile_cli.mcp_server.tool_providers import (
    FORCE_APPLY_CONFLICT_ID_KEY,
    ToolProvider,
    create_conflict_response,
    create_success_response,
    n,
)
from agentdecompile_cli.registry import Tool

logger = logging.getLogger(__name__)


def find_catalog_data_type(dtm: Any, name: str, category_path: str | None = None) -> Any | None:
    """Find a program-catalog data type by name, optionally scoped to a category."""
    from ghidra.program.model.data import CategoryPath  # pyright: ignore[reportMissingModuleSource]

    if category_path:
        cat = dtm.getCategory(CategoryPath(category_path))
        if cat is not None:
            for dt in cat.getDataTypes():
                if str(dt.getName()) == name:
                    return dt
        return None

    for dt in dtm.getAllDataTypes():
        if str(dt.getName()) == name:
            return dt
    return None


def data_type_summary(dt: Any) -> dict[str, Any]:
    return {
        "name": dt.getName(),
        "path": str(dt.getCategoryPath()),
        "length": dt.getLength(),
        "description": dt.getDescription() or "",
        "displayName": dt.getDisplayName(),
    }


class DataTypeToolProvider(ToolProvider):
    HANDLERS = {"managedatatypes": "_handle"}

    def list_tools(self) -> list[types.Tool]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider.list_tools")
        return [
            types.Tool(
                name=Tool.MANAGE_DATA_TYPES.value,
                description="List, parse, or apply standard C data types (like 'int', 'char*', 'FILE*', or struct names) to raw memory addresses. This enables the decompiler to see what variables mean. Use this when variables show up as 'undefined' or a raw number, but you know they are holding a specific structure or pointer type.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "programPath": {"type": "string", "description": "The path to the program containing the data types."},
                        "mode": {
                            "type": "string",
                            "description": "Action to perform on the data type catalog or listing.",
                            "enum": ["archives", "list", "by_string", "info", "create", "delete", "apply"],
                            "default": "list",
                        },
                        "name": {"type": "string", "description": "Catalog type name for info/delete, or typedef alias for create."},
                        "categoryPath": {"type": "string", "description": "Ghidra category folder (e.g. '/MyTypes'). Defaults to '/' for create."},
                        "dataTypeString": {"type": "string", "description": "The C-style text definition of the type you want to apply or parse (e.g., 'unsigned int', 'char *')."},
                        "addressOrSymbol": {"type": "string", "description": "If mode is 'apply', the address or symbol name where you want to stick this data type label."},
                        "limit": {"type": "integer", "default": 100, "description": "Number of data type results to return. Typical values are 100–500."},
                        "offset": {"type": "integer", "default": 0, "description": "Pagination offset tracker."},
                    },
                    "required": [],
                },
            ),
        ]

    async def _handle(self, args: dict[str, Any]) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider._handle")
        self._require_program()
        action = self._get_str(args, "mode", "action", "operation", default="list")
        # Pattern 1 dispatch: get handler by action, then call with args
        dispatch = {
            "archives": self._archives,
            "list": self._list,
            "bystring": self._by_string,
            "info": self._info,
            "create": self._create,
            "delete": self._delete,
            "apply": self._apply,
        }
        handler = self._dispatch_handler(dispatch, action, "action")
        return await handler(args)

    async def _archives(self, args: dict[str, Any]) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider._archives")
        assert self.program_info is not None  # for type checker
        program = self.program_info.program
        archives = collect_data_type_archives(program)

        return create_success_response({"action": "archives", "archives": archives, "count": len(archives)})

    async def _list(self, args: dict[str, Any]) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider._list")
        assert self.program_info is not None  # for type checker
        program = self.program_info.program
        dtm = program.getDataTypeManager()
        cat_path = self._get_str(args, "categorypath", "category", "path")
        offset, max_results = self._get_pagination_params(args, default_limit=100)

        results = []
        if cat_path:
            from ghidra.program.model.data import CategoryPath  # pyright: ignore[reportMissingModuleSource]

            cat = dtm.getCategory(CategoryPath(cat_path))
            if cat is None:
                raise ValueError(f"Category not found: {cat_path}")
            dts = cat.getDataTypes()
            for i, dt in enumerate(dts):
                if i < offset:
                    continue
                if len(results) >= max_results:
                    break
                results.append(
                    {
                        "name": dt.getName(),
                        "path": str(dt.getCategoryPath()),
                        "length": dt.getLength(),
                        "description": dt.getDescription() or "",
                    },
                )
        else:
            # List root categories
            root = dtm.getRootCategory()
            subcats = root.getCategories()
            for i, sc in enumerate(subcats):
                if i < offset:
                    continue
                if len(results) >= max_results:
                    break
                results.append(
                    {
                        "name": sc.getName(),
                        "path": str(sc.getCategoryPath()),
                        "isCategory": True,
                    },
                )
            # Also list root-level types
            for dt in root.getDataTypes():
                if len(results) >= max_results:
                    break
                results.append(
                    {
                        "name": dt.getName(),
                        "path": "/",
                        "length": dt.getLength(),
                    },
                )

        return create_success_response(
            {
                "action": "list",
                "category": cat_path or "/",
                "results": results,
                "count": len(results),
            },
        )

    async def _by_string(self, args: dict[str, Any]) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider._by_string")
        dt_str = self._require_str(args, "datatypestring", "datatype", "typestring", "type", name="dataTypeString")
        assert self.program_info is not None  # for type checker
        program = self.program_info.program
        dtm = program.getDataTypeManager()

        try:
            from ghidra.util.data import DataTypeParser  # pyright: ignore[reportMissingModuleSource]

            parser = DataTypeParser(dtm, dtm, cast("Any", None), DataTypeParser.AllowedDataTypes.ALL)
            dt = parser.parse(dt_str)
            return create_success_response(
                {
                    "action": "by_string",
                    "input": dt_str,
                    "resolved": {
                        "name": dt.getName(),
                        "path": str(dt.getCategoryPath()),
                        "length": dt.getLength(),
                        "description": dt.getDescription() or "",
                        "displayName": dt.getDisplayName(),
                    },
                },
            )
        except Exception as e:
            raise ValueError(f"Could not parse data type '{dt_str}': {e}")

    async def _info(self, args: dict[str, Any]) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider._info")
        assert self.program_info is not None
        program = self.program_info.program
        dtm = program.getDataTypeManager()
        name = self._get_str(args, "name", "typename")
        cat_path = self._get_str(args, "categorypath", "category", "path")
        if not name:
            dt_str = self._require_str(args, "datatypestring", "datatype", "typestring", "type", name="dataTypeString")
            from ghidra.util.data import DataTypeParser  # pyright: ignore[reportMissingModuleSource]

            parser = DataTypeParser(dtm, dtm, cast("Any", None), DataTypeParser.AllowedDataTypes.ALL)
            dt = parser.parse(dt_str)
            return create_success_response({"action": "info", "resolved": data_type_summary(dt)})

        dt = find_catalog_data_type(dtm, name, cat_path)
        if dt is None:
            raise ValueError(f"Data type not found: {name}")
        return create_success_response({"action": "info", "resolved": data_type_summary(dt)})

    async def _create(self, args: dict[str, Any]) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider._create")
        dt_str = self._require_str(args, "datatypestring", "datatype", "typestring", "type", name="dataTypeString")
        alias_name = self._require_str(args, "name", "typename", name="name")
        cat_path = self._get_str(args, "categorypath", "category", default="/") or "/"
        description = self._get_str(args, "description", "comment", default="")
        assert self.program_info is not None
        program = self.program_info.program
        dtm = program.getDataTypeManager()

        if not args.get(FORCE_APPLY_CONFLICT_ID_KEY):
            existing = find_catalog_data_type(dtm, alias_name, cat_path)
            if existing is not None:
                from agentdecompile_cli.mcp_server.conflict_store import store as conflict_store_store
                from agentdecompile_cli.mcp_server.session_context import get_current_mcp_session_id

                conflict_id = str(uuid.uuid4())
                conflict_summary = (
                    f"Create data type would overwrite existing catalog entry:\n\n"
                    f"Type **{alias_name}** already exists at `{existing.getCategoryPath()}`."
                )
                next_step = (
                    f'To apply this change, call `resolve-modification-conflict` with `conflictId` = "{conflict_id}" '
                    'and `resolution` = "overwrite". To discard, use `resolution` = "skip".'
                )
                program_path = args.get(n("programPath")) or getattr(self.program_info, "path", None) or getattr(
                    self.program_info,
                    "file_path",
                    None,
                )
                store_args = dict(args)
                store_args["mode"] = "create"
                conflict_store_store(
                    get_current_mcp_session_id(),
                    conflict_id,
                    tool=Tool.MANAGE_DATA_TYPES.value,
                    arguments=store_args,
                    program_path=str(program_path) if program_path else None,
                    summary=conflict_summary,
                )
                return create_conflict_response(conflict_id, Tool.MANAGE_DATA_TYPES.value, conflict_summary, next_step)

        from ghidra.program.model.data import CategoryPath, TypedefDataType  # pyright: ignore[reportMissingModuleSource]
        from ghidra.util.data import DataTypeParser  # pyright: ignore[reportMissingModuleSource]

        parser = DataTypeParser(dtm, dtm, cast("Any", None), DataTypeParser.AllowedDataTypes.ALL)
        base_dt = parser.parse(dt_str)
        force_apply = bool(args.get(FORCE_APPLY_CONFLICT_ID_KEY))
        existing = find_catalog_data_type(dtm, alias_name, cat_path) if force_apply else None

        def _create_datatype() -> None:
            if existing is not None:
                dtm.remove(existing, None)
            typedef_dt = TypedefDataType(CategoryPath(cat_path), alias_name, base_dt, dtm)
            if description:
                typedef_dt.setDescription(description)
            dtm.addDataType(typedef_dt, None)

        self._run_program_transaction(program, "create-data-type", _create_datatype)
        return create_success_response(
            {
                "action": "create",
                "name": alias_name,
                "dataTypeString": dt_str,
                "categoryPath": cat_path,
                "success": True,
            },
        )

    async def _delete(self, args: dict[str, Any]) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider._delete")
        name = self._require_str(args, "name", "typename", name="name")
        cat_path = self._get_str(args, "categorypath", "category", "path")
        assert self.program_info is not None
        program = self.program_info.program
        dtm = program.getDataTypeManager()

        dt = find_catalog_data_type(dtm, name, cat_path)
        if dt is None:
            raise ValueError(f"Data type not found: {name}")

        def _delete_datatype() -> None:
            dtm.remove(dt, None)

        self._run_program_transaction(program, "delete-data-type", _delete_datatype)
        return create_success_response({"action": "delete", "name": name, "success": True})

    async def _apply(self, args: dict[str, Any]) -> list[types.TextContent]:
        logger.debug("diag.enter %s", "mcp_server/providers/datatypes.py:DataTypeToolProvider._apply")
        addr_str = self._require_str(args, "addressorsymbol", "address", "addr", name="addressOrSymbol")
        dt_str = self._require_str(args, "datatypestring", "datatype", "type", name="dataTypeString")
        assert self.program_info is not None  # for type checker
        program = self.program_info.program
        dtm = program.getDataTypeManager()

        # Batch support
        addr_list = self._get_list(args, "addressorsymbol", "addresses")
        if addr_list and len(addr_list) > 1:
            # Batch mode
            from ghidra.util.data import DataTypeParser  # pyright: ignore[reportMissingModuleSource]

            parser = DataTypeParser(dtm, dtm, cast("Any", None), DataTypeParser.AllowedDataTypes.ALL)
            dt = parser.parse(dt_str)
            results = []

            def _batch_apply_datatype() -> None:
                listing = self._get_listing(program)
                for a in addr_list:
                    try:
                        addr = self._resolve_address(str(a), program=program)
                        listing.clearCodeUnits(addr, addr.add(dt.getLength() - 1), False)
                        listing.createData(addr, dt)
                        results.append({"address": str(addr), "success": True})
                    except Exception as e:
                        results.append({"address": str(a), "success": False, "error": str(e)})

            self._run_program_transaction(program, "batch-apply-datatype", _batch_apply_datatype)
            return create_success_response({"action": "apply", "batch": True, "results": results, "count": len(results)})

        # Single
        from ghidra.util.data import DataTypeParser  # pyright: ignore[reportMissingModuleSource]

        parser = DataTypeParser(dtm, dtm, cast("Any", None), DataTypeParser.AllowedDataTypes.ALL)
        dt = parser.parse(dt_str)
        addr = self._resolve_address(addr_str, program=program)

        def _apply_datatype() -> None:
            listing = self._get_listing(program)
            listing.clearCodeUnits(addr, addr.add(dt.getLength() - 1), False)
            listing.createData(addr, dt)

        self._run_program_transaction(program, "apply-datatype", _apply_datatype)
        return create_success_response(
            {
                "action": "apply",
                "address": str(addr),
                "dataType": dt_str,
                "success": True,
            },
        )
