
import sys
import os
from pathlib import Path
import csv
import logging

# Add src to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src/pyragify"))

from tabular_tokenizer import TabularDataTokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_dummy_csv(path):
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Name", "Role"])
        writer.writerow([1, "Alice", "Engineer"])
        writer.writerow([2, "Bob", "Designer"])
        writer.writerow([3, "Charlie", "Manager"])

def create_dummy_excel(path):
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Employees"
        ws.append(["ID", "Name", "Role"])
        ws.append([101, "David", "DevOps"])
        ws.append([102, "Eve", "Product"])
        wb.save(path)
    except ImportError:
        logger.warning("openpyxl not installed, skipping Excel test creation.")

def main():
    output_dir = Path("output/tokenizer_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    tokenizer = TabularDataTokenizer(output_dir=output_dir)

    # Test 1: CSV
    csv_path = output_dir / "test.csv"
    create_dummy_csv(csv_path)
    logger.info("Testing CSV processing...")
    out_csv = tokenizer.process_csv(csv_path)
    logger.info(f"CSV output: {out_csv}")
    
    # Verify CSV output
    if out_csv.exists():
        print("--- CSV Output Content ---")
        print(out_csv.read_text())
        print("--------------------------")

    # Test 2: Excel
    xlsx_path = output_dir / "test.xlsx"
    create_dummy_excel(xlsx_path)
    if xlsx_path.exists():
        logger.info("Testing Excel processing...")
        out_excel_files = tokenizer.process_excel(xlsx_path)
        for f in out_excel_files:
            logger.info(f"Excel output: {f}")
            print(f"--- Excel Output Content ({f.name}) ---")
            print(f.read_text())
            print("---------------------------------------")

    # Test 3: List of Dicts
    data = [
        {"ID": 201, "Name": "Frank", "Role": "Sales"},
        {"ID": 202, "Name": "Grace", "Role": "Marketing"}
    ]
    logger.info("Testing Dict processing...")
    out_dict = tokenizer.process_dicts(data, output_dir / "dicts.txt")
    if out_dict.exists():
        print("--- Dict Output Content ---")
        print(out_dict.read_text())
        print("---------------------------")

if __name__ == "__main__":
    main()
