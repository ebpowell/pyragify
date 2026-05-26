import logging
import re
from pathlib import Path
from processor import FileProcessor

logger = logging.getLogger(__name__)

def split_by_comma_nesting(text: str) -> list[str]:
    """
    Split a string by comma at parenthesis depth 0, ignoring commas inside quotes.
    """
    parts = []
    current = []
    depth = 0
    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    
    i = 0
    while i < len(text):
        char = text[i]
        if char == '\\' and i + 1 < len(text):
            current.append(text[i:i+2])
            i += 2
            continue
            
        if char == "'" and not in_double_quote and not in_backtick:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote and not in_backtick:
            in_double_quote = not in_double_quote
        elif char == '`' and not in_single_quote and not in_double_quote:
            in_backtick = not in_backtick
            
        if not in_single_quote and not in_double_quote and not in_backtick:
            if char in ('(', '[', '{'):
                depth += 1
            elif char in (')', ']', '}'):
                depth -= 1
            elif char == ',' and depth == 0:
                parts.append("".join(current).strip())
                current = []
                i += 1
                continue
        current.append(char)
        i += 1
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]

def extract_table_name(table_ref: str) -> str | None:
    """
    Extract table name from a table reference (stripping alias and quotes).
    """
    table_ref = table_ref.strip().rstrip(';')
    if not table_ref or table_ref.startswith('('):
        return None
    parts = re.split(r'\s+', table_ref)
    first_part = parts[0]
    # Remove quotes/backticks
    clean_table = first_part.replace('`', '').replace('"', '').replace("'", "")
    return clean_table

