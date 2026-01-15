import logging
import os
from pathlib import Path

from openpyxl.styles.builtins import output
from transformers import DataProcessor
from triton import Config

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
            pivot_logic = self._extract_pivot_logic(wb, file_path.name)
            for pivot_desc in pivot_logic:
                chunks.append({
                    "type": "excel_pivot",
                    "name": "Pivot Table",
                    "content": pivot_desc
                })

            # 3. Extract Advanced Logic/External Links (Ported from extract_advanced_logic [5])
            adv_logic = self._extract_advanced_logic(wb, file_path.name)
            if adv_logic:
                chunks.append({
                    "type": "excel_dependencies",
                    "name": "External Dependencies",
                    "content": adv_logic
                })

            # 4. Extract Data Connections (Merged from ExcelQueryExtractor)
            connections = self._extract_connections(file_path)
            if connections:
                chunks.append({
                    "type": "excel_connection",
                    "name": "External Connections",
                    "content": connections
                })

            # fields = self._extract_field_metadata(file_path)
            # if fields:
            #     for key, value in fields:
            #         chunks.append({"type": "excel_fields_metadata",
            #                        "name": key,
            #                        "fields": value})
            lineage = self._extract_connections(file_path)
            if lineage:
                chunks.append({"type": "excel_lineage",
                               "name": "External Lineage",
                               "content": lineage
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
        # ---------------------------------------------------------
        # LAZY IMPORTS: Only load heavy libraries if processing Excel
        # ---------------------------------------------------------
        import re
        from openpyxl.worksheet.formula import ArrayFormula
        # ---------------------------------------------------------
        # report = []
        themes = {}
        # report.append(f"\n### WORKBOOK: {filename}")
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]

            # report.append(f"\n## SHEET: {sheet_name}")
            themes[sheet_name] = {}
            seen_patterns = set()

            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type == 'f':  # Formula cell [3]
                        if isinstance(cell.value, ArrayFormula):
                            formula_text = cell.value.ref  # Extract the actual math string
                        else:
                            formula_text = str(cell.value)
                        # Replaces any whitespace character (newlines, tabs, etc.) with a single space
                        formula_text = re.sub(r'\s+', ' ', str(formula_text)).strip()

                        theme_pattern = re.sub(r'\d+', '', str(formula_text))
                        # 2. Extract Header for context
                        header = ws.cell(row=1, column=cell.column).value or f"Col {cell.column}"
                        # Replaces any whitespace character (newlines, tabs, etc.) with a single space
                        header = re.sub(r'\s+', ' ', str(header)).strip()
                        if theme_pattern not in seen_patterns:
                            themes[sheet_name][theme_pattern] = {
                                    "example_formula": formula_text,
                                    "column_context": header,
                                }
                            seen_patterns.add(theme_pattern)
        if not themes:
            return ""
        output = f"### WORKBOOK: {filename}\n" + "=" * 30 + "\n"
        # output += "### LOGIC ANALYSIS\n"
        for sheet, logic in themes.items():
            if not logic: continue
            output += f"\n## SHEET: {sheet}\n"
            for pattern, details in logic.items():
                output += (f"- [THEME] in '{details['column_context']}': "
                           f"Uses logic {details['example_formula']} (Pattern: {pattern})\n")
        return output

    def _extract_pivot_logic(self, wb, filename) -> list:
        """
        Ported from PrintFormula.extract_pivot_logic [4].
        Extracts metadata about Pivot Table sources and dimensions.
        """
        pivot_summaries = []
        # pivot_summaries.append(f"### WORKBOOK: {filename}\n")
        # pivot_summaries.append(f"### PIVOT TABLES\n")
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
                            source_name = f"[Sheet]: {cs.worksheetSource.sheet}, [RANGE]: {cs.worksheetSource.ref or 'Defined Name'}"
                        elif hasattr(cs, 'extRef') and cs.extRef:
                            source_type = "External Reference"
                            source_name = getattr(cs.extRef, 'target', 'External Link')

                    # Extract Dimensions [7]
                    fields = [f.name for f in cache.cacheFields if f.name]

                    logic_desc = (
                        f"### WORKBOOK: {filename}\n" + "=" * 30 + "\n"
                        f"### PIVOT TABLE: {pivot.name}\n"
                        f"- **Location:** Sheet '{sheet_name}'\n"
                        f"- **Data Source Type:** {source_type}\n"
                        f"- **Source Reference:** {source_name}\n"
                        f"- **Fields:** {', '.join(fields[:10])}\n"
                    )
                    pivot_summaries.append(logic_desc)
        return pivot_summaries

    def _extract_advanced_logic(self, wb, filename) -> list:
        """
        Ported from PrintFormula.extract_advanced_logic [5].
        Identifies external workbook links and LOOKUP "bridges".
        """
        # ---------------------------------------------------------
        # LAZY IMPORTS: Only load heavy libraries if processing Excel
        # ---------------------------------------------------------
        import re
        from openpyxl.worksheet.formula import ArrayFormula
        #---------------------------------------------------------
        return_string = []
        bridges = []
        lst_links = []
        # report.append("### EXTERNAL DEPENDENCIES\n")
        # 1. External Links [5]
        if hasattr(wb, 'external_links') and wb.external_links:
            # Note: external_values implementation varies by openpyxl version,
            # keeping generic check based on source logic
            # report.append("### EXTERNAL DEPENDENCIES")
            for link in wb.external_links:
                # Attempt to get target if available
                target = getattr(link, 'file_link', getattr(link, 'target', 'Unknown Link'))
                lst_links.append(f"- Links to external file: {target}")
        # 2. Lookup Logic [8]
        for sheet_name in wb.sheetnames:
            report = []
            ws = wb[sheet_name]
            seen_patterns = set()
            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type == 'f':
                        # 1. Handle ArrayFormula objects vs standard strings
                        if isinstance(cell.value, ArrayFormula):
                            formula_text = cell.value.ref  # Extract the actual math string
                        else:
                            formula_text = str(cell.value)
                        # Replaces any whitespace character (newlines, tabs, etc.) with a single space
                        formula_text = re.sub(r'\s+', ' ', str(formula_text)).strip()
                        # 2. Extract Header for context
                        header = ws.cell(row=1, column=cell.column).value or f"Col {cell.column}"
                        # Replaces any whitespace character (newlines, tabs, etc.) with a single space
                        header = re.sub(r'\s+', ' ', str(header)).strip()
                        # 3. Pattern Grouping (Logic Themes)
                        theme_pattern = re.sub(r'\d+', '', str(formula_text))
                        if "LOOKUP" in formula_text.upper() and theme_pattern not in seen_patterns:
                            report.append(f"- [BRIDGE] {header}: {formula_text}")
                            seen_patterns.add(theme_pattern)
            if report:
                bridges.append(f"## SHEET: {sheet_name}\n")
                bridges += report
                del report
        if bridges or lst_links:
            # return_string.append(f"\n### LINKS AND BRIDGES\n")
            return_string.append(f"### WORKBOOK: {filename}\n" + "=" * 30 + "\n")
            if lst_links:
                return_string.append(f"## LINKS \n")
                return_string += lst_links
            if bridges:
                return_string.append(f"## BRIDGES:")
                return_string += bridges
            return return_string
        else:
            return None

    def _extract_connections(self, file_path: Path) -> str:
        """
        Extracts database connection strings and command text.
        Merged from ExcelQueryExtractor logic.
        """
        import zipfile
        import xml.etree.ElementTree as ET

        if not zipfile.is_zipfile(file_path):
            return []

        results = []
        namespaces = {
            'main': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
            'spr': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        }
        
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # The logic is typically stored in xl/connections.xml
                conn_path = 'xl/connections.xml'
                
                if conn_path not in z.namelist():
                    return []

                with z.open(conn_path) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()

                    # Iterate through connection definitions
                    for conn in root.findall('.//spr:connection', namespaces):
                        conn_data = {
                            "sheet": conn.get('name'),
                            "type": "Unknown",
                            "connection_string": "",
                            "command_text": ""
                        }

                        # Database Properties (SQL Server, etc.)
                        db_pr = conn.find('spr:dbPr', namespaces)
                        if db_pr is not None:
                            conn_data["type"] = "Database/SQL"
                            conn_data["connection_string"] =db_pr.get('connection'),
                            conn_data["command_text"] = db_pr.get('command')

                        # OLAP Properties (DataCubes)
                        olap_pr = conn.find('spr:olapPr', namespaces)
                        if olap_pr is not None:
                            conn_data["type"] = "OLAP/DataCube"
                            # OLAP connections often point to local connection files or specific providers
                        results.append(conn_data)
        except Exception as e:
            logger.warning(f"Error extracting connections from {file_path}: {e}")
        output = f"### WORKBOOK: {file_path.name}\n" + "=" * 30 + "\n"
        for conn in results:
            output += f"## SHEET: {conn["sheet"]}\n"
            output += f"* Connection Type: {conn["type"]}\n"
            output += f"* Connection Connection String: {conn['connection_string']}\n"
            output += f"* Connection Command: {conn['command_text']}\n\n"
        return output

    # def _extract_field_metadata(self, file_path: Path) -> list:
    #     """Extracts the SQL/MDX command text and connection details."""
    #     import zipfile
    #     import xml.etree.ElementTree as ET
    #     ns = {'spr': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    #     if not zipfile.is_zipfile(file_path):
    #        return []
    #     field_data = {}
    #     with zipfile.ZipFile(file_path, 'r') as z:
    #         # 1. Find all query table files
    #         qt_files = [f for f in z.namelist() if f.startswith('xl/queryTables/queryTable')]
    #
    #         for qt_file in qt_files:
    #             with z.open(qt_file) as f:
    #                 tree = ET.parse(f)
    #                 root = tree.getroot()
    #
    #                 table_name = root.get('name')
    #                 fields = []
    #
    #                 # 2. Extract specific field info
    #                 # queryTableFields contains the column-level metadata
    #                 qt_fields = root.find('spr:queryTableFields', ns)
    #                 if qt_fields is not None:
    #                     for field in qt_fields.findall('spr:queryTableField', ns):
    #                         fields.append({
    #                             "id": field.get('id'),
    #                             "name": field.get('name'),  # The display name in Excel
    #                             "data_type": field.get('fillFormulas', 'Standard'),
    #                             "is_filtered": field.get('filterColumn', '0') == '1'
    #                         })
    #
    #                 field_data[table_name] = fields
    #
    #         return field_data

    def _get_lineage_data(self, file_path: Path) -> str:
        """Extracts and joins connections with query table field lists."""

        import zipfile
        import xml.etree.ElementTree as ET
        ns = {'spr': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        lineage = []
        with zipfile.ZipFile(file_path, 'r') as z:
            # 1. Extract Connections
            connections = {}
            if 'xl/connections.xml' in z.namelist():
                with z.open('xl/connections.xml') as f:
                    root = ET.parse(f).getroot()
                    for conn in root.findall('.//spr:connection', ns):
                        c_id = conn.get('id')
                        db_pr = conn.find('spr:dbPr', ns)
                        connections[c_id] = {
                            "ConnectionName": conn.get('name'),
                            "SQLQuery": db_pr.get('command') if db_pr is not None else "N/A"
                        }

            # 2. Extract QueryTables and Join with Connections
            qt_files = [f for f in z.namelist() if f.startswith('xl/queryTables/queryTable')]
            for qt_file in qt_files:
                with z.open(qt_file) as f:
                    root = ET.parse(f).getroot()
                    c_id = root.get('connectionId')
                    info = connections.get(c_id, {"ConnectionName": "Unknown", "SQLQuery": "N/A"})

                    fields = root.find('spr:queryTableFields', ns)
                    field_list = [field.get('name') for field in
                                  fields.findall('spr:queryTableField', ns)] if fields is not None else []

                    lineage.append({
                        "Sheet": root.get('name'),
                        "SourceConnection": info["ConnectionName"],
                        "SQLLogic:": info["SQLQuery"],
                        "Fields": ", ".join(field_list)
                    })
        if lineage:
            output = f"### WORKBOOK: {file_path.name}\n" + "=" * 30 + "\n"
            for line in lineage:
                output += f"## SHEET: {line['Sheet']}\n"
                output += f"* Connection String: {line['SourceConnection']}\n"
                output += f"* Connection Logic: {line['SQLogic']}\n"
                output += f"* Connection Fields: {line['Fields']}\n"
            return output
        else:
            return []

    def format_chunk(self, chunk: dict) -> str:
        """
        Format a chunk into plain text for saving.
        """
        type_map = {
            "excel_logic": "Excel Logic",
            "excel_pivot": "Excel Pivot",
            "excel_dependencies": "Excel Dependencies"
        }
        chunk_type = chunk.get("type")
        if chunk_type in type_map:
            header = type_map[chunk_type]
            return (f"{header}: {chunk.get('name')}\n"
                    f"Content:\n{self._ensure_text(chunk.get('content', ''))}")
        
        if chunk_type == "excel_connection":
            content = chunk.get("content", {})
            return (f"Excel Connection: {chunk.get('name')}\n"
                    f"Type: {content.get('type')}\n"
                    f"Connection String: {content.get('connection_string')}\n"
                    f"Command Text: {content.get('command_text')}\n")

        return super().format_chunk(chunk)

class ExcelDataProcessor:
    """ Tool to re-format the data from a Spreadsheet into AI parsable format. ."""

    def __init__(self, file_path) -> None:
        self.file_path = file_path
        # Generate the list of Excel files to process
        lst_excel = []
        lst_files = os.listdir(file_path)
        self.lst_excel = [filename for filename in lst_files if Path(filename).suffix == ".xlsx"]


    def sanitize_spreadsheet_for_llm(self, output_path):
        import openpyxl
        import re
        output_path = os.path.join(output_path,'excel')
        for filename in self.lst_excel:
            wb = openpyxl.load_workbook(os.path.join(self.file_path, filename))
            outfile = os.path.join(output_path, filename)

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]

                # 1. Unmerge cells and propagate values
                merged_ranges = list(ws.merged_cells.ranges)
                for merged_range in merged_ranges:
                    # Get the value from the top-left cell of the merge
                    top_left_value = ws.cell(row=merged_range.min_row, column=merged_range.min_col).value
                    ws.unmerge_cells(str(merged_range))

                    # Fill all previously merged cells with the same value
                    for row in range(merged_range.min_row, merged_range.max_row + 1):
                        for col in range(merged_range.min_col, merged_range.max_col + 1):
                            ws.cell(row=row, column=col).value = top_left_value

                # 2. Clean Headers and Cell Content
                for row in ws.iter_rows():
                    for cell in row:
                        if isinstance(cell.value, str):
                            # Remove line breaks, tabs, and Excel-specific artifacts
                            cleaned = re.sub(r'[\r\n\t]+', ' ', cell.value)
                            cleaned = cleaned.replace('_x000D_', '')
                            cell.value = cleaned.strip()
            wb.save(outfile)
            self.save_for_llm_reasoning(outfile, output_path)
            logger.info(f"Cleaned Spreadsheet {filename} has been saved to {output_path}")
        return None

    def save_for_llm_reasoning(self, excel_file, output_path):
        import openpyxl

        stub = Path(excel_file).stem
        wb = openpyxl.load_workbook(excel_file, data_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            headers = [cell.value for cell in ws[1]]  # Assumes row 1 is headers
            output_txt = Path(output_path).joinpath(stub+'_'+sheet_name+'.txt')
            with open(output_txt, 'w', encoding='utf-8') as f:
                for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                    f.write(f"--- Row {row_idx} ---\n")
                    for header, value in zip(headers, row):
                        f.write(f"{header}: {value}\n")
                    f.write("\n")

