import logging
from pathlib import Path
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
        """
        if file_path.name == "model.tmdl":
            return self.chunk_model_tmdl(file_path)

        chunks = []
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
            line_count = len(lines)

            # Keywords to track
            keywords = ["table", "column", "partition", "expression", "measure", "annotation"]
            
            # Helper to calculate indentation
            def get_indent(line):
                return len(line) - len(line.lstrip())

            # Identify all blocks starting with a keyword
            # Structure: (start_index, indent_level, type, name, header_line, parent)
            blocks = []
            current_table_name = None

            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                
                parts = stripped.split(maxsplit=1)
                if not parts:
                    continue
                
                kw = parts[0]
                if kw in keywords:
                    name = ""
                    if kw == "annotation":
                        name = parts[1] if len(parts) > 1 else "Unnamed"
                    elif len(parts) > 1:
                        rest = parts[1]
                        if "=" in rest:
                             name = rest.split("=", 1)[0].strip()
                        else:
                             name = rest.strip()
                    
                    # Update current table context if we hit a table
                    if kw == "table":
                        current_table_name = name

                    blocks.append({
                        "start_index": i,
                        "indent": get_indent(line),
                        "type": kw,
                        "name": name,
                        "header": stripped,
                        "parent": current_table_name if kw != "table" else None
                    })

            # For each identified block, capture its content
            for block in blocks:
                start_i = block["start_index"]
                base_indent = block["indent"]
                
                content_lines = [lines[start_i]]
                
                # Scan subsequent lines
                for j in range(start_i + 1, len(lines)):
                    next_line = lines[j]
                    if not next_line.strip():
                        content_lines.append(next_line)
                        continue
                    
                    next_indent = get_indent(next_line)
                    if next_indent > base_indent:
                        content_lines.append(next_line)
                    else:
                        break
                
                while content_lines and not content_lines[-1].strip():
                    content_lines.pop()
                    
                chunks.append({
                    "type": block["type"],
                    "name": block["name"],
                    "content": "".join(content_lines),
                    "parent": block.get("parent")
                })

            if not chunks:
                 # Fallback: treat as file
                 return [{
                    "type": "file",
                    "name": file_path.name,
                    "content": "".join(lines)
                }], line_count

        except Exception as e:
            logger.warning(f"Error chunking TMDL file {file_path}: {e}")
            return [], 0
            
        return chunks, line_count

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

    def format_chunk(self, chunk: dict) -> str:
        """
        Format a chunk into plain text for saving.
        """
        if chunk.get("type") == "table":
             content = self._ensure_text(chunk.get("content", ""))
             return f"Table: {chunk.get('name')}\nContent:\n{content}"
        elif chunk.get("type") == "model_index":
             content = self._ensure_text(chunk.get("content", ""))
             return f"Model Index:\n{content}"
        elif chunk.get("type") in ["column", "partition", "expression", "measure", 
        "annotation", "relationship","joinOnDateBehavior", "fromColumn", "toColumn", 
        "joinOnDateBehavior", "database"]:
             type_label = chunk.get("type").capitalize()
             content = self._ensure_text(chunk.get("content", ""))
             parent = chunk.get("parent")
             prefix = f"Table: {parent}\n" if parent else ""
             return f"{prefix}{type_label}: {chunk.get('name')}\nContent:\n{content}"
        
        return super().format_chunk(chunk)