def scan_clauses(tokens) -> list[tuple[str, list]]:
    """
    Scan tokens at top level (depth 0) and partition them into clauses.
    """
    import sqlparse
    
    clauses = []
    current_clause_type = None
    current_clause_tokens = []
    
    depth = 0
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        # Parenthesis depth tracking
        if token.value == '(':
            depth += 1
        elif token.value == ')':
            depth -= 1
            
        is_top_level = (depth == 0 or (depth == 1 and token.value == '('))
        
        if is_top_level and (token.ttype in (sqlparse.tokens.Keyword, sqlparse.tokens.Keyword.DML) or token.value.upper() in ('GROUP', 'ORDER', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'CROSS', 'FULL', 'NATURAL', 'JOIN')):
            val = token.value.upper()
            
            clause_type = None
            offset = 1
            
            if val == 'SELECT':
                clause_type = 'SELECT'
            elif val == 'FROM':
                clause_type = 'FROM'
            elif val in ('WHERE', 'HAVING', 'LIMIT', 'UNION', 'INTERSECT', 'EXCEPT'):
                clause_type = val
            elif val == 'GROUP' and i + 2 < len(tokens) and tokens[i+2].value.upper() == 'BY':
                clause_type = 'GROUP BY'
                offset = 3
            elif val == 'ORDER' and i + 2 < len(tokens) and tokens[i+2].value.upper() == 'BY':
                clause_type = 'ORDER BY'
                offset = 3
            elif 'JOIN' in val:
                clause_type = 'JOIN'
            elif val in ('LEFT', 'RIGHT', 'INNER', 'OUTER', 'CROSS', 'FULL', 'NATURAL'):
                # Look ahead for JOIN keyword
                j = i + 1
                while j < len(tokens) and tokens[j].is_whitespace:
                    j += 1
                if j < len(tokens) and (tokens[j].ttype in (sqlparse.tokens.Keyword, sqlparse.tokens.Keyword.DML) or tokens[j].value.upper() in ('JOIN', 'OUTER', 'INNER')):
                    next_val = tokens[j].value.upper()
                    if next_val == 'JOIN':
                        clause_type = 'JOIN'
                        offset = j - i + 1
                    elif next_val in ('OUTER', 'INNER'):
                        k = j + 1
                        while k < len(tokens) and tokens[k].is_whitespace:
                            k += 1
                        if k < len(tokens) and tokens[k].value.upper() == 'JOIN':
                            clause_type = 'JOIN'
                            offset = k - i + 1
            
            if clause_type:
                # Save previous clause
                if current_clause_type:
                    clauses.append((current_clause_type, current_clause_tokens))
                current_clause_type = clause_type
                current_clause_tokens = tokens[i:i+offset]
                i += offset
                continue
                
        if current_clause_type:
            current_clause_tokens.append(token)
        else:
            if not token.is_whitespace or current_clause_tokens:
                current_clause_type = 'HEADER'
                current_clause_tokens = [token]
                
        i += 1
        
    if current_clause_type:
        clauses.append((current_clause_type, current_clause_tokens))
        
    return clauses

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
        Chunk a SQL file into granular semantic sections.
        """
        # ---------------------------------------------------------
        # LAZY IMPORTS: Only load heavy libraries if SQL Files
        # ---------------------------------------------------------
        try:
            import sqlparse
        except ImportError:
            raise ImportError("sqlparse is required for SqlProcessor")
            
        chunks = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            line_count = content.count('\n') + 1

            # Use sqlparse to split/parse statements
            statements = sqlparse.parse(content)
            
            for i, stmt in enumerate(statements):
                # 1. Leading comments extraction
                comment_tokens = []
                non_comment_tokens = []
                found_non_comment = False
                
                for token in stmt.tokens:
                    if not found_non_comment:
                        is_comment = (
                            token.ttype in (sqlparse.tokens.Comment, sqlparse.tokens.Comment.Single, sqlparse.tokens.Comment.Multiline) or
                            isinstance(token, sqlparse.sql.Comment)
                        )
                        if token.is_whitespace or is_comment:
                            comment_tokens.append(token)
                        else:
                            found_non_comment = True
                            non_comment_tokens.append(token)
                    else:
                        non_comment_tokens.append(token)
                        
                comment_str = "".join(t.value for t in comment_tokens).strip()
                remaining_sql = "".join(t.value for t in non_comment_tokens).strip()
                
                if not remaining_sql:
                    # It was just a comment block
                    if comment_str:
                        chunks.append({
                            "type": "sql_comment",
                            "name": "Comment",
                            "content": comment_str
                        })
                    continue

                stmt_info = {
                    "comment": comment_str if comment_str else None,
                    "sql_create": None,
                    "sql_select": None,
                    "sql_from": None,
                    "sql_joins": []
                }
                
                # 2. DDL Check
                ddl_regex = re.compile(
                    r'^\s*(CREATE(?:\s+OR\s+REPLACE)?(?:\s+(?:TEMP|TEMPORARY|SECURE))?\s+(?:TABLE|VIEW|FUNCTION|PROCEDURE|MATERIALIZED\s+VIEW|INDEX|TRIGGER))\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(\)]+)',
                    re.IGNORECASE | re.DOTALL
                )
                ddl_match = ddl_regex.match(remaining_sql)
                if ddl_match:
                    sql_type = ddl_match.group(1).upper()
                    sql_type = re.sub(r'\s+', ' ', sql_type)
                    name = ddl_match.group(2).strip().rstrip(';').replace('`', '').replace('"', '').replace("'", "")
                    stmt_info["sql_create"] = {
                        "type": "sql_create",
                        "sql_type": sql_type,
                        "name": name,
                        "content": remaining_sql
                    }

                # 3. Parse clauses
                try:
                    clauses = scan_clauses(non_comment_tokens)
                    for clause_type, clause_tokens in clauses:
                        clause_content = "".join(t.value for t in clause_tokens).strip()
                        
                        if clause_type == 'SELECT':
                            select_text = re.sub(r'^\s*SELECT\s+', '', clause_content, flags=re.IGNORECASE).strip().rstrip(';')
                            fields = split_by_comma_nesting(select_text)
                            stmt_info["sql_select"] = {
                                "type": "sql_select",
                                "name": "SELECT Fields",
                                "fields": fields,
                                "content": clause_content.rstrip(';')
                            }
                        elif clause_type == 'FROM':
                            from_text = re.sub(r'^\s*FROM\s+', '', clause_content, flags=re.IGNORECASE).strip().rstrip(';')
                            table_refs = split_by_comma_nesting(from_text)
                            tables = []
                            for ref in table_refs:
                                tbl = extract_table_name(ref)
                                if tbl:
                                    tables.append(tbl)
                            stmt_info["sql_from"] = {
                                "type": "sql_from",
                                "name": "FROM Tables",
                                "tables": tables,
                                "content": clause_content.rstrip(';')
                            }
                        elif clause_type == 'JOIN':
                            join_regex = re.compile(
                                r'^\s*(?:LEFT|RIGHT|INNER|OUTER|CROSS|FULL|NATURAL)?\s*(?:OUTER|INNER)?\s*JOIN\s+(.*?)(?:\s+((?:ON|USING)\s+.*))?$',
                                re.IGNORECASE | re.DOTALL
                            )
                            join_match = join_regex.match(clause_content)
                            table_name = "Unknown"
                            condition_text = "None"
                            if join_match:
                                table_ref = join_match.group(1).strip().rstrip(';')
                                tbl = extract_table_name(table_ref)
                                if tbl:
                                    table_name = tbl
                                if join_match.group(2):
                                    condition_text = join_match.group(2).strip().rstrip(';')
                            
                            stmt_info["sql_joins"].append({
                                "type": "sql_join",
                                "name": f"JOIN - {table_name}",
                                "table": table_name,
                                "condition": condition_text,
                                "content": clause_content.rstrip(';')
                            })
                except Exception as parse_ex:
                    logger.warning(f"Error parsing SQL clauses: {parse_ex}")

                # 4. Emit Chunks
                has_granular = (
                    stmt_info["sql_create"] is not None or
                    stmt_info["sql_select"] is not None or
                    stmt_info["sql_from"] is not None or
                    len(stmt_info["sql_joins"]) > 0
                )
                
                if stmt_info["comment"]:
                    chunks.append({
                        "type": "sql_comment",
                        "name": "Comment",
                        "content": stmt_info["comment"]
                    })
                    
                if has_granular:
                    if stmt_info["sql_create"]:
                        chunks.append(stmt_info["sql_create"])
                    if stmt_info["sql_select"]:
                        chunks.append(stmt_info["sql_select"])
                    if stmt_info["sql_from"]:
                        chunks.append(stmt_info["sql_from"])
                    for join_chunk in stmt_info["sql_joins"]:
                        chunks.append(join_chunk)
                else:
                    chunks.append({
                        "type": "sql_statement",
                        "sql_type": "SQL Statement",
                        "name": "Statement",
                        "content": remaining_sql
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

    def vectorize_sql(self, file_path: Path) -> tuple[list, list[str], list[dict]]:
        """
        Transforms SQL granular chunks into semantic vectors.
        This serves as the vectorization engine for SQL files.
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("sentence-transformers is required for vectorize_sql")
            
        try:
            # Get the granular chunks
            chunks, line_count = self.chunk_sql_file(file_path)
            
            # Initialize the embedding model
            model = SentenceTransformer('all-MiniLM-L6-v2')

            processed_strings = []
            metadata = []

            for i, chunk in enumerate(chunks):
                # Format chunk to human-readable semantic string
                semantic_desc = self.format_chunk(chunk)
                processed_strings.append(semantic_desc)

                meta = {
                    "id": f"chunk_{i}",
                    "type": chunk.get("type"),
                    "name": chunk.get("name"),
                    **{k: v for k, v in chunk.items() if k not in ("type", "name", "content")}
                }
                metadata.append(meta)

            embeddings = model.encode(processed_strings)
            # Ensure it is a list or array
            return embeddings, processed_strings, metadata

        except Exception as e:
            logger.warning(f"Error vectorizing SQL file {file_path}: {e}")
            return [], [], []

    def format_chunk(self, chunk: dict) -> str:
        """
        Format a chunk into plain text for saving/vectorizing.
        """
        chunk_type = chunk.get("type")
        if chunk_type == "sql_comment":
            return f"SQL Comment:\n{chunk.get('content')}"
        elif chunk_type == "sql_create":
            return f"SQL DDL: {chunk.get('sql_type')} {chunk.get('name')}\nContent:\n{chunk.get('content')}"
        elif chunk_type == "sql_select":
            fields = ", ".join(chunk.get("fields", []))
            return f"SQL SELECT Fields: {fields}\nClause:\n{chunk.get('content')}"
        elif chunk_type == "sql_from":
            tables = ", ".join(chunk.get("tables", []))
            return f"SQL FROM Tables: {tables}\nClause:\n{chunk.get('content')}"
        elif chunk_type == "sql_join":
            table = chunk.get("table", "Unknown")
            condition = chunk.get("condition", "None")
            return f"SQL JOIN Table: {table}\nCondition: {condition}\nClause:\n{chunk.get('content')}"
        elif chunk_type == "sql_statement":
            content = self._ensure_text(chunk.get("content", ""))
            sql_type = chunk.get("sql_type", "SQL")
            name = chunk.get("name", "Unknown")
            return f"{sql_type}: {name}\nContent:\n{content}"
        
        return super().format_chunk(chunk)
