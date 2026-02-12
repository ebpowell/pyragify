import sys
import os
from pathlib import Path
import csv
import logging

# Add src to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src/pyragify"))
import psycopg2
from contextlib import contextmanager
from tabular_tokenizer import TabularDataTokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PgData:
    def __init__(self, connect_string, table_name):
        self.connect_string = connect_string
        self.table_name = table_name

    def __get_data(self):
        try:
            # Use a context manager for the connection too!
            with psycopg2.connect(self.connect_string) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"select * from {self.table_name};")
                    # Fetching here ensures data is captured before closure
                    return cursor.fetchall()
        except (Exception, psycopg2.DatabaseError) as error:
            raise error

    @contextmanager
    def get_cursor(self):
        conn = psycopg2.connect(self.connect_string)
        try:
            # We don't use 'with' here because we yield the cursor
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {self.table_name}")
            yield cur  # The cursor is still alive here!
        finally:
            cur.close()
            conn.close()

    def get_results(self):
        return self.__get_data()

def main(output_dir, connect_string, table_name):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = TabularDataTokenizer(output_dir=output_dir)
    obj_db = PgData(connect_string, table_name=table_name)
    # the_cursor = obj_db.get_cursor()
    with obj_db.get_cursor() as active_cursor:
        # processor.process_cursor(active_cursor, "users")
        tokenizer.process_cursor(active_cursor, table_name)

if __name__ == "__main__":
    connect_string= "dbname=itsd_analysis user=postgres password=postgres host=hgis-prj-mgmt port=5438"
    table_name = 'raw_data.v_itsd_positions'
    output_dir = '/home/ebpowell/ITSD'
    main(output_dir, connect_string, table_name)