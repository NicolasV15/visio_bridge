"""Shared PDF export models and helpers for the Visio desktop backend."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping


PDF_INTENTS = {"print", "screen"}
PDF_PAGE_RANGES = {"all", "from_to", "current_page", "selection", "current_view"}
PDF_EXPORT_SOURCES = {"saved_file", "open_document"}


def _normalize_choice(value: Any, *, field_name: str, allowed: set[str]) -> str:
    text = str(value).strip().lower()
    if text not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"Unsupported {field_name}: {value!r}. Expected one of: {allowed_text}.")
    return text


def normalize_pdf_source(source: Any) -> str:
    return _normalize_choice(source, field_name="PDF export source", allowed=PDF_EXPORT_SOURCES)


@dataclass
class VisioPdfExportOptions:
    """User-facing PDF export options for the Visio desktop backend."""

    intent: str = "print"
    page_range: str = "all"
    from_page: int = 1
    to_page: int = -1
    color_as_black: bool = False
    include_background: bool = True
    include_document_properties: bool = True
    include_structure_tags: bool = True
    pdfa: bool = False
    page: str | int | None = None
    selection_shape_paths: list[str] | None = None

    @classmethod
    def from_value(
        cls,
        value: "VisioPdfExportOptions | Mapping[str, Any] | None",
    ) -> "VisioPdfExportOptions":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(**dict(value))
        raise TypeError(
            "pdf_options must be None, a VisioPdfExportOptions instance, "
            f"or a mapping, got {type(value).__name__}."
        )

    def to_payload(self, *, source: str) -> dict[str, Any]:
        normalized_source = normalize_pdf_source(source)
        normalized_intent = _normalize_choice(
            self.intent,
            field_name="PDF intent",
            allowed=PDF_INTENTS,
        )
        normalized_range = _normalize_choice(
            self.page_range,
            field_name="PDF page_range",
            allowed=PDF_PAGE_RANGES,
        )

        try:
            from_page = int(self.from_page)
            to_page = int(self.to_page)
        except Exception as exc:
            raise ValueError("from_page and to_page must be integers.") from exc

        if from_page < 1:
            raise ValueError("from_page must be >= 1.")
        if to_page != -1 and to_page < from_page:
            raise ValueError("to_page must be -1 or >= from_page.")

        page = self.page
        if page is not None and not isinstance(page, (str, int)):
            page = str(page)

        selection_shape_paths = None
        if self.selection_shape_paths is not None:
            selection_shape_paths = [str(path) for path in self.selection_shape_paths if str(path).strip()]

        if normalized_source == "saved_file":
            if normalized_range == "current_view":
                raise ValueError("page_range='current_view' is only supported with source='open_document'.")
            if normalized_range == "current_page" and page in (None, ""):
                raise ValueError("page is required when page_range='current_page' and source='saved_file'.")
            if normalized_range == "selection" and not selection_shape_paths:
                raise ValueError(
                    "selection_shape_paths is required when page_range='selection' "
                    "and source='saved_file'."
                )

        return {
            "intent": normalized_intent,
            "page_range": normalized_range,
            "from_page": from_page,
            "to_page": to_page,
            "color_as_black": bool(self.color_as_black),
            "include_background": bool(self.include_background),
            "include_document_properties": bool(self.include_document_properties),
            "include_structure_tags": bool(self.include_structure_tags),
            "pdfa": bool(self.pdfa),
            "page": None if page is None else str(page),
            "selection_shape_paths": selection_shape_paths,
        }


@dataclass
class VisioPdfExportResult:
    """Result returned by a PDF export request."""

    action: str
    status: str
    output_pdf_path: str
    source: str
    message: str = ""
    document_name: str = ""
    document_full_name: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VisioPdfExportResult":
        document = data.get("document")
        document_name = ""
        document_full_name = ""
        if isinstance(document, Mapping):
            document_name = str(document.get("name", ""))
            document_full_name = str(document.get("full_name", ""))
        return cls(
            action=str(data.get("action", "")),
            status=str(data.get("export_status", data.get("status", ""))),
            output_pdf_path=str(data.get("output_pdf_path", "")),
            source=str(data.get("source", "")),
            message=str(data.get("message", "")),
            document_name=document_name,
            document_full_name=document_full_name,
        )


def export_visio_pdf(
    file_path: str | os.PathLike[str],
    output_pdf_path: str | os.PathLike[str],
    *,
    options: VisioPdfExportOptions | Mapping[str, Any] | None = None,
    source: str = "saved_file",
    session: Any = None,
    mode: str | None = None,
    vm_name: str | None = None,
    timeout: int | None = None,
    visible: bool | None = None,
    activate: bool = True,
    keep_artifacts: bool = False,
) -> VisioPdfExportResult:
    """Export a Visio document to PDF through the desktop backend."""

    from ..skill.backend import require_configured_backend

    require_configured_backend("desktop")
    normalized_source = normalize_pdf_source(source)

    if normalized_source == "saved_file":
        from .session import export_pdf_desktop

        return export_pdf_desktop(
            file_path,
            output_pdf_path,
            options=options,
            session=session,
            mode=mode,
            vm_name=vm_name,
            timeout=timeout,
            visible=visible,
        )

    from .session_control import export_open_document_pdf

    return export_open_document_pdf(
        file_path,
        output_pdf_path,
        options=options,
        visible=True if visible is None else visible,
        activate=activate,
        session=session,
        mode=mode,
        vm_name=vm_name,
        timeout=timeout,
        keep_artifacts=keep_artifacts,
    )
