import logging
from pathlib import Path
from pyragify.processor import FileProcessor

logger = logging.getLogger(__name__)

class pbi_processor(FileProcessor):
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
        Chunk a TMDL file into semantic sections (tables).

        Parameters
        ----------
        file_path : pathlib.Path
            The path to the TMDL file to be chunked.

        Returns
        -------
        tuple[list, int]
            A tuple containing a list of chunks and the total number of lines in the file.
        """
        if file_path.name == "model.tmdl":
            return self.chunk_model_tmdl(file_path)

        chunks = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            line_count = len(lines)

            current_chunk = None
            
            for line in lines:
                stripped_line = line.strip()
                # Basic TMDL table detection: starts with 'table' followed by name
                # Tables are top-level definitions usually not indented or indented at root
                # But typically 'table <Name>'
                
                if stripped_line.startswith("table "):
                    if current_chunk:
                         chunks.append(current_chunk)
                    
                    table_name = stripped_line.split(" ", 1)[1].strip()
                    current_chunk = {
                        "type": "table",
                        "name": table_name,
                        "content": line
                    }
                elif current_chunk:
                    current_chunk["content"] += line
                
            if current_chunk:
                chunks.append(current_chunk)
                
            # Fallback if no tables found, treat as single text file ???
            # Requirement said "process ... files for tables".
            # If empty chunks, maybe return file as whole? 
            if not chunks:
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
            with open(file_path, "r", encoding="utf-8") as f:
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
        
        return super().format_chunk(chunk)
