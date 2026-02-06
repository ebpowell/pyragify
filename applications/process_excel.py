import sys
from pathlib import Path

# 1. Get the path to the 'applications' folder (where this script is)
current_dir = Path(__file__).resolve().parent

# 2. Go up one level to the Project Root, then into 'src'
#    Structure: applications/ -> (up) -> Root -> (down) -> src
src_path = current_dir.parent / "src/pyragify"

# 3. Add this path to sys.path so Python looks there for modules
sys.path.append(str(src_path))

from processor import RepoContentProcessor, FileProcessor
from excel_processor import ExcelDataProcessor

if __name__ == "__main__":
    repo_folder = '/mnt/c/Users/UVP/'
    #repo_folder = '/home/ebpowell/TradeOutreach/'
    repo_name = 'ITSD'
    repo_path = Path(repo_folder + repo_name)
    output_dir = Path(repo_folder + '/output_'+ repo_name)
    # processor = RepoContentProcessor(repo_path)
    hashes_file = output_dir / "hashes.json"
    if hashes_file.exists():
        hashes_file.unlink()
    skip_folders = [".venv", "venv", "build", "dist", "__pycache__", ".idea", ".git", "output"]
    skip_patterns = ["**/*.pyc", "**/__pycache__", "**/venv", "**/.venv"]

    processor = RepoContentProcessor(repo_path, output_dir, skip_patterns=skip_patterns, skip_dirs=skip_folders,
                                     processor_class=FileProcessor)
    processor.process_repo()
    # Parse the DATA from the Excel file
    obj_excel = ExcelDataProcessor(repo_path)
    obj_excel.sanitize_spreadsheet_for_llm(output_dir)
