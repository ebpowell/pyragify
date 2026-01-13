import pytest
import zipfile
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from pyragify.excel_processor import ExcelProcessor

@pytest.fixture
def mock_excel_file(tmp_path):
    return tmp_path / "test.xlsx"

@pytest.fixture
def mock_zip_file():
    with patch("zipfile.ZipFile") as mock_zip:
        yield mock_zip

def test_extract_connections_success(mock_excel_file):
    processor = ExcelProcessor(Path("."), Path("."))
    
    # Mock zipfile content
    xml_content = """
    <connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
        <connection name="TestConn">
            <dbPr connection="Provider=SQLOLEDB;Data Source=Server;" command="SELECT * FROM Table"/>
        </connection>
    </connections>
    """
    
    with patch("zipfile.is_zipfile", return_value=True):
        with patch("zipfile.ZipFile") as MockZip:
            mock_zip_instance = MockZip.return_value
            mock_zip_instance.__enter__.return_value = mock_zip_instance
            mock_zip_instance.namelist.return_value = ['xl/connections.xml']
            
            # Mock opening the file inside zip
            mock_file = mock_open(read_data=xml_content).return_value
            mock_zip_instance.open.return_value = mock_file
            
            connections = processor._extract_connections(mock_excel_file)
            
            assert len(connections) == 1
            assert connections[0]["name"] == "TestConn"
            assert connections[0]["type"] == "Database/SQL"
            assert connections[0]["connection_string"] == "Provider=SQLOLEDB;Data Source=Server;"
            assert connections[0]["command_text"] == "SELECT * FROM Table"

def test_extract_connections_no_file(mock_excel_file):
    processor = ExcelProcessor(Path("."), Path("."))
    
    with patch("zipfile.is_zipfile", return_value=True):
        with patch("zipfile.ZipFile") as MockZip:
            mock_zip_instance = MockZip.return_value
            mock_zip_instance.__enter__.return_value = mock_zip_instance
            mock_zip_instance.namelist.return_value = ['other.xml']
            
            connections = processor._extract_connections(mock_excel_file)
            
            assert connections == []

def test_extract_connections_not_zip(mock_excel_file):
    processor = ExcelProcessor(Path("."), Path("."))
    
    with patch("zipfile.is_zipfile", return_value=False):
        connections = processor._extract_connections(mock_excel_file)
        assert connections == []

def test_format_chunk_connection():
    processor = ExcelProcessor(Path("."), Path("."))
    chunk = {
        "type": "excel_connection",
        "name": "TestConn",
        "content": {
            "type": "Database/SQL",
            "connection_string": "conn_str",
            "command_text": "SELECT 1"
        }
    }
    
    formatted = processor.format_chunk(chunk)
    assert "Excel Connection: TestConn" in formatted
    assert "Type: Database/SQL" in formatted
    assert "Connection String: conn_str" in formatted
    assert "Command Text: SELECT 1" in formatted
