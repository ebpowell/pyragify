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
from powerbi_processor import PBIProcessor
from sql_processor import SqlProcessor
from excel_processor import ExcelProcessor

if __name__ == "__main__":
    repo_folder = '/home/ebpowell/GIT_REPO/'
    repo_name = 'pyragify'
    repo_path = Path(repo_folder + repo_name)
    output_dir = Path(repo_folder + repo_name + '/output')
    hashes_file = output_dir / "hashes.json"
    if hashes_file.exists():
        hashes_file.unlink()
    skip_folders = [".venv", "venv", "build", "dist", "__pycache__", ".idea", ".git", "output"]
    skip_patterns = ["**/*.pyc", "**/__pycache__", "**/venv", "**/.venv"]

    # Use pbi_processor to handle PowerBI files
    # Need to locally overload skip_patterns with *.py, *.md, etc to use the appropriate function from FileProcessor
    # Also ignore .sql files here so they can be handled by SqlProcessor
    pbi_skip = skip_patterns + ['*.py', '*.md', '*.html', '*.css', '*.sql', '*.xlsx', '*.xlsm']
    processor = RepoContentProcessor(repo_path, output_dir, skip_patterns=pbi_skip, skip_dirs=skip_folders,
                                     processor_class=PBIProcessor)
    processor.process_repo()
    del processor

    # Handle SQL files with SqlProcessor
    sql_skip = skip_patterns + ['*.py', '*.md', '*.html', '*.css', '*.tmdl', '*.xlsx', '*.xlsm']
    processor = RepoContentProcessor(repo_path, output_dir, skip_patterns=sql_skip, skip_dirs=skip_folders,
                                     processor_class=SqlProcessor)
    processor.process_repo()
    del processor

    excel_skip = skip_patterns + ['*.py', '*.md', '*.html', '*.sql','*.tmdl', '*.css']
    processor = RepoContentProcessor(repo_path, output_dir, skip_patterns=excel_skip, skip_dirs=skip_folders,
                                     processor_class=ExcelProcessor)
    processor.process_repo()
    del processor

    # If a mixed repo (has PowerBI AND Python AND SQL etc.) locally overload skip_patterns with *.tmdl and *.sql
    # to keep from re-running the PowerBI and SQL files).
    py_skip = skip_patterns + ['*.tmdl', '*.sql', '*.xlsx', '*.xlsm']
    processor = RepoContentProcessor(repo_path, output_dir, skip_patterns=py_skip, skip_dirs=skip_folders,
                                     processor_class=FileProcessor)
    processor.process_repo()
    del processor