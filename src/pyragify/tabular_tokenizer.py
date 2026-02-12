
import logging
import csv
from pathlib import Path
from typing import List, Dict, Any, Iterable, Union

logger = logging.getLogger(__name__)

class TabularDataTokenizer:
    """
    A generalized tokenizer for tabular data sources (CSV, Excel, Database Cursors).
    Converts rows into a key-value pair format suitable for LLM reasoning.
    """

    def __init__(self, output_dir: Union[str, Path] = None):
        """
        Initialize the tokenizer.
        
        Args:
            output_dir: Optional default directory to save tokenized files.
        """
        self.output_dir = Path(output_dir) if output_dir else None

    def tokenize_row(self, headers: List[str], row_values: List[Any], row_index: int) -> str:
        """
        Core logic: Converts a single row into the LLM-friendly string format.
        
        Format:
        --- Row {row_index} ---
        Header1: Value1
        Header2: Value2
        ...
        """
        lines = [f"--- Row {row_index} ---"]
        for header, value in zip(headers, row_values):
            # Handle None/Null values gracefully
            val_str = str(value) if value is not None else ""
            lines.append(f"{header}: {val_str}")
        lines.append("") # Add a blank line for separation
        lines.append("") # Add another blank line for distinct separation between rows
        return "\n".join(lines)

    def _write_to_file(self, content_generator: Iterable[str], output_path: Path):
        """Helper to write generated content to file."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                for chunk in content_generator:
                    f.write(chunk)
            logger.info(f"Successfully tokenized data to {output_path}")
        except Exception as e:
            logger.error(f"Failed to write tokenized data to {output_path}: {e}")
            raise

    def process_csv(self, file_path: Union[str, Path], output_path: Union[str, Path] = None) -> Path:
        """
        Process a CSV file.
        """
        file_path = Path(file_path)
        if not output_path:
            if not self.output_dir:
                raise ValueError("Output path not specified and no default output_dir set.")
            output_path = self.output_dir / f"{file_path.stem}.txt"
        else:
            output_path = Path(output_path)

        def generate_content():
            try:
                with open(file_path, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.reader(f)
                    try:
                        headers = next(reader)
                    except StopIteration:
                        logger.warning(f"CSV file {file_path} is empty.")
                        return

                    for i, row in enumerate(reader, start=2): # Start at 2 to match Excel row numbering (1-based header)
                        yield self.tokenize_row(headers, row, i)
            except Exception as e:
                logger.error(f"Error processing CSV {file_path}: {e}")
                raise

        self._write_to_file(generate_content(), output_path)
        return output_path

    def process_excel(self, file_path: Union[str, Path], output_dir: Union[str, Path] = None) -> List[Path]:
        """
        Process an Excel file. Generates one text file per sheet.
        Requires `openpyxl` to be installed.
        """
        try:
            import openpyxl
        except ImportError:
            logger.error("openpyxl is required for Excel processing. Please install it.")
            raise

        file_path = Path(file_path)
        out_root = Path(output_dir) if output_dir else (self.output_dir if self.output_dir else file_path.parent)
        
        generated_files = []

        try:
            # Use data_only=True to get values, not formulas
            wb = openpyxl.load_workbook(file_path, data_only=True)
            stub = file_path.stem

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = ws.iter_rows(values_only=True)
                
                try:
                    headers = next(rows) # Get header row
                    if not headers:
                        continue # Skip empty sheets
                except StopIteration:
                     continue 

                # Convert tuple headers to list and handle None
                headers = [str(h) if h is not None else f"Col_{i}" for i, h in enumerate(headers)]

                output_path = out_root / f"{stub}_{sheet_name}.txt"
                
                def generate_sheet_content():
                    for i, row in enumerate(rows, start=2):
                        yield self.tokenize_row(headers, row, i)

                self._write_to_file(generate_sheet_content(), output_path)
                generated_files.append(output_path)
                
        except Exception as e:
            logger.error(f"Error processing Excel file {file_path}: {e}")
            raise

        return generated_files

    def process_cursor(self, cursor: Any, table_name: str = None) -> Path:
        """
        Process data from a database cursor.
        Assumes cursor.description is available for headers.
        """
        filename = table_name + '.txt'
        output_path = self.output_dir / filename
        
        if not cursor.description:
             logger.warning("Cursor has no description (headers).")
             return None

        headers = [col[0] for col in cursor.description]

        def generate_cursor_content():
            for i, row in enumerate(cursor, start=1):
                yield self.tokenize_row(headers, row, i)

        self._write_to_file(generate_cursor_content(), output_path)
        return output_path

    def process_dicts(self, data: List[Dict[str, Any]], output_path: Union[str, Path]) -> Path:
        """
        Process a list of dictionaries.
        Assumes all dicts have the same keys (headers).
        """
        if not data:
            logger.warning("No data to process.")
            return None

        output_path = Path(output_path)
        headers = list(data[0].keys())

        def generate_dict_content():
            for i, item in enumerate(data, start=1):
                row_values = [item.get(h) for h in headers]
                yield self.tokenize_row(headers, row_values, i)

        self._write_to_file(generate_dict_content(), output_path)
        return output_path
