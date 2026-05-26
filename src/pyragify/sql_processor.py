import logging
from pathlib import Path
from processor import FileProcessor

logger = logging.getLogger(__name__)

class SqlProcessor(FileProcessor):
    """
    Processor for SQL files.
    """

    def chunk_file(self, file_path: Path) -> tuple[list, int]:
        """
        Chunk a file into semantic sections based on its type.
        
        Overrides FileProcessor.chunk_file to handle .sql files.
        """
        if file_path.suffix == ".sql":
            return self.chunk_sql_file(file_path)
        return super().chunk_file(file_path)

    def chunk_sql_file(self, file_path: Path) -> tuple[list, int]:
        """
        Chunk a SQL file into semantic sections (statements).
        """
        # ---------------------------------------------------------
        # LAZY IMPORTS: Only load heavy libraries if SQL Files
        # ---------------------------------------------------------
        try:
            import re
            from sentence_transformers import SentenceTransformer
            import sqlparse
        except ImportError:
            raise ImportError()
        chunks = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            line_count = content.count('\n') + 1

            # Use sqlparse to split into statements
            statements = sqlparse.split(content)
            
            for i, statement in enumerate(statements):
                statement = statement.strip()
                if not statement:
                    continue

                # Basic identification of statement type
                stmt_type = "SQL Statement"
                # Extract first word as type
                match = re.match(r'^(\w+)', statement)
                if match:
                    stmt_type = match.group(1).upper()
                else:
                    if statement[0:2] == '--' or statement[0:2] == '/*':
                        stmt_type = 'Comment'
                
                # Try to extract a name if CREATE/ALTER/DROP
                name = "Unknown"
                name_match = re.search(r'(?:TABLE|VIEW|PROCEDURE|FUNCTION|INDEX|TRIGGER)\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(]+)', statement, re.IGNORECASE)
                if name_match:
                    name = name_match.group(1)

                chunks.append({
                    "type": "sql_statement",
                    "sql_type": stmt_type,
                    "name": name,
                    "content": statement
                })

            if not chunks:
                 return [{
                    "type": "file",
                    "name": file_path.name,
                    "content": content
                }], line_count

        except Exception as e:
            logger.warning(f"Error chunking SQL file {file_path}: {e}")
            width_fallback = file_path.read_text(encoding="utf-8")
            return [{
                "type": "file",
                "name": file_path.name,
                "content": width_fallback
            }], width_fallback.count('\n') + 1
            
        return chunks, line_count

    def vectorize_sql(self, file_path: Path) -> tuple[list, int]:
        """
        Transforms SQL statements into semantic vectors.
        This serves as the vectorization engine for SQL files.
        """
        # ---------------------------------------------------------
        # LAZY IMPORTS: Only load heavy libraries if SQL Files
        # ---------------------------------------------------------
        try:
            import re
            from sentence_transformers import SentenceTransformer
            import sqlparse
        except ImportError:
            raise ImportError()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Initialize the embedding model
            model = SentenceTransformer('all-MiniLM-L6-v2')

            statements = sqlparse.split(content)
            processed_strings = []
            metadata = []

            for i, statement in enumerate(statements):
                statement = statement.strip()
                if not statement:
                    continue

                # Create a semantic description
                # For now, we use the raw statement + some context
                stmt_type = "SQL Statement"
                match = re.match(r'^(\w+)', statement)
                if match:
                    stmt_type = match.group(1).upper()

                semantic_description = f"{stmt_type}: {statement}"
                processed_strings.append(semantic_description)

                metadata.append({
                    "id": f"stmt_{i}",
                    "type": stmt_type,
                    "raw_text": statement
                })

            embeddings = model.encode(processed_strings)
            return embeddings, processed_strings, metadata

        except Exception as e:
            logger.warning(f"Error vectorizing SQL file {file_path}: {e}")
            return [], [], []

    def format_chunk(self, chunk: dict) -> str:
        """
        Format a chunk into plain text for saving.
        """
        if chunk.get("type") == "sql_statement":
            content = self._ensure_text(chunk.get("content", ""))
            sql_type = chunk.get("sql_type", "SQL")
            name = chunk.get("name", "Unknown")
            return f"{sql_type}: {name}\nContent:\n{content}"
        
        return super().format_chunk(chunk)
