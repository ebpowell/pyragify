import logging
from pathlib import Path
import re
import textwrap
from processor import FileProcessor

logger = logging.getLogger(__name__)

class PBIProcessor(FileProcessor):
    """
    Processor for PowerBI files, specifically TMDL files.
    """

    def chunk_file(self, file_path: Path) -> tuple[list, int]:
        """
        Chunk a file into semantic sections based on its type.
        
        Overrides FileProcessor.chunk_file to handle .tmdl files.
        """
        if file_path.suffix == ".tmdl":
            return self.chunk_tmdl_file(file_path)
        return super().chunk_file(file_path)

    def chunk_tmdl_file(self, file_path: Path) -> tuple[list, int]:
        """
        Chunk a TMDL file into semantic sections (tables, columns, measures, etc.).
        Produces a single Markdown chunk per file.
        """
        project_name = self.repo_path.name
        for part in file_path.parts:
            if part.endswith(".Dataset") or part.endswith(".SemanticModel") or part.endswith(".pbip") or part.endswith(".Report"):
                project_name = part.replace(".Dataset", "").replace(".SemanticModel", "").replace(".pbip", "").replace(".Report", "")
                break
                
        if file_path.name == "model.tmdl":
            return self.chunk_model_tmdl(file_path, project_name)
        elif file_path.name == "relationships.tmdl":
            return self.vectorize_relationships(file_path, project_name)
        # Skip the LocalDateTables
        elif "LocalDateTable" in file_path.name:
            return None

        # For standard table TMDL files
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
            line_count = content.count('\n') + 1

            # Determine Table Name
            name = "Unknown"
            # pattern = r"^table\s+['\"]?(.+?)['\"]?\n\n\t"
            pattern = r"^table\s+(['\"]?)(.*?)\1(?=\s*\n\n\t)"
            match = re.search(pattern, content, re.MULTILINE)
            # match = re.search(r"^table\s+['\"]?([^'\"]+)['\"]?\n\n\t", content, re.MULTILINE)
            if match:
                # Split the captured group at the specific sequence and take the first part
                # name = match.group(1).split('\n\n\t')[0].strip()
                name = match.group(2).strip()
            # If no table found, it might be a different type of object, try to name it by filename
            if name == "Unknown":
                name = file_path.stem

            # Skip system generated tables if desired (LocalDateTable, etc)
            if "LocalDateTable" in name or "DateTableTemplate" in name:
                return [], line_count

            markdown_output = f"### Project: {project_name}\n### Table: {name}\n"

            # Regex to capture Column name, Type, and its indented body
            # Logic Breakdown:
            # 1. ^\s*column\s+      -> Starts with 'column' (ignoring leading indentation)
            # 2. (['\"]?)           -> Group 1: Capture optional opening quote
            # 3. (.*?)              -> Group 2: The Column Name (lazy)
            # 4. \1                 -> Match the same quote from Group 1
            # 5. \s+                -> Required space between Name and DataType
            # 6. (.*?)              -> Group 3: The DataType and everything else...
            # 7. (?=\n\s*(?:column|measure|partition|hierarchy|annotation|lineageTag)|$) -> Lookahead stop
            column_pattern = r"^\s*column\s+(['\"]?)(.*?)\1\s+(.*?)(?=\n\s*(?:column|measure|partition|hierarchy|annotation|lineageTag)|$)"

            columns = re.findall(column_pattern, content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
            if columns:
                markdown_output += "### Data Schema (Columns)\n"
                markdown_output += "| Column Name | Data Type | Properties |\n"
                markdown_output += "| :--- | :--- | :--- |\n"

                for quote, c_name, c_body in columns:
                    clean_name = c_name.strip().strip("'\"")

                    # Split the body to separate DataType from the rest
                    body_parts = c_body.strip().split('\n')
                    data_type = body_parts[0].strip()

                    # The rest are properties like 'summarizeBy' or 'sourceColumn'
                    properties = [p.strip() for p in body_parts[1:] if p.strip()]

                    # Format for your Markdown output
                    prop_list = ", ".join(properties) if properties else "None"
                    markdown_output += f"| {clean_name} | {data_type} | {prop_list} |\n"


            """
            Extracts partition names, individual properties, and the source code.
            """

            lst_partitions = self.extract_partition_with_file_details(content)
            if lst_partitions:
                markdown_output += f"### Partitions \n"
                for partition in lst_partitions:
                    markdown_output += f"## Partition: {partition['partition_name']}\n"
                    markdown_output += f"# Connection String: {partition['connection_string']}\n"
                    markdown_output += f"# Data Source Filename: {partition['filename_only']}\n"
                    markdown_output += f"# Logic: {partition['full_logic']}\n\n"
                # partitions_found.append(partition_data)

            # --- NEW LOGIC: Master Join Keys ---
            # Check the ENTIRE table content for these keys (columns, etc)
            ##################### FIX ME #################################################################################
            # This doesn't make a terrible lot of sense - need to revisit whether it is even needed
            
            master_keys = ["Division ID", "Organization_ID", "ProjectID", "Directorate ID", "BaseRSS"]
            found_keys = [key for key in master_keys if key in content]
            
            if found_keys:
                markdown_output += "\n### Master Join Keys\n"
                markdown_output += "* **Keys Found:** " + ", ".join(found_keys) + "\n"

            #############################################################################################################
            # Identify DAX Measures
            # This pattern captures the name and the logic
            # It stops when it sees a line starting with a new keyword
            # or a property that isn't indented (like 'formatString' or 'displayFolder').
            # Updated Regex
            # 1. (.*?) with re.DOTALL captures all newlines in the DAX.
            # 2. The Lookahead now only stops for specific TMDL object keywords.
            # measure_pattern = r"^\s*measure\s+(['\"]?)(.*?)\1\s*=\s*(.*?)(?=\n\s*(?:measure|column|partition|hierarchy|annotation|lineageTag|formatString|displayFolder)|$)"
            #

            lst_measures = self.extract_measures_string_split(content)
            if lst_measures:
                markdown_output += "## Business Logic (DAX Measures)\n\n"
                for m in lst_measures:
                    markdown_output += f"### {m['name']}\n"
                    markdown_output += f"**Description**: {m['description']}\n\n"

                    # Metadata Table for a clean look
                    markdown_output += "| Attribute | Value |\n"
                    markdown_output += "| :--- | :--- |\n"
                    if m['format_string']:
                        markdown_output += f"| **Format** | `{m['format_string']}` |\n"
                    # markdown_output += f"| **Folder** | `{m['display_folder']}` |\n"
                    if m['lineage_tag']:
                        markdown_output += f"| **Lineage Tag** | `{m['lineage_tag']}` |\n"

                    markdown_output += f"\n**DAX Expression:**\n```dax\n{m['dax']}\n```\n\n"
                    markdown_output += "---\n"
            chunk = {
                "type": "tmdl_table_summary",
                "name": name,
                "content": markdown_output
            }
            return [chunk], line_count

        except Exception as e:
            logger.warning(f"Error chunking TMDL file {file_path}: {e}")
            return [], 0
            
    def chunk_model_tmdl(self, file_path: Path, project_name: str = "") -> tuple[list, int]:
        """
        Parse model.tmdl to extract table references and return an index chunk.
        """
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
            line_count = content.count('\n') + 1
            
            tables = []
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("ref table") and "LocalDateTable" not in stripped:
                    # ref table <TableName>
                    parts = stripped.split(maxsplit=2)
                    if len(parts) >= 3:
                        tables.append(parts[2])
            
            project_info = f"Project: {project_name}\n" if project_name else ""
            chunk = {
                "type": "model_index",
                "name": f"Model Index - {project_name}" if project_name else "Model Index",
                "content": f"{project_info}Tables found in model:\n" + "\n".join(f"- {t}" for t in tables)
            }
            return [chunk], line_count
        except Exception as e:
            logger.warning(f"Error processing model.tmdl {file_path}: {e}")
            return [], 0

    def vectorize_relationships(self, file_path: Path, project_name: str = "") -> tuple[list, int]:
        """
        Transforms raw relationship logs into semantic vectors
        by flattening the structure into human-readable sentences.
        Returns a single Markdown chunk with a global map and aggregated embedding.
        """
        # ---------------------------------------------------------
        # LAZY IMPORTS
        # ---------------------------------------------------------
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning("Missing dependencies for vectorize_relationships (sentence_transformers, etc).")
            # We still proceed to generate markdown even if we can't embed (embedding will be None or skipped)
            pass

        # Read the file
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                raw_data = f.read()
            line_count = raw_data.count('\n') + 1

            # Initialize the embedding model if available
            try:
                model = SentenceTransformer('all-MiniLM-L6-v2')
            except:
                model = None

            project_info = f" ({project_name})" if project_name else ""
            markdown_output = f"## 1. Global Relationship Map{project_info}\n"
            if project_name:
                markdown_output += f"**Project:** {project_name}\n\n"
            
            # 1. Parse raw relationships
            # Structure: relationship <Id> \n fromColumn: <table>[<Col>] \n toColumn: <table>[<Col>] ...
            # We use regex to identify blocks.
            
            rel_pattern = re.compile(
                r"relationship\s+(?P<id>\w+).*?"
                r"fromColumn:\s*(?P<from>.*?)\n.*?"
                r"toColumn:\s*(?P<to>.*?)(?=\n\s*(?:relationship|$))",
                re.DOTALL | re.IGNORECASE
            )
            
            relationships = rel_pattern.findall(raw_data)
            
            semantic_sentences = []
            
            for r_id, r_from, r_to in relationships:
                r_from = r_from.strip()
                r_to = r_to.strip()
                # Strip out JOINS to the LocalDateTables
                if "LocalDateTable" not in r_from and "LocalDateTable" not in r_to:
                    # Format: * **Join:** `source` → `target`
                    markdown_output += f"* **Join:** `{r_from}` → `{r_to}`\n"

                    # Create a sentence for embedding context (optional, but good for retrieval)
                    # Cleaning toColumn for semantic match (e.g. LocalDateTable -> DateTable)
                    # to_clean = re.sub(r"LocalDateTable_[a-z0-9-]+", "DateTable", r_to)
                    sentence = f"Relationship {r_id}: {r_from} links to {r_to}."
                    semantic_sentences.append(sentence)

            # Generate embedding for the WHOLE map (aggregate or single string?)
            # Plan said: "Compute embedding for this summary string."
            # So we encode 'markdown_output' or the joined semantic sentences.
            # Using the markdown output as the text for the vector makes sense for "Global Map".
            
            embedding = None
            if model and markdown_output:
                # We can embed the whole markdown text
                # OR we can embed the list of sentences and mean-pool them.
                # Let's simple-encode the markdown text for now as it represents the "Document".
                encoded = model.encode(markdown_output)
                if hasattr(encoded, "tolist"):
                    embedding = encoded.tolist()
                else:
                    embedding = encoded

            chunk = {
                 "type": "tmdl_relationships_map",
                 "name": "Global Relationship Map",
                 "content": markdown_output,
                 "embedding": embedding 
            }

            return [chunk], line_count

        except Exception as e:
            logger.warning(f"Error processing relationships.tmdl {file_path}: {e}")
            return [], 0

    def format_chunk(self, chunk: dict) -> str:
        """
        Format a chunk into plain text for saving.
        """
        # Pass-through for pre-formatted Markdown chunks
        if chunk.get("type") in ["tmdl_relationships_map", "tmdl_table_summary"]:
             # Content is already Markdown
             return chunk.get("content", "")

        if chunk.get("type") == "table":
             content = self._ensure_text(chunk.get("content", ""))
             return f"Table: {chunk.get('name')}\nContent:\n{content}"
        elif chunk.get("type") == "model_index":
             content = self._ensure_text(chunk.get("content", ""))
             return f"Model Index:\n{content}"
        elif chunk.get("type") == "model_relationships":
             content = self._ensure_text(chunk.get("content", ""))
             return f"Model Relationships:\n{content}"
        elif chunk.get("type") in ["column", "partition", "expression", "measure", 
        "annotation", "joinOnDateBehavior", "fromColumn", "toColumn",
        "joinOnDateBehavior", "database", "Source"]:
             type_label = chunk.get("type").capitalize()
             content = self._ensure_text(chunk.get("content", ""))
             parent = chunk.get("parent")
             prefix = f"Table: {parent}\n" if parent else ""
             return f"{prefix}{type_label}: {chunk.get('name')}\nContent:\n{content}"
        
        return super().format_chunk(chunk)


    def extract_partition_with_file_details(self, content):
        partitions_found = []

        # 1. Capture the partition block (Standard TMDL block)
        partition_pattern = r"^\s*partition\s+(['\"]?)(.*?)\1\s*=\s*m((?:\n\s+.*)+)"
        matches = re.findall(partition_pattern, content, re.MULTILINE | re.IGNORECASE)

        for quote, p_name, p_body in matches:
            # 2. Extract the TRUE Source Line (The connection string)
            # Look for the capitalized 'Source =' variable in the M code
            true_source_match = re.search(r"^\s*Source\s*=\s*(.*)", p_body, re.MULTILINE)
            true_source_path = true_source_match.group(1).strip() if true_source_match else ""

            # 3. Extract FILENAME ONLY (The text inside the first pair of quotes)
            # This grabs "C:\Data.csv" out of Csv.Document(File.Contents("C:\Data.csv"))
            filename_match = re.search(r'\"(.*?)\"', true_source_path)
            filename_only = filename_match.group(1) if filename_match else "Inlined/System"

            # 4. Extract the Full Logic
            logic_match = re.search(r"(let\s+.*in\s+.*)", p_body, re.DOTALL | re.IGNORECASE)
            source_logic = textwrap.dedent(logic_match.group(1)).strip() if logic_match else p_body.strip()


            partitions_found.append({
                "partition_name": p_name.strip(),
                "connection_string": true_source_path,
                "filename_only": filename_only,
                "full_logic": self.truncate_m_logic(source_logic)
            })

        return partitions_found

    def extract_measures_string_split(self, content):
        extracted_measures = []

        # 1. Split the file into chunks based on your delimiter
        # This separates tables, columns, and measures into individual strings
        chunks = content.split('\n\n\t')

        for chunk in chunks:
            # 2. Only process chunks that start with 'measure'
            line = chunk.strip()
            if line.lower().startswith('measure '):

                # 3. Separate the Header (name/logic) from the Properties
                # We split by the first newline to isolate the DAX header
                lines = line.split('\n')
                header = lines[0]  # e.g., "measure 'Total Sales' = SUM(Sales[Amount])"

                # 4. Extract Name and First Line of DAX
                # Split by the first '='
                header_parts = header.split('=', 1)
                name = header_parts[0].replace('measure', '').strip().strip("'\"")
                first_line_dax = header_parts[1].strip() if len(header_parts) > 1 else ""

                # 5. Collect the rest of the DAX until we hit TMDL properties
                dax_body = [first_line_dax]
                metadata = {}

                for extra_line in lines[1:]:
                    # Check if the line is a property (contains a colon and isn't a DAX calc)
                    if ':' in extra_line and not any(char in extra_line for char in '()[]{}'):
                        key, val = extra_line.split(':', 1)
                        metadata[key.strip().lower()] = val.strip().strip('"')
                    else:
                        dax_body.append(extra_line)

                # 6. Final Clean up
                extracted_measures.append({
                    "name": name,
                    "dax": textwrap.dedent("\n".join(dax_body)).strip(),
                    "description": metadata.get("description", "No description"),
                    "lineage_tag": metadata.get("lineagetag", None),
                    "format_string": metadata.get("formatstring", None)
                })

        return extracted_measures

    def master_tmdl_parser(self,content):
        # Dictionary to hold the final model structure
        model_data = {
            "table_name": "Unknown",
            "measures": [],
            "columns": [],
            "partitions": []
        }

        # 1. Extract the Table Name first (usually at the very top)
        table_match = re.search(r"^table\s+['\"]?([^'\"]+)['\"]?", content, re.MULTILINE)
        if table_match:
            model_data["table_name"] = table_match.group(1).strip()

        # 2. Split the file into chunks using your delimiter
        chunks = content.split('\n\n\t')

        for chunk in chunks:
            lines = chunk.strip().split('\n')
            if not lines:
                continue
                # If the chunk belongs to an internal table, skip it entirely
            if "LocalDateTable_" in chunk or "DateTableTemplate_" in chunk:
                    continue
            first_line = lines[0].strip().lower()

            # --- PROCESS MEASURES ---
            if first_line.startswith('measure '):
                header_parts = lines[0].split('=', 1)
                name = header_parts[0].replace('measure', '', 1).strip().strip("'\"")

                dax_lines = [header_parts[1].strip()] if len(header_parts) > 1 else []
                metadata = {}

                for extra_line in lines[1:]:
                    # Differentiate between DAX and Metadata (Metadata has ':' and no DAX brackets)
                    if ':' in extra_line and not any(c in extra_line for c in '()[]{}'):
                        k, v = extra_line.split(':', 1)
                        metadata[k.strip().lower()] = v.strip().strip('"')
                    else:
                        dax_lines.append(extra_line)

                model_data["measures"].append({
                    "name": name,
                    "logic": textwrap.dedent("\n".join(dax_lines)).strip(),
                    "description": metadata.get("description", ""),
                    "lineage_tag": metadata.get("lineagetag", ""),
                    "format_string": metadata.get("formatstring", "")
                })

            # --- PROCESS COLUMNS ---
            elif first_line.startswith('column '):
                # Format: column Name DataType
                header_content = lines[0].replace('column', '', 1).strip()
                # Handle quoted names with spaces
                name_match = re.search(r"(['\"]?)(.*?)\1\s+(.*)", header_content)

                if name_match:
                    name = name_match.group(2).strip()
                    data_type = name_match.group(3).strip()

                    metadata = {}
                    for extra_line in lines[1:]:
                        if ':' in extra_line:
                            k, v = extra_line.split(':', 1)
                            metadata[k.strip().lower()] = v.strip().strip('"')

                    model_data["columns"].append({
                        "name": name,
                        "data_type": data_type,
                        "description": metadata.get("description", ""),
                        "source_column": metadata.get("sourcecolumn", name),
                        "lineage_tag": metadata.get("lineagetag", "")
                    })

            # --- PROCESS PARTITIONS ---
            elif first_line.startswith('partition '):
                # Format: partition Name = m
                header_parts = lines[0].split('=', 1)
                name = header_parts[0].replace('partition', '', 1).strip().strip("'\"")

                # Find the 'Source =' line within the M code
                # Note: We look for the capitalized 'Source =' for the connection string
                m_body = "\n".join(lines[1:])
                true_source_match = re.search(r"^\s*Source\s*=\s*(.*)", m_body, re.MULTILINE)
                conn_string = true_source_match.group(1).strip() if true_source_match else "Inlined"

                # Extract filename from quotes in the connection string
                fn_match = re.search(r'\"(.*?)\"', conn_string)

                model_data["partitions"].append({
                    "name": name,
                    "connection_string": conn_string,
                    "file_name": fn_match.group(1) if fn_match else "N/A",
                    "full_m_logic": textwrap.dedent(m_body).strip()
                })

        return model_data

    # def generate_tmdl_markdown(self, model_data):
    #     """
    #     Converts model_data dictionary into a formatted Markdown report.
    #     """
    #     md = []
    #
    #     # --- 1. Header & Summary ---
    #     md.append(f"# Technical Documentation: {model_data['table_name']}")
    #     md.append(f"\n**Entity Type:** `Table` | **Source Type:** `TMDL Definition` | **Generated Date:** 2026")
    #
    #     md.append("\n## Summary")
    #     md.append(f"* **Total Columns:** {len(model_data['columns'])}")
    #     md.append(f"* **Total Measures:** {len(model_data['measures'])}")
    #     md.append(f"* **Data Partitions:** {len(model_data['partitions'])}")
    #
    #     # --- 2. Data Partitions (Source Information) ---
    #     if model_data["partitions"]:
    #         md.append("\n## Data Connectivity")
    #         for p in model_data["partitions"]:
    #             md.append(f"### Partition: {p['name']}")
    #             md.append(f"* **Connection Target:** `{p['file_name']}`")
    #             md.append(f"* **Full String:** `{p['connection_string']}`")
    #             md.append("\n**M Transformation Logic:**")
    #             md.append(f"```powerquery\n{p['full_m_logic']}\n```")
    #
    #     # --- 3. Column Schema ---
    #     if model_data["columns"]:
    #         md.append("\n## Data Schema (Columns)")
    #         md.append("| Name | Type | Source Column | Lineage Tag |")
    #         md.append("| :--- | :--- | :--- | :--- |")
    #         for c in model_data["columns"]:
    #             desc = f"<br/>*{c['description']}*" if c['description'] else ""
    #             md.append(
    #                 f"| **{c['name']}**{desc} | `{c['data_type']}` | `{c['source_column']}` | `{c['lineage_tag']}` |")
    #
    #     # --- 4. Business Logic (Measures) ---
    #     if model_data["measures"]:
    #         md.append("\n## Business Logic (DAX Measures)")
    #         for m in model_data["measures"]:
    #             md.append(f"### {m['name']}")
    #             if m['description']:
    #                 md.append(f"> {m['description']}")
    #
    #             # Metadata line
    #             meta = []
    #             if m['format_string']: meta.append(f"**Format:** `{m['format_string']}`")
    #             if m['lineage_tag']: meta.append(f"**ID:** `{m['lineage_tag']}`")
    #             if meta:
    #                 md.append(" | ".join(meta))
    #
    #             md.append(f"\n```dax\n{m['logic']}\n```")
    #             md.append("\n---")
    #
    #     return "\n".join(md)

    def prune_internal_tables(self, model_data):
        """
        Removes auto-generated Power BI date tables from the model summary.
        """
        # Define prefixes for internal Power BI artifacts
        internal_prefixes = ("LocalDateTable_", "DateTableTemplate_")

        # 1. Prune the master Table List/Index if you have one
        if "table_index" in model_data:
            model_data["table_index"] = [
                t for t in model_data["table_index"]
                if not t.startswith(internal_prefixes)
            ]

        # 2. Prune Columns (if any were captured from these tables)
        model_data["columns"] = [
            c for c in model_data["columns"]
            if not any(p in c.get("table_name", "") for p in internal_prefixes)
        ]

        # 3. Prune Relationships (This is the most impactful cleanup)
        # Most relationships in your map were connecting to these hidden tables.
        if "relationships" in model_data:
            model_data["relationships"] = [
                r for r in model_data["relationships"]
                if not any(p in r for p in internal_prefixes)
            ]

        return model_data

    import re

    def truncate_m_logic(self, m_code, max_lines=10):
        """
        Truncates repetitive Power Query transformation steps (Changed Type, Renamed Columns)
        while preserving the Source and the final 'in' result.
        """
        lines = m_code.split('\n')

        # If the logic is already short, return it as is
        if len(lines) <= max_lines:
            return m_code

        truncated_lines = []
        # Identify patterns of repetitive column lists: {"Col1", type text}, {"Col2", type int}
        # This regex looks for the common Power Query list-of-lists format
        repetition_pattern = r'\{".*?",\s*.*?\}'

        for line in lines:
            # Detect if this line is a massive transformation step
            matches = re.findall(repetition_pattern, line)

            if len(matches) > 6:  # If more than 6 column definitions in one line
                # Keep the start of the line (Step Name = Table.Transform...)
                prefix = line.split('{')[0]
                # Keep the first 3 and last 3 column transformations
                summarized_line = (
                    f"{prefix}{{ {', '.join(matches[:3])}, "
                    f"... [ {len(matches) - 6} columns omitted for brevity ] ..., "
                    f"{', '.join(matches[-3:])} }})"
                )
                truncated_lines.append(summarized_line)
            else:
                truncated_lines.append(line)

        return "\n".join(truncated_lines)