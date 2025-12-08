import pytest
from pathlib import Path
from pyragify.powerbi_processor import pbi_processor

@pytest.fixture
def sample_model_tmdl(tmp_path):
    """Fixture for model.tmdl."""
    file_path = tmp_path / "model.tmdl"
    file_path.write_text("""
model Model
	culture: en-US
	defaultPowerBIDataSourceVersion: powerBI_V3
	sourceQueryCulture: en-US
	dataAccessOptions
		legacyRedirects
		returnErrorValuesAsNull

ref table Date
ref table Sales
ref table 'Product'
""")
    return file_path

@pytest.fixture
def sample_tmdl_file(tmp_path):
    """Fixture for a sample TMDL file with tables and other keywords."""
    file_path = tmp_path / "tables.tmdl"
    file_path.write_text("""
table Date
    lineageTag: 2d1234...

    column Date
        dataType: dateTime
        formatString: Short Date

table Sales
    lineageTag: 3e5678...

    measure 'Total Sales' = SUM(Sales[Amount])
        formatString: $#,##0

    partition Partition1
        mode: import
        source = M

    annotation PBI_ResultType = Table
""")
    return file_path

@pytest.fixture
def sample_python_file(tmp_path):
    """Fixture for a sample Python file to test delegation."""
    file_path = tmp_path / "script.py"
    file_path.write_text("print('hello')")
    return file_path

class TestPbiProcessor:

    def test_chunk_tmdl_file(self, sample_tmdl_file, tmp_path):
        """Test TMDL chunking logic."""
        output_dir = tmp_path / "output"
        processor = pbi_processor(tmp_path, output_dir)
        
        chunks, line_count = processor.chunk_tmdl_file(sample_tmdl_file)
        
        assert line_count > 0
        # Expected chunks:
        # 1. table Date
        # 2. column Date
        # 3. table Sales
        # 4. measure 'Total Sales'
        # 5. partition Partition1
        # 6. annotation PBI_ResultType
        assert len(chunks) == 6
        
        types = [c["type"] for c in chunks]
        assert "table" in types
        assert "column" in types
        assert "measure" in types
        assert "partition" in types
        assert "annotation" in types
        
        # Verify specific content containment
        col_chunk = next(c for c in chunks if c["type"] == "column")
        assert col_chunk["name"] == "Date"
        assert "dataType: dateTime" in col_chunk["content"]
        
        measure_chunk = next(c for c in chunks if c["type"] == "measure")
        assert measure_chunk["name"] == "'Total Sales'"
        assert "formatString" in measure_chunk["content"]

        partition_chunk = next(c for c in chunks if c["type"] == "partition")
        assert partition_chunk["name"] == "Partition1"
        assert "mode: import" in partition_chunk["content"]
        
        # Verify parent association
        assert col_chunk["parent"] == "Date"
        assert measure_chunk["parent"] == "Sales"
        assert partition_chunk["parent"] == "Sales"
        
        # Annotation defined inside Sales table
        annotation_chunk = next(c for c in chunks if c["type"] == "annotation")
        assert annotation_chunk["parent"] == "Sales"

    def test_format_chunk_parent(self, tmp_path):
        """Test formatting with parent table."""
        processor = pbi_processor(tmp_path, tmp_path)
        chunk = {
            "type": "column",
            "name": "Date",
            "content": "dataType: dateTime",
            "parent": "DateTable"
        }
        formatted = processor.format_chunk(chunk)
        assert "Column: Date" in formatted
        assert "Table: DateTable" in formatted
        assert formatted.startswith("Table: DateTable")

    def test_chunk_file_delegation(self, sample_tmdl_file, sample_python_file, tmp_path):
        """Test that chunk_file delegates correctly."""
        output_dir = tmp_path / "output"
        processor = pbi_processor(tmp_path, output_dir)
        
        # Test .tmdl
        tmdl_chunks, _ = processor.chunk_file(sample_tmdl_file)
        assert tmdl_chunks[0]["type"] == "table"
        
        # Test .py delegation to super()
        # chunk_python_file from FileProcessor produces 'file' chunk for simple script or 'function'/'class'
        # with just print('hello'), likely falls back or produces empty 'function' list? 
        # Actually FileProcessor.chunk_python_file uses AST. print('hello') is body logic.
        # It might produce no function chunks, but `chunk_python_file` returns chunks list.
        # Let's just check it doesn't crash and returns list (empty or not).
        # Actually in FileProcessor fallback for .py is chunk_python_file.
        # If no func/class, it returns empty list? 
        # Re-reading FileProcessor: yes, if no func/class/comments, returns empty list.
        # Let's make sample_python_file have a function to be sure.
        sample_python_file.write_text("def foo(): pass")
        py_chunks, _ = processor.chunk_file(sample_python_file)
        assert len(py_chunks) > 0
        assert py_chunks[0]["type"] == "function"

    def test_format_chunk_table(self, tmp_path):
        """Test formatting of table chunks."""
        processor = pbi_processor(tmp_path, tmp_path)
        chunk = {
            "type": "table",
            "name": "MyTable",
            "content": "table MyTable\n  column ID"
        }
        formatted = processor.format_chunk(chunk)
        assert "Table: MyTable" in formatted
        assert "column ID" in formatted

    def test_format_chunk_delegation(self, tmp_path):
        """Test formatting delegation for standard chunks."""
        processor = pbi_processor(tmp_path, tmp_path)
        chunk = {
            "type": "function",
            "name": "my_func",
            "code": "def my_func(): pass"
        }
        formatted = processor.format_chunk(chunk)
        assert "Function: my_func" in formatted

    def test_chunk_model_tmdl(self, sample_model_tmdl, tmp_path):
        """Test model.tmdl chunking into index."""
        output_dir = tmp_path / "output"
        processor = pbi_processor(tmp_path, output_dir)
        
        chunks, line_count = processor.chunk_file(sample_model_tmdl)
        assert line_count > 0
        assert len(chunks) == 1
        
        index_chunk = chunks[0]
        assert index_chunk["type"] == "model_index"
        content = index_chunk["content"]
        assert "- Date" in content
        assert "- Sales" in content
        assert "- 'Product'" in content
