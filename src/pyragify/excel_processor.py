import logging
from pathlib import Path
from processor import FileProcessor

logger = logging.getLogger(__name__)

class ExcelProcessor(FileProcessor):
    """
    Processor for Excel files (.xlsx, .xlsm).
    Extracts semantic logic, pivot table metadata, and external dependencies.
    """

    def chunk_file(self, file_path: Path) -> tuple[list, int]:
        """
        Chunk an Excel file into semantic sections.
        Overrides FileProcessor.chunk_file to handle .xlsx files with lazy imports.
        """
        if file_path.suffix not in ['.xlsx', '.xlsm']:
            return super().chunk_file(file_path)

        # ---------------------------------------------------------
        # LAZY IMPORTS: Only load heavy libraries if processing Excel
        # ---------------------------------------------------------
        try:
            import openpyxl
            import pandas as pd
        except ImportError as e:
            logger.error(f"Excel processing requires 'openpyxl' and 'pandas'. Please install them. Error: {e}")
            return [], 0

        chunks = []
        try:
            # Load workbook using logic from PrintFormula.__init__ [1]
            # data_only=False ensures we get formulas, not values
            wb = openpyxl.load_workbook(str(file_path), data_only=False, keep_links=True)

            # 1. Extract Formula Logic Themes (Ported from extract_logic_themes [3])
            logic_themes = self._extract_logic_themes(wb, file_path.name)
            if logic_themes:
                chunks.append({
                    "type": "excel_logic",
                    "name": "Formula Patterns",
                    "content": logic_themes
                })

            # 2. Extract Pivot Table Metadata (Ported from extract_pivot_logic [4])
            pivot_logic = self._extract_pivot_logic(wb)
            for pivot_desc in pivot_logic:
                chunks.append({
                    "type": "excel_pivot",
                    "name": "Pivot Table",
                    "content": pivot_desc
                })

            # 3. Extract Advanced Logic/External Links (Ported from extract_advanced_logic [5])
            adv_logic = self._extract_advanced_logic(wb)
            if adv_logic:
                chunks.append({
                    "type": "excel_dependencies",
                    "name": "External Dependencies",
                    "content": adv_logic
                })

            # Estimate 'lines' as number of populated rows across sheets
            line_count = sum(sheet.max_row for sheet in wb.worksheets)

            return chunks, line_count

        except Exception as e:
            logger.warning(f"Error chunking Excel file {file_path}: {e}")
            return [], 0

    def _extract_logic_themes(self, wb, filename: str) -> str:
        """
        Ported from PrintFormula.extract_logic_themes [3].
        Normalizes formulas (e.g., =A2*B2 -> =COL_A*COL_B) to identify business logic patterns.
        """
        import re  # Standard lib, safe to import top-level, but kept here for encapsulation

        themes = {}
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            themes[sheet_name] = {}

            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type == 'f':  # Formula cell [3]
                        # Normalize formula: Remove row numbers to find the "Theme"
                        theme_pattern = re.sub(r'\d+', '', str(cell.value))

                        if theme_pattern not in themes[sheet_name]:
                            # Get column header context [6]
                            header = ws.cell(row=1, column=cell.column).value or f"Col {cell.column}"
                            themes[sheet_name][theme_pattern] = {
                                "example_formula": cell.value,
                                "column_context": header,
                            }

        # Format for LLM consumption [6]
        if not themes:
            return ""

        output = f"Logic Analysis for {filename}\n" + "=" * 30 + "\n"
        for sheet, logic in themes.items():
            if not logic: continue
            output += f"\nSheet: {sheet}\n"
            for pattern, details in logic.items():
                output += (f"- Theme in '{details['column_context']}': "
                           f"Uses logic {details['example_formula']} (Pattern: {pattern})\n")
        return output

    def _extract_pivot_logic(self, wb) -> list:
        """
        Ported from PrintFormula.extract_pivot_logic [4].
        Extracts metadata about Pivot Table sources and dimensions.
        """
        pivot_summaries = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # Access internal _pivots attribute [4]
            if hasattr(ws, '_pivots'):
                for pivot in ws._pivots:
                    cache = pivot.cache
                    source_type = "Internal Range"
                    source_name = "Unknown"

                    # Identify Source Type [4]
                    if cache.cacheSource:
                        cs = cache.cacheSource
                        if cs.worksheetSource:
                            source_type = "Worksheet Range"
                            source_name = cs.worksheetSource.ref or "Defined Name"
                        elif hasattr(cs, 'extRef') and cs.extRef:
                            source_type = "External Reference"
                            source_name = getattr(cs.extRef, 'target', 'External Link')

                    # Extract Dimensions [7]
                    fields = [f.name for f in cache.cacheFields if f.name]

                    logic_desc = (
                        f"### PIVOT TABLE: {pivot.name}\n"
                        f"- **Location:** Sheet '{sheet_name}'\n"
                        f"- **Data Source Type:** {source_type}\n"
                        f"- **Source Reference:** {source_name}\n"
                        f"- **Fields:** {', '.join(fields[:10])}\n"
                    )
                    pivot_summaries.append(logic_desc)
        return pivot_summaries

    def _extract_advanced_logic(self, wb) -> str:
        """
        Ported from PrintFormula.extract_advanced_logic [5].
        Identifies external workbook links and LOOKUP "bridges".
        """
        import re
        report = []

        # 1. External Links [5]
        if hasattr(wb, 'external_links') and wb.external_links:
            # Note: external_values implementation varies by openpyxl version,
            # keeping generic check based on source logic
            report.append("### EXTERNAL DEPENDENCIES")
            for link in wb.external_links:
                # Attempt to get target if available
                target = getattr(link, 'file_link', getattr(link, 'target', 'Unknown Link'))
                report.append(f"- Links to external file: {target}")

        # 2. Lookup Logic [8]
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            seen_patterns = set()

            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type == 'f':
                        formula = str(cell.value)

                        if "LOOKUP" in formula.upper():
                            header = ws.cell(row=1, column=cell.column).value or f"Col {cell.column}"
                            # Deduplicate specific lookup patterns
                            if formula not in seen_patterns:
                                report.append(f"- [BRIDGE] Sheet '{sheet_name}' Col '{header}' fetches data: {formula}")
                                seen_patterns.add(formula)

        return "\n".join(report)

    def format_chunk(self, chunk: dict) -> str:
        """
        Format a chunk into plain text for saving.
        """
        if chunk.get("type") in ["excel_logic", "excel_pivot", "excel_dependencies"]:
            return (f"Excel Analysis: {chunk.get('name')}\n"
                    f"Content:\n{self._ensure_text(chunk.get('content', ''))}")
        return super().format_chunk(chunk)
