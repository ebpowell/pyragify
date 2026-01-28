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
        if file_path.name == "model.tmdl":
            return self.chunk_model_tmdl(file_path)
        elif file_path.name == "relationships.tmdl":
            return self.vectorize_relationships(file_path)

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

            markdown_output = f"### Table: {name}\n"

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
            # measures = re.findall(measure_pattern, content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
            # if measures:
            #     markdown_output += "### Business Logic (DAX Measures)\n"
            #     for quote, m_name, m_logic in measures:
            #         clean_name = m_name.strip()
            #
            #         # Split by newline and handle potential metadata if the lookahead was too broad
            #         # We want to ensure we don't capture 'formatString:' as part of the DAX
            #         logic_lines = m_logic.split('\n')
            #         final_dax_lines = []
            #
            #         for line in logic_lines:
            #             # If we hit a line that looks like a TMDL property, stop
            #             if re.match(r"^\s*\w+\s*:", line):
            #                 break
            #             final_dax_lines.append(line)
            #
            #         clean_logic = "\n".join(final_dax_lines).strip()
            #
            #         # Use dedent to clean up the leading spaces from the file structure
            #         formatted_dax = textwrap.dedent(clean_logic)
            #
            #         markdown_output += f"* **{clean_name}**\n  ```dax\n  {formatted_dax}\n  ```\n"
            lst_measures = self.extract_measures_comprehensive(content)
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
                    markdown_output += f"| **Folder** | `{m['display_folder']}` |\n"
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
            
    def chunk_model_tmdl(self, file_path: Path) -> tuple[list, int]:
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
                if stripped.startswith("ref table"):
                    # ref table <TableName>
                    parts = stripped.split(maxsplit=2)
                    if len(parts) >= 3:
                        tables.append(parts[2])
            
            chunk = {
                "type": "model_index",
                "name": "Model Index",
                "content": "Tables found in model:\n" + "\n".join(f"- {t}" for t in tables)
            }
            return [chunk], line_count
        except Exception as e:
            logger.warning(f"Error processing model.tmdl {file_path}: {e}")
            return [], 0

    def vectorize_relationships(self, file_path: Path) -> tuple[list, int]:
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

            markdown_output = "## 1. Global Relationship Map\n"
            
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
                
                # Format: * **Join:** `source` → `target`
                markdown_output += f"* **Join:** `{r_from}` → `{r_to}`\n"
                
                # Create a sentence for embedding context (optional, but good for retrieval)
                # Cleaning toColumn for semantic match (e.g. LocalDateTable -> DateTable)
                to_clean = re.sub(r"LocalDateTable_[a-z0-9-]+", "DateTable", r_to)
                sentence = f"Relationship {r_id}: {r_from} links to {to_clean}."
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
                "full_logic": source_logic
            })

        return partitions_found


    def extract_measures_comprehensive(self, content):
        # Capture the entire block until the next major TMDL object
        measure_pattern = r"^\s*measure\s+(['\"]?)(.*?)\1\s*=\s*(.*?)(?=\n\s*(?:measure|column|partition|table|hierarchy)|$)"

        matches = re.findall(measure_pattern, content, re.DOTALL | re.MULTILINE | re.IGNORECASE)

        extracted_measures = []

        for quote, name, body in matches:
            measure_data = {
                "name": name.strip(),
                "dax": "",
                "description": "No description provided.",
                "format_string": None,
                "display_folder": "Home",
                "lineage_tag": None
            }

            lines = body.split('\n')
            dax_lines = []
            metadata_started = False

            for line in lines:
                # Match the pattern 'key: value'
                prop_match = re.match(r"^\s*(description|formatString|displayFolder|lineageTag)\s*:\s*(.*)", line, re.I)

                if prop_match:
                    metadata_started = True
                    key = prop_match.group(1).lower()
                    val = prop_match.group(2).strip().strip('"')

                    if key == "description":
                        measure_data["description"] = val
                    elif key == "formatstring":
                        measure_data["format_string"] = val
                    elif key == "displayfolder":
                        measure_data["display_folder"] = val
                    elif key == "lineagetag":
                        measure_data["lineage_tag"] = val
                elif not metadata_started:
                    # If we haven't hit a metadata key, we are still inside the DAX formula
                    dax_lines.append(line)

            measure_data["dax"] = textwrap.dedent("\n".join(dax_lines)).strip()
            extracted_measures.append(measure_data)

        return extracted_measures