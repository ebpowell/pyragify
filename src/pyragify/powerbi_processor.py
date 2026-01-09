import logging
from pathlib import Path
import re
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
            match = re.search(r"^table\s+['\"]?([^'\"]+)['\"]?", content, re.MULTILINE)
            if match:
                name = match.group(1).strip()
            # If no table found, it might be a different type of object, try to name it by filename
            if name == "Unknown":
                name = file_path.stem

            # Skip system generated tables if desired (LocalDateTable, etc)
            if "LocalDateTable" in name or "DateTableTemplate" in name:
                return [], line_count

            markdown_output = f"## Table: {name}\n"

            # Identify Data Source (Power Query / M-Code)
            # RegEx: looking for 'partition <name> = m' ... 'source = let ... in'
            # Adapting User's RegEx: source =\s+let\n(.*?)\nin
            # Robust RegEx to handle indentation and newlines found in TMDL
            source_match = re.search(r"source\s*=\s*let\s*(.*?)\s*in", content, re.DOTALL | re.IGNORECASE)
            if source_match:
                m_code = source_match.group(1).strip()
                markdown_output += "### Data Lineage & Transformations\n"
                markdown_output += "```powerquery\n" + m_code + "\n```\n"

                # --- NEW LOGIC: External Sources ---
                urls = set(re.findall(r'Web\.Contents\("([^"]+)"\)', m_code))
                if urls:
                    markdown_output += "\n#### External Sources\n"
                    for url in urls:
                        markdown_output += f"* **External Source:** {url}\n"

                # --- NEW LOGIC: Transformation Steps ---
                # Looking for #"Step Name" = ...
                steps = re.findall(r'#"(.*?)"\s*=\s*(.*?)(?:,|\n\t\tin)', m_code, re.DOTALL)
                if steps:
                    markdown_output += "\n#### Transformation Steps\n"
                    for step_name, logic in steps:
                        # Truncate logic for readability if too long
                        clean_logic = logic.strip().replace('\n', ' ')
                        if len(clean_logic) > 100:
                            clean_logic = clean_logic[:100] + "..."
                        markdown_output += f"* **{step_name}**: `{clean_logic}`\n"

            # --- NEW LOGIC: Master Join Keys ---
            # Check the ENTIRE table content for these keys (columns, etc)
            master_keys = ["Division ID", "Organization_ID", "ProjectID", "Directorate ID", "BaseRSS"]
            found_keys = [key for key in master_keys if key in content]
            
            if found_keys:
                markdown_output += "\n### Master Join Keys\n"
                markdown_output += "* **Keys Found:** " + ", ".join(found_keys) + "\n"


            # Identify DAX Measures
            # User's RegEx: measure (.*?) = (.*?)(?=\n\t\w+:|\n\n|$)
            # Raw TMDL: measure 'Name' = Expression ...
            # We need to match 'measure' keyword, then Name (quoted or not), then =, then Expression
            # until next keyword or end of block.
            # Simplified approach: Look for lines starting with 'measure'
            measures = re.findall(r"^\s*measure\s+(.*?)\s*=\s*(.*?)(?=\s*(?:\n\s*\w+)|$)", content, re.DOTALL | re.MULTILINE)
            if measures:
                markdown_output += "### Business Logic (DAX Measures)\n"
                for m_name, m_logic in measures:
                    # Clean up name if quoted
                    clean_name = m_name.strip().strip("'\"")
                    # Clean up logic (remove line continuations or extra spaces if needed)
                    # For now, just take what's captured
                    clean_logic = m_logic.strip()
                    markdown_output += f"* **{clean_name}**: `{clean_logic}`\n"


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
