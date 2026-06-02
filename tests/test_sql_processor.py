import pytest
from pathlib import Path
from pyragify.sql_processor import SqlProcessor

@pytest.fixture
def temp_sql_file(tmp_path):
    def _create_file(content: str, filename: str = "query.sql") -> Path:
        file_path = tmp_path / filename
        file_path.write_text(content, encoding="utf-8")
        return file_path
    return _create_file

class TestSqlProcessor:
    def test_chunk_sql_simple_select(self, temp_sql_file, tmp_path):
        """Test simple SELECT statement chunking."""
        sql_content = "SELECT a, b, c FROM schema.my_table;"
        file_path = temp_sql_file(sql_content)
        
        processor = SqlProcessor(tmp_path, tmp_path)
        chunks, line_count = processor.chunk_sql_file(file_path)
        
        assert line_count == 1
        # Expecting sql_select and sql_from
        assert len(chunks) == 2
        
        select_chunk = chunks[0]
        assert select_chunk["type"] == "sql_select"
        assert select_chunk["fields"] == ["a", "b", "c"]
        assert "SELECT a, b, c" in select_chunk["content"]
        assert select_chunk["filename"] == "query.sql"
        
        from_chunk = chunks[1]
        assert from_chunk["type"] == "sql_from"
        assert from_chunk["tables"] == ["schema.my_table"]
        assert "FROM schema.my_table" in from_chunk["content"]
        assert from_chunk["filename"] == "query.sql"

    def test_chunk_sql_comment_extraction(self, temp_sql_file, tmp_path):
        """Test isolating leading comment blocks to separate chunks."""
        sql_content = """-- This is a single-line comment
/*
This is a multi-line comment block
*/
SELECT id FROM users;"""
        file_path = temp_sql_file(sql_content)
        
        processor = SqlProcessor(tmp_path, tmp_path)
        chunks, line_count = processor.chunk_sql_file(file_path)
        
        assert line_count == 5
        # Expecting: sql_comment, sql_select, sql_from
        assert len(chunks) == 3
        
        comment_chunk = chunks[0]
        assert comment_chunk["type"] == "sql_comment"
        assert "This is a single-line comment" in comment_chunk["content"]
        assert "This is a multi-line comment block" in comment_chunk["content"]
        assert comment_chunk["filename"] == "query.sql"
        
        select_chunk = chunks[1]
        assert select_chunk["type"] == "sql_select"
        assert select_chunk["fields"] == ["id"]
        assert select_chunk["filename"] == "query.sql"
        
        from_chunk = chunks[2]
        assert from_chunk["type"] == "sql_from"
        assert from_chunk["tables"] == ["users"]
        assert from_chunk["filename"] == "query.sql"

    def test_chunk_sql_ddl_statement(self, temp_sql_file, tmp_path):
        """Test CREATE OR REPLACE TABLE / VIEW / FUNCTION etc. parsing."""
        sql_content = """
        -- Create a new table
        CREATE OR REPLACE TABLE my_project.my_dataset.my_table AS
        SELECT name, age FROM raw_users;
        """
        file_path = temp_sql_file(sql_content)
        
        processor = SqlProcessor(tmp_path, tmp_path)
        chunks, line_count = processor.chunk_sql_file(file_path)
        
        # Expecting: sql_comment, sql_create, sql_select, sql_from
        assert len(chunks) == 4
        
        comment_chunk = chunks[0]
        assert comment_chunk["type"] == "sql_comment"
        assert comment_chunk["filename"] == "query.sql"
        
        create_chunk = chunks[1]
        assert create_chunk["type"] == "sql_create"
        assert create_chunk["sql_type"] == "CREATE OR REPLACE TABLE"
        assert create_chunk["name"] == "my_project.my_dataset.my_table"
        assert create_chunk["filename"] == "query.sql"
        
        select_chunk = chunks[2]
        assert select_chunk["type"] == "sql_select"
        assert select_chunk["fields"] == ["name", "age"]
        assert select_chunk["filename"] == "query.sql"
        
        from_chunk = chunks[3]
        assert from_chunk["type"] == "sql_from"
        assert from_chunk["tables"] == ["raw_users"]
        assert from_chunk["filename"] == "query.sql"

    def test_chunk_sql_joins(self, temp_sql_file, tmp_path):
        """Test JOIN clause deconstruction (tables, aliases, conditions)."""
        sql_content = """
        SELECT u.id, o.order_date, d.delivery_status
        FROM my_db.users u
        LEFT JOIN my_db.orders o ON u.id = o.user_id
        INNER JOIN my_db.deliveries d USING (order_id);
        """
        file_path = temp_sql_file(sql_content)
        
        processor = SqlProcessor(tmp_path, tmp_path)
        chunks, line_count = processor.chunk_sql_file(file_path)
        
        # Expecting: sql_select, sql_from, two sql_joins
        assert len(chunks) == 4
        
        select_chunk = chunks[0]
        assert select_chunk["type"] == "sql_select"
        assert select_chunk["fields"] == ["u.id", "o.order_date", "d.delivery_status"]
        assert select_chunk["filename"] == "query.sql"
        
        from_chunk = chunks[1]
        assert from_chunk["type"] == "sql_from"
        assert from_chunk["tables"] == ["my_db.users"]
        assert from_chunk["filename"] == "query.sql"
        
        join_chunk1 = chunks[2]
        assert join_chunk1["type"] == "sql_join"
        assert join_chunk1["table"] == "my_db.orders"
        assert join_chunk1["condition"] == "ON u.id = o.user_id"
        assert "LEFT JOIN" in join_chunk1["content"]
        assert join_chunk1["filename"] == "query.sql"
        
        join_chunk2 = chunks[3]
        assert join_chunk2["type"] == "sql_join"
        assert join_chunk2["table"] == "my_db.deliveries"
        assert join_chunk2["condition"] == "USING (order_id)"
        assert "INNER JOIN" in join_chunk2["content"]
        assert join_chunk2["filename"] == "query.sql"
        
        # Verify parent statement links and names are consistent
        assert select_chunk["parent_stmt"] is not None
        assert select_chunk["parent_stmt"] == from_chunk["parent_stmt"] == join_chunk1["parent_stmt"] == join_chunk2["parent_stmt"]
        assert select_chunk["parent_name"] == "Query on my_db.users"

    def test_chunk_sql_fallback(self, temp_sql_file, tmp_path):
        """Test non-query SQL statements fall back to default sql_statement type."""
        sql_content = "COMMIT;"
        file_path = temp_sql_file(sql_content)
        
        processor = SqlProcessor(tmp_path, tmp_path)
        chunks, _ = processor.chunk_sql_file(file_path)
        
        assert len(chunks) == 1
        assert chunks[0]["type"] == "sql_statement"
        assert chunks[0]["content"] == "COMMIT;"
        assert chunks[0]["filename"] == "query.sql"

    def test_format_chunks(self):
        """Test formatting of granular chunks."""
        processor = SqlProcessor(Path("."), Path("."))
        
        # Comment
        comment_chunk = {
            "type": "sql_comment",
            "content": "-- my comment",
            "parent_stmt": "abc12345",
            "parent_name": "my_view"
        }
        formatted = processor.format_chunk(comment_chunk)
        assert "SQL Comment (Statement: my_view, Link ID: abc12345):\n-- my comment" in formatted

        # Comment with filename
        comment_chunk_with_file = {
            "type": "sql_comment",
            "content": "-- my comment",
            "parent_stmt": "abc12345",
            "parent_name": "my_view",
            "filename": "query.sql"
        }
        formatted_with_file = processor.format_chunk(comment_chunk_with_file)
        assert "SQL Comment (File: query.sql, Statement: my_view, Link ID: abc12345):\n-- my comment" in formatted_with_file
        
        # DDL
        ddl_chunk = {
            "type": "sql_create",
            "sql_type": "CREATE VIEW",
            "name": "my_view",
            "content": "CREATE VIEW my_view AS SELECT 1;",
            "parent_stmt": "abc12345",
            "parent_name": "my_view",
            "filename": "query.sql"
        }
        formatted = processor.format_chunk(ddl_chunk)
        assert "SQL DDL: CREATE VIEW my_view (File: query.sql, Statement: my_view, Link ID: abc12345)" in formatted
        assert "Content:\nCREATE VIEW my_view AS SELECT 1;" in formatted
        
        # Select
        select_chunk = {
            "type": "sql_select",
            "fields": ["field_1", "field_2"],
            "content": "SELECT field_1, field_2",
            "parent_stmt": "abc12345",
            "parent_name": "my_view",
            "filename": "query.sql"
        }
        formatted = processor.format_chunk(select_chunk)
        assert "SQL SELECT Fields: field_1, field_2 (File: query.sql, Statement: my_view, Link ID: abc12345)" in formatted
        assert "Clause:\nSELECT field_1, field_2" in formatted
        
        # From
        from_chunk = {
            "type": "sql_from",
            "tables": ["my_schema.table_a"],
            "content": "FROM my_schema.table_a",
            "parent_stmt": "abc12345",
            "parent_name": "my_view",
            "filename": "query.sql"
        }
        formatted = processor.format_chunk(from_chunk)
        assert "SQL FROM Tables: my_schema.table_a (File: query.sql, Statement: my_view, Link ID: abc12345)" in formatted
        
        # Join
        join_chunk = {
            "type": "sql_join",
            "table": "table_b",
            "condition": "a.id = b.id",
            "content": "JOIN table_b ON a.id = b.id",
            "parent_stmt": "abc12345",
            "parent_name": "my_view",
            "filename": "query.sql"
        }
        formatted = processor.format_chunk(join_chunk)
        assert "SQL JOIN Table: table_b (File: query.sql, Statement: my_view, Link ID: abc12345)" in formatted
        assert "Condition: a.id = b.id" in formatted

    def test_vectorize_sql(self, temp_sql_file, tmp_path):
        """Test semantic vectorization of SQL granular chunks."""
        sql_content = "SELECT a FROM t JOIN t2 ON t.id = t2.id;"
        file_path = temp_sql_file(sql_content)
        
        processor = SqlProcessor(tmp_path, tmp_path)
        embeddings, processed_strings, metadata = processor.vectorize_sql(file_path)
        
        # Expect three chunks: SELECT, FROM, JOIN
        assert len(processed_strings) == 3
        assert len(metadata) == 3
        
        assert metadata[0]["type"] == "sql_select"
        assert metadata[1]["type"] == "sql_from"
        assert metadata[2]["type"] == "sql_join"
        
        # Validate that embeddings is a non-empty sequence
        assert len(embeddings) == 3
        assert len(embeddings[0]) > 0

    def test_chunk_sql_ddl_alter_drop_add(self, temp_sql_file, tmp_path):
        """Test ALTER, DROP, and ADD statements parsing."""
        sql_content = """
        ALTER TABLE my_schema.my_table ADD COLUMN email VARCHAR(255);
        DROP TABLE IF EXISTS my_schema.old_table;
        ADD CONSTRAINT pk_id PRIMARY KEY (id);
        """
        file_path = temp_sql_file(sql_content)
        
        processor = SqlProcessor(tmp_path, tmp_path)
        chunks, _ = processor.chunk_sql_file(file_path)
        
        # Expecting three DDL chunks
        assert len(chunks) == 3
        
        alter_chunk = chunks[0]
        assert alter_chunk["type"] == "sql_create"
        assert alter_chunk["sql_type"] == "ALTER TABLE"
        assert alter_chunk["name"] == "my_schema.my_table"
        assert alter_chunk["filename"] == "query.sql"
        
        drop_chunk = chunks[1]
        assert drop_chunk["type"] == "sql_create"
        assert drop_chunk["sql_type"] == "DROP TABLE"
        assert drop_chunk["name"] == "my_schema.old_table"
        assert drop_chunk["filename"] == "query.sql"
        
        add_chunk = chunks[2]
        assert add_chunk["type"] == "sql_create"
        assert add_chunk["sql_type"] == "ADD CONSTRAINT"
        assert add_chunk["name"] == "pk_id"
        assert add_chunk["filename"] == "query.sql"
